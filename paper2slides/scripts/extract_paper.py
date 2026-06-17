"""
extract_paper.py — Stage 1: PDF 解析（文本 + 嵌入图 + 整页渲染 + caption 索引）

输入：paper.pdf
输出（写到 workdir）：
  - raw_text.txt              按页分隔的纯文本，分隔符 "===== PAGE N ====="
  - figures/fig-NNN.{jpg,...} 嵌入图（pdfimages -j 输出）
  - pages/page-NN.png         整页 PNG（pdftoppm 渲染，150 dpi）
  - figures_index.json        captions / embedded_images / page_renders 三个独立列表

为什么 captions 与 embedded_images 分两列：pdfimages 不带页码信息，强行配对会出错。
让 Stage 4 的你看到完整候选自己挑——这是"协调器路线"的体现。

CLI:
    python scripts/extract_paper.py <paper.pdf> [--output <out.pptx>] [--ocr]
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from workdir import resolve_workspace  # noqa: E402

PAGE_SEP = "===== PAGE {n} ====="
TEXT_DENSITY_WARN = 200  # 每页字符数下限，低于此提示 OCR

CAPTION_RE = re.compile(
    r"^\s*(?P<kind>Figure|Fig\.?|Table)\s*(?P<num>\d+)[\.\:]\s+(?P<text>.+?)$",
    re.IGNORECASE | re.MULTILINE,
)


def _need(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise SystemExit(f"required tool not in PATH: {cmd}")


def extract_text(pdf: Path) -> list[str]:
    import pdfplumber
    with pdfplumber.open(str(pdf)) as p:
        return [pg.extract_text() or "" for pg in p.pages]


def extract_embedded_images(pdf: Path, out_dir: Path) -> list[Path]:
    """统一输出 PNG。pdfimages 默认是 PPM/PBM，PptxGenJS 加载不了；用 -png 强制。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "fig"
    try:
        subprocess.run(
            ["pdfimages", "-png", str(pdf), str(prefix)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[warn] pdfimages failed: {e.stderr.decode(errors='replace')}",
              file=sys.stderr)
        return []
    return sorted(out_dir.glob("fig-*.png"))


def render_pages(pdf: Path, out_dir: Path, dpi: int = 300) -> list[Path]:
    """整页渲染。默认 300 dpi（学术表格小字清晰阈值），加 -hide-annotations 去掉
    论文 PDF 自带的 hyperlink 绿框（[N] 引用 / cross-references）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), "-hide-annotations",
         str(pdf), str(prefix)],
        check=True, capture_output=True,
    )
    return sorted(out_dir.glob("page-*.png"))


def find_captions(pages_text: list[str]) -> list[dict]:
    out: list[dict] = []
    for page_idx, text in enumerate(pages_text, start=1):
        for m in CAPTION_RE.finditer(text):
            kind_raw = m.group("kind").lower().rstrip(".")
            kind = "figure" if kind_raw in ("figure", "fig") else "table"
            num = int(m.group("num"))
            head = m.group("text").strip()
            # caption 经常跨多行；向后吃到空行或下一个 caption 起点
            tail = text[m.end():m.end() + 400]
            stop = re.search(
                r"\n\s*\n|^\s*(?:Figure|Fig\.?|Table)\s*\d+",
                tail, re.MULTILINE,
            )
            extra = tail[:stop.start()] if stop else tail
            caption = (head + " " + extra.strip()).strip()
            out.append({
                "id": f"{kind}{num}",
                "kind": kind,
                "num": num,
                "page": page_idx,
                "caption": caption,
            })
    return out


# Stage 4 让你视觉估表格 bbox 误差 ±5%（实测 attention.pdf 上 Table 1 底线被切，
# Tables 2-4 第一次裁带入正文）。改用 pdfplumber.find_tables 精确定位。
#
# 设计取舍：只用 lines 策略，不上 text 策略。
#   - lines 策略：精确边界（rule-based），漏检 booktabs 风格（无垂直线，仅 \toprule/\midrule/\bottomrule）
#   - text 策略：实测在 booktabs 上把整列正文圈成 "1 列 N 行的伪表"，bbox 覆盖几乎整页 — 比缺
#     bbox 还糟（让 Stage 4 拿到错误的"精确"信号）。所以宁可漏检也不要假阳性。
#   - 漏检的表（如 booktabs）通过缺失 bbox 字段告知 Stage 4，让你走视觉估算 fallback
def detect_tables(pdf_path: Path) -> list[dict]:
    """返回 [{page, bbox: [x,y,w,h] in 0..1, rows, cols, confidence}, ...]，按 (page, top, left) 排序。"""
    try:
        import pdfplumber
    except ImportError:
        return []
    out: list[dict] = []
    try:
        with pdfplumber.open(str(pdf_path)) as p:
            for page_idx, pg in enumerate(p.pages, start=1):
                W, H = pg.width, pg.height
                for t in _safe_find_tables(pg, "lines"):
                    extracted = _safe_extract(t)
                    if len(extracted) < 3:
                        continue
                    # 过滤 "几乎整页" 的虚假表（cell 拼接、版心整体被识别成表）
                    x0, top, x1, bottom = t.bbox
                    if (x1 - x0) > 0.85 * W and (bottom - top) > 0.7 * H:
                        continue
                    out.append(_table_record(
                        page_idx, t.bbox, extracted, W, H, "lines", "high"))
    except Exception as e:
        print(f"[warn] table detection skipped: {e}", file=sys.stderr)
        return []
    out.sort(key=lambda r: (r["page"], r["_top"], r["_left"]))
    for r in out:
        del r["_top"]; del r["_left"]
    return out


def _safe_find_tables(pg, strategy: str) -> list:
    settings = {"vertical_strategy": strategy, "horizontal_strategy": strategy}
    try:
        return pg.find_tables(table_settings=settings)
    except Exception:
        return []


def _safe_extract(table) -> list:
    """t.extract() 返回 List[List[Optional[str]]]；某些 PDF 会抛，安全降级到空。"""
    try:
        return table.extract() or []
    except Exception:
        return []


def _table_record(page: int, bbox_pts, extracted: list,
                  page_w: float, page_h: float,
                  source: str, confidence: str) -> dict:
    """pdfplumber bbox 是 (x0, top, x1, bottom) in points, top-origin → 转相对 0..1 的 [x,y,w,h]。"""
    x0, top, x1, bottom = bbox_pts
    n_rows = len(extracted)
    n_cols = max((len(r) for r in extracted), default=0)
    return {
        "page": page,
        "bbox": [round(x0 / page_w, 4), round(top / page_h, 4),
                 round((x1 - x0) / page_w, 4),
                 round((bottom - top) / page_h, 4)],
        "rows": n_rows,
        "cols": n_cols,
        "bbox_source": f"pdfplumber:{source}",
        "bbox_confidence": confidence,
        "_top": top, "_left": x0,  # 仅用于排序，返回前删
    }


def attach_bbox_to_captions(captions: list[dict],
                            detected: list[dict]) -> None:
    """把 detected 按 page 出现顺序 zip 给 kind=='table' 的 caption。配不到的字段直接省略。"""
    by_page: dict[int, list[dict]] = {}
    for d in detected:
        by_page.setdefault(d["page"], []).append(d)
    seen_index_per_page: dict[int, int] = {}
    for c in captions:
        if c.get("kind") != "table":
            continue
        page = c["page"]
        idx = seen_index_per_page.get(page, 0)
        candidates = by_page.get(page, [])
        if idx < len(candidates):
            d = candidates[idx]
            c["bbox"] = d["bbox"]
            c["bbox_source"] = d["bbox_source"]
            c["bbox_confidence"] = d["bbox_confidence"]
        seen_index_per_page[page] = idx + 1


def _page_renders(workdir: Path, pages_png: list[Path]) -> list[dict]:
    """从已渲染的 page-NN.png 文件名抽 page 号，返回按 page 升序的 [{page, path}]。"""
    out: list[dict] = []
    for png in pages_png:
        m = re.search(r"page-(\d+)\.png$", png.name)
        if m:
            out.append({"page": int(m.group(1)),
                        "path": str(png.relative_to(workdir))})
    return sorted(out, key=lambda x: x["page"])


def _run_local(ws, args) -> dict:
    """旧 Stage 1 路径：pdfplumber 文本 + pdfimages 嵌入图 + pdftoppm 整页 + find_captions + detect_tables。"""
    _need("pdfimages")
    _need("pdftoppm")

    pages_text = extract_text(ws.paper_path)
    n_pages = len(pages_text)
    avg_density = sum(len(t) for t in pages_text) / max(1, n_pages)
    if avg_density < TEXT_DENSITY_WARN and not args.ocr:
        print(
            f"[warn] sparse text ({avg_density:.0f} chars/page). "
            "Try --ocr if this is a scanned paper.",
            file=sys.stderr,
        )

    if args.ocr:
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError:
            raise SystemExit(
                "--ocr requires: pip install pytesseract pdf2image")
        images = convert_from_path(str(ws.paper_path))
        pages_text = [pytesseract.image_to_string(im) for im in images]
        n_pages = len(pages_text)

    body: list[str] = []
    for i, t in enumerate(pages_text, start=1):
        body.append(PAGE_SEP.format(n=i))
        body.append(t)
        body.append("")
    ws.raw_text_path.write_text("\n".join(body), encoding="utf-8")

    embedded = extract_embedded_images(ws.paper_path, ws.figures_dir)
    pages_png = render_pages(ws.paper_path, ws.pages_dir, dpi=args.dpi)
    captions = find_captions(pages_text)

    detected_tables = detect_tables(ws.paper_path)
    attach_bbox_to_captions(captions, detected_tables)

    index = {
        "schema_version": "0.1",
        "source_pdf": str(ws.paper_path),
        "n_pages": n_pages,
        "extract_backend": "local",
        "avg_text_density": round(avg_density, 1),
        "ocr_used": args.ocr,
        "captions": captions,
        "embedded_images": [
            {"path": str(p.relative_to(ws.workdir))} for p in embedded
        ],
        "page_renders": _page_renders(ws.workdir, pages_png),
    }
    ws.figures_index_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    n_tables_with_bbox = sum(
        1 for c in captions if c.get("kind") == "table" and "bbox" in c)
    return {
        "stage": "extract",
        "backend": "local",
        "workdir": str(ws.workdir),
        "n_pages": n_pages,
        "n_captions": len(captions),
        "n_embedded_images": len(embedded),
        "n_tables_with_bbox": n_tables_with_bbox,
        "raw_text_path": str(ws.raw_text_path),
        "figures_index_path": str(ws.figures_index_path),
    }


def _run_mineru(ws, args, token: str) -> dict:
    """新 Stage 1 路径：MinerU 云 API 解析。一次性产 paper_meta.json + figures_index.json + 高清裁图。"""
    # 局部 import：让 local 后端不依赖 requests/zipfile 链路
    sys.path.insert(0, str(Path(__file__).parent))
    from lib import mineru_client, mineru_parser  # noqa: E402

    _need("pdftoppm")  # 仍要整页 PNG（高清裁图与未来公式裁源）

    paper_path = ws.paper_path
    size_mb = paper_path.stat().st_size / (1024 * 1024)
    print(f"[mineru] uploading {paper_path.name} ({size_mb:.1f} MB) "
          f"to mineru.net cloud API", file=sys.stderr)

    # 1) 提交任务（本地 PDF 走 file-urls/batch）
    task_id = mineru_client.submit_local_pdf(paper_path, token)
    print(f"[mineru] task_id = {task_id}", file=sys.stderr)

    # 2) 轮询
    result = mineru_client.poll_task(task_id, token, timeout_s=300)
    state = result.get("state", "")
    if state != "done":
        raise RuntimeError(
            f"task {task_id} ended with state={state!r}: "
            f"{result.get('err_msg', '(no err_msg)')}")
    zip_url = result.get("full_zip_url")
    if not zip_url:
        raise RuntimeError(f"task {task_id} done but no full_zip_url: {result}")

    # 3) 下载 + 解压
    zip_bytes = mineru_client.download_zip(zip_url)
    unzipped = ws.workdir / "_mineru"
    mineru_client.extract_zip(zip_bytes, unzipped)

    # 4) 渲染整页 PNG（mineru 不给高清整页，需我们自己裁高清要这个）
    pages_png = render_pages(ws.paper_path, ws.pages_dir, dpi=args.dpi)

    # 5) 调 parser 写产物
    page_renders = _page_renders(ws.workdir, pages_png)
    pm_path, fi_path = mineru_parser.write_outputs(
        unzipped_dir=unzipped,
        workdir=ws.workdir,
        source_pdf=str(ws.paper_path),
        page_renders=page_renders,
        mineru_task_id=task_id,
    )

    # 简单统计返回
    pm = json.loads(pm_path.read_text(encoding="utf-8"))
    fi = json.loads(fi_path.read_text(encoding="utf-8"))
    return {
        "stage": "extract",
        "backend": "mineru",
        "workdir": str(ws.workdir),
        "n_pages": fi.get("n_pages"),
        "title": pm.get("title", "")[:80],
        "n_authors": len(pm.get("authors", [])),
        "n_sections": len(pm.get("sections", [])),
        "n_figures": len(pm.get("figures", [])),
        "n_tables": len(pm.get("tables", [])),
        "n_equations": len(pm.get("equations", [])),
        "references_count": pm.get("references_count"),
        "paper_meta_path": str(pm_path),
        "figures_index_path": str(fi_path),
        "mineru_task_id": task_id,
    }


def _choose_backend(args) -> str:
    """auto: 见 token 用 mineru，否则 local。其他模式直传。"""
    if args.backend != "auto":
        return args.backend
    return "mineru" if os.environ.get("MINERU_API_TOKEN", "").strip() else "local"


def main() -> None:
    p = argparse.ArgumentParser(description="paper2slides Stage 1: PDF extract")
    p.add_argument("paper", type=Path)
    p.add_argument("--output", type=Path, default=None,
                   help="(透传给 workdir 的最终 .pptx 路径；本阶段不直接产 .pptx)")
    p.add_argument("--ocr", action="store_true",
                   help="文本稀疏时改走 OCR（仅 local 后端，需 pytesseract + pdf2image）")
    p.add_argument(
        "--backend", default="auto",
        choices=("auto", "mineru", "mineru-strict", "local"),
        help=("后端：auto = 见 MINERU_API_TOKEN 走 mineru 否则 local；"
              "mineru = 强制云端，失败 fallback 到 local；"
              "mineru-strict = 强制云端，失败直接报错；"
              "local = 旧 pdfplumber 路径"),
    )
    p.add_argument(
        "--dpi", type=int, default=300,
        help=("整页 PNG 渲染分辨率（默认 300，clamp 100-600）。"
              "学术论文表格小字清晰阈值在 250-300 区间；"
              "论文超长可降到 200 减载，对超细公式可升到 400"),
    )
    args = p.parse_args()
    args.dpi = max(100, min(600, args.dpi))

    ws = resolve_workspace(args.paper, args.output)
    ws.ensure()

    chosen = _choose_backend(args)
    if chosen in ("mineru", "mineru-strict"):
        token = os.environ.get("MINERU_API_TOKEN", "").strip()
        if not token:
            if chosen == "mineru-strict":
                raise SystemExit(
                    "[mineru-strict] MINERU_API_TOKEN env var is required")
            print("[mineru] no MINERU_API_TOKEN; using local backend",
                  file=sys.stderr)
            chosen = "local"

    if chosen in ("mineru", "mineru-strict"):
        try:
            result = _run_mineru(ws, args, token)
        except Exception as e:
            if chosen == "mineru-strict":
                raise
            print(f"[mineru] fallback to local: {type(e).__name__}: {e}",
                  file=sys.stderr)
            result = _run_local(ws, args)
    else:
        result = _run_local(ws, args)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
