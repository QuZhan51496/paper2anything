"""
extract_paper.py — Stage 1: PDF 解析（MinerU 云 API）

输入：paper.pdf
输出（写到 workdir）：
  - paper_meta.json     title/authors/sections/figures/tables/equations（mineru_parser 产出）
  - figures_index.json  captions / 高清裁图索引 / page_renders 三个列表
  - pages/page-NN.png   整页 PNG（pdftoppm 渲染，默认 300 dpi，供高清裁图与公式裁源）
  - 高清 figure/table 裁图

解析统一走 MinerU 云端；需要 MINERU_API_TOKEN。失败即报错。

CLI:
    python scripts/extract_paper.py <paper.pdf> [--output <out.pptx>] [--dpi 300]
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


def _need(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise SystemExit(f"required tool not in PATH: {cmd}")


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


def _page_renders(workdir: Path, pages_png: list[Path]) -> list[dict]:
    """从已渲染的 page-NN.png 文件名抽 page 号，返回按 page 升序的 [{page, path}]。"""
    out: list[dict] = []
    for png in pages_png:
        m = re.search(r"page-(\d+)\.png$", png.name)
        if m:
            out.append({"page": int(m.group(1)),
                        "path": str(png.relative_to(workdir))})
    return sorted(out, key=lambda x: x["page"])


def _run_mineru(ws, args, token: str) -> dict:
    """Stage 1：MinerU 云 API 解析。一次性产 paper_meta.json + figures_index.json + 高清裁图。"""
    # 局部 import：mineru 专用解析依赖（requests/zipfile 链路）按需加载
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


def main() -> None:
    p = argparse.ArgumentParser(
        description="paper2slides Stage 1: PDF extract (MinerU cloud)")
    p.add_argument("paper", type=Path)
    p.add_argument("--output", type=Path, default=None,
                   help="(透传给 workdir 的最终 .pptx 路径；本阶段不直接产 .pptx)")
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

    token = os.environ.get("MINERU_API_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "MINERU_API_TOKEN env var is required (MinerU cloud parsing). "
            "Get one at https://mineru.net/apiManage/token")

    result = _run_mineru(ws, args, token)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
