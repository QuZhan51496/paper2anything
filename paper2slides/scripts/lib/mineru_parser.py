"""
mineru_parser.py — MinerU 解压输出 → paper2slides schema

输入：MinerU 解析任务下载并解压后的目录（含 content_list_v2.json + layout.json）
输出：
  - paper_meta.json           （title / authors / abstract / sections / figures / tables / equations / references_count）
  - figures_index.json        （含 captions[].bbox 与 high_res_crop_path）
  - figures/<id>.png          （从 pages/page-NN.png 高清裁出的 figure / table / equation）

设计要点：
  - bbox 来源：figure / equation 直接从 content_list_v2[i].bbox；table 从 layout.json
    的 para_blocks 配对（按 page + 同页顺序）
  - 全部坐标用 layout.pdf_info[page].page_size = [W, H] 归一化到 0..1，top-origin
  - LaTeX 清洗：MinerU 会把字母间错插空格（"A t t e n t i o n"），但要保留控制序列后的必要空格
  - 子图归并：caption 不带 "Figure N" 的 image 暂存 staging，遇下一带编号 caption 合并为 subfigures
  - kind 分类复用 sectionize.py 的关键词表，保证两条后端路径的 kind 一致

CLI（无网络测试）：
    python -m scripts.lib.mineru_parser <unzipped_dir> <workdir>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 复用 sectionize 的关键词表，保证 kind 跨后端一致
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.sectionize import (  # noqa: E402
    NUMBERING, NUMBERED_KEYWORDS, TOP_LEVEL_KEYWORDS,
)

EXCLUDED_TYPES = {
    "page_header", "page_footer", "page_number",
    "page_aside_text", "page_footnote",
}

LICENSE_WATERMARK_HINT = "provided proper attribution"


# --------------------------------------------------------------------------- #
# 通用辅助
# --------------------------------------------------------------------------- #


def _join_text(items: list) -> str:
    """把 [{type:'text', content:'...'}, ...] 拼成一个字符串。"""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append(it.get("content", "") or "")
        else:
            out.append(str(it))
    return "".join(out).strip()


def _page_size(layout: dict, page_idx: int) -> tuple[float, float]:
    page = layout["pdf_info"][page_idx]
    W, H = page["page_size"]
    return float(W), float(H)


def _norm_bbox_pts(bbox_pts: list, layout: dict, page_idx: int) -> list:
    """[x0, y0, x1, y1] (绝对像素，top-origin) → [x, y, w, h] (0..1)。"""
    W, H = _page_size(layout, page_idx)
    x0, y0, x1, y1 = bbox_pts
    return [
        round(x0 / W, 4),
        round(y0 / H, 4),
        round((x1 - x0) / W, 4),
        round((y1 - y0) / H, 4),
    ]


def _union_bbox(bboxes: list[list]) -> list:
    """多个 [x, y, w, h] 0..1 → 它们的并集 [x, y, w, h]。"""
    x0 = min(b[0] for b in bboxes)
    y0 = min(b[1] for b in bboxes)
    x1 = max(b[0] + b[2] for b in bboxes)
    y1 = max(b[1] + b[3] for b in bboxes)
    return [round(x0, 4), round(y0, 4),
            round(x1 - x0, 4), round(y1 - y0, 4)]


def clean_latex(s: str) -> str:
    r"""
    MinerU VLM 会把字母间错插空格（"A t t e n t i o n" → "Attention"）。
    只做这一步即可——LaTeX 控制序列（如 \operatorname、\frac、\sqrt）后跟的
    通常是 `{` 或空白，被 step 1 不会破坏。

    早期版本试图给 `\word + 字母` 自动补空格，但贪婪量词 + 回溯会把 `\operatorname`
    拆成 `\operatornam e`（regex 缩短匹配以满足后置字母条件）。已移除。
    """
    if not s:
        return ""
    return re.sub(r'(?<=[A-Za-z])\s+(?=[A-Za-z])', '', s).strip()


def _classify_kind(title_text: str) -> str:
    """复用 sectionize 的关键词表把章节标题映射成 kind。"""
    s = title_text.strip()
    # 去 numbering 前缀
    s = re.sub(rf"^{NUMBERING}\s*", "", s, flags=re.IGNORECASE).strip().lower()
    # TOP_LEVEL（独立词）
    for kw, kind in TOP_LEVEL_KEYWORDS:
        if re.fullmatch(rf"\s*(?:{kw})\s*", s, flags=re.IGNORECASE):
            return kind
    # NUMBERED（关键词后允许 0-4 个补充词）
    for kw, kind in NUMBERED_KEYWORDS:
        if re.fullmatch(
            rf"\s*(?:{kw})(?:\s+\S+){{0,4}}\s*", s, flags=re.IGNORECASE,
        ):
            return kind
    return "other"


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #


def _find_mineru_output(unzipped_dir: Path, basename: str) -> Path:
    # MinerU's zip sometimes names result JSONs as `<job_id>_<basename>` instead
    # of the bare basename — the job-id used inside the zip is not the same as
    # the submission task_id our client returns, so we can't predict the prefix.
    exact = unzipped_dir / basename
    if exact.exists():
        return exact
    matches = sorted(unzipped_dir.glob(f"*{basename}"))
    if not matches:
        raise FileNotFoundError(f"{unzipped_dir}/{basename} (also no *_{basename})")
    return matches[0]


def load_mineru_outputs(unzipped_dir: Path) -> tuple[list, dict]:
    cl_path = _find_mineru_output(unzipped_dir, "content_list_v2.json")
    layout_path = _find_mineru_output(unzipped_dir, "layout.json")
    cl = json.loads(cl_path.read_text(encoding="utf-8"))
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    return cl, layout


# --------------------------------------------------------------------------- #
# 元信息提取
# --------------------------------------------------------------------------- #


def extract_title(cl: list) -> str:
    if not cl or not cl[0]:
        return ""
    for elem in cl[0]:
        if elem.get("type") != "title":
            continue
        if elem.get("content", {}).get("level") != 1:
            continue
        t = _join_text(elem["content"].get("title_content", []))
        if LICENSE_WATERMARK_HINT in t.lower():
            continue
        return t.strip()
    return ""


def extract_authors(cl: list) -> list[str]:
    if not cl or not cl[0]:
        return []
    page0 = cl[0]
    # 论文标题之后的位置
    start = None
    for i, elem in enumerate(page0):
        if elem.get("type") != "title":
            continue
        if elem.get("content", {}).get("level") != 1:
            continue
        t = _join_text(elem["content"].get("title_content", []))
        if LICENSE_WATERMARK_HINT in t.lower():
            continue
        start = i + 1
        break
    if start is None:
        return []
    # 截至 abstract（如果出现）
    end = len(page0)
    for j in range(start, len(page0)):
        elem = page0[j]
        if elem.get("type") == "title":
            t = _join_text(elem["content"].get("title_content", [])).lower()
            if "abstract" in t:
                end = j
                break

    authors: list[str] = []
    seen: set[str] = set()
    affil_re = re.compile(
        r"\b(university|institute|brain|research|lab|laborator(y|ies)|"
        r"inc|corp|college|google|facebook|meta|microsoft|amazon|"
        r"openai|anthropic|deepmind|nvidia|apple|college|department|school)\b",
        re.IGNORECASE,
    )
    # 上标符号（含 U+2217 ∗、U+2020 †、U+2021 ‡、U+00A7 §、U+00B6 ¶ 等）
    superscripts = " .*†‡§¶∗⋆⁎\t\n0123456789"
    for elem in page0[start:end]:
        if elem.get("type") != "paragraph":
            continue
        text = _join_text(elem["content"].get("paragraph_content", []))
        if any(x in text.lower() for x in ("@", "http://", "https://", "doi:")):
            continue
        if affil_re.search(text):
            continue
        for raw in re.split(r",| and |;|·", text):
            cand = raw.strip(superscripts)
            if not (2 < len(cand) < 40):
                continue
            # 主要由字母与空格/连字符/句点组成
            stripped = re.sub(r"[\s\-\.\']", "", cand)
            if not stripped.isalpha():
                continue
            if cand in seen:
                continue
            authors.append(cand)
            seen.add(cand)
    return authors


def extract_abstract(cl: list) -> str:
    if not cl or not cl[0]:
        return ""
    page0 = cl[0]
    abs_start = None
    for i, elem in enumerate(page0):
        if elem.get("type") != "title":
            continue
        t = _join_text(elem["content"].get("title_content", [])).lower()
        if "abstract" in t:
            abs_start = i + 1
            break
    if abs_start is None:
        return ""
    paras: list[str] = []
    for elem in page0[abs_start:]:
        if elem.get("type") == "title":
            break
        if elem.get("type") == "paragraph":
            paras.append(_join_text(elem["content"].get("paragraph_content", [])))
    return " ".join(paras).strip()


# --------------------------------------------------------------------------- #
# 章节切分
# --------------------------------------------------------------------------- #


def _section_depth(title_text: str) -> int:
    """根据数字前缀判断章节层级："3" → 1, "3.1" → 2, "3.1.1" → 3，无前缀 → 0。"""
    m = re.match(r"^(\d+(?:\.\d+)*)", title_text.strip())
    if m:
        return m.group(1).count(".") + 1
    return 0


def iter_sections(cl: list) -> list[dict]:
    flat: list[tuple[int, dict]] = []
    for page_idx, page_elems in enumerate(cl):
        for elem in page_elems:
            flat.append((page_idx, elem))

    # 选 title 作为切分点：
    #   - depth >= 2 视为子节，跳过（短期不切 subsections）
    #   - depth == 0 且 kind == "other" 视为论文 title 或 license/水印杂项，跳
    #   - 其他保留作为顶层 section
    titles: list[tuple[int, str]] = []
    for i, (_, elem) in enumerate(flat):
        if elem.get("type") != "title":
            continue
        if elem.get("content", {}).get("level") != 1:
            continue
        t = _join_text(elem["content"].get("title_content", []))
        if not t:
            continue
        if LICENSE_WATERMARK_HINT in t.lower():
            continue
        depth = _section_depth(t)
        kind = _classify_kind(t)
        if depth >= 2:
            continue
        if depth == 0 and kind == "other":
            continue
        titles.append((i, t))

    sections: list[dict] = []
    seen_kinds: dict[str, int] = {}
    for k, (start_i, title_text) in enumerate(titles):
        end_i = titles[k + 1][0] if k + 1 < len(titles) else len(flat)
        page_start = flat[start_i][0] + 1
        last_page = page_start
        text_parts: list[str] = []
        for j in range(start_i + 1, end_i):
            page_idx, elem = flat[j]
            t = elem.get("type")
            if t in EXCLUDED_TYPES:
                continue
            last_page = page_idx + 1
            if t == "paragraph":
                text_parts.append(_join_text(
                    elem["content"].get("paragraph_content", [])))

        kind = _classify_kind(title_text)
        n = seen_kinds.get(kind, 0) + 1
        seen_kinds[kind] = n
        sid = kind if n == 1 else f"{kind}{n}"
        sections.append({
            "id": sid,
            "kind": kind,
            "title": title_text.strip(),
            "page_start": page_start,
            "page_end": last_page,
            "text": "\n".join(p for p in text_parts if p).strip(),
            "subsections": [],
        })
    return sections


# --------------------------------------------------------------------------- #
# Figures / Tables / Equations
# --------------------------------------------------------------------------- #


def iter_figures(cl: list, layout: dict) -> list[dict]:
    """
    bbox 一律取自 layout.json/pdf_info[].para_blocks[type='image']，按页内顺序配对。
    **不**用 content_list_v2 的 elem['bbox']——实测它的坐标系跟 layout.page_size 不一致
    （前者疑似是渲染坐标 / 缩放坐标），用 page_size 归一化会把 figure 切到错的位置。
    table 路径已是这样做的，这里同步对齐。
    """
    # 预聚合 layout 各页 type='image' 的 bbox。**不**排序——para_blocks 已是 reading order
    # （左→右、上→下），与 content_list_v2 的 element 顺序一致；强行按 top 排会让
    # "page 4 Scaled+Multi-Head 子图"这种同页多图的左右关系反过来配对。
    by_page: dict[int, list[list]] = {}
    for page_idx, page_layout in enumerate(layout.get("pdf_info", [])):
        for blk in page_layout.get("para_blocks", []):
            if blk.get("type") != "image":
                continue
            by_page.setdefault(page_idx, []).append(blk["bbox"])

    consumed: dict[int, int] = {}
    figures: list[dict] = []
    staging: list[dict] = []  # 无编号 caption 的 image，等下一个有编号的合并

    def _bbox_for_page(page_idx: int):
        avail = by_page.get(page_idx, [])
        i = consumed.get(page_idx, 0)
        if i >= len(avail):
            return None
        consumed[page_idx] = i + 1
        return _norm_bbox_pts(avail[i], layout, page_idx)

    for page_idx, page_elems in enumerate(cl):
        for elem in page_elems:
            if elem.get("type") != "image":
                continue
            cap_text = _join_text(elem["content"].get("image_caption", []))
            page_no = page_idx + 1
            bbox = _bbox_for_page(page_idx)

            m = re.search(r"Figure\s+(\d+)", cap_text, re.IGNORECASE)
            if m:
                num = int(m.group(1))
                fig = {
                    "id": f"figure{num}",
                    "kind": "figure",
                    "num": num,
                    "page": page_no,
                    "caption": cap_text,
                }
                if staging:
                    # 多子图：当前 image 自己也是 figure 的一个子图（不是"主图"）。
                    # bbox 取所有子图的并集，subfigures 完整列出每个子图的精确边界
                    # 供 Stage 3 视情况单独裁。
                    parts = list(staging) + [{
                        "page": page_no, "bbox": bbox, "caption": cap_text,
                    }]
                    staging = []
                    valid = [p for p in parts if p.get("bbox")]
                    if valid:
                        fig["bbox"] = _union_bbox([p["bbox"] for p in valid])
                        fig["bbox_source"] = "mineru:vlm"
                        fig["bbox_confidence"] = "high"
                    fig["subfigures"] = [
                        {"page": p["page"], "bbox": p["bbox"]} for p in valid
                    ]
                else:
                    # 单子图（无前序无编号 caption）：bbox 直接用当前
                    if bbox:
                        fig["bbox"] = bbox
                        fig["bbox_source"] = "mineru:vlm"
                        fig["bbox_confidence"] = "high"
                figures.append(fig)
            else:
                staging.append({"page": page_no, "bbox": bbox, "caption": cap_text})

    # 末尾仍有 staging：单独成 figure
    for i, s in enumerate(staging, start=1):
        fig = {
            "id": f"figure_unnamed_{i}",
            "kind": "figure",
            "num": None,
            "page": s["page"],
            "caption": s["caption"],
        }
        if s.get("bbox"):
            fig["bbox"] = s["bbox"]
            fig["bbox_source"] = "mineru:vlm"
            fig["bbox_confidence"] = "medium"
        figures.append(fig)
    return figures


def iter_tables(cl: list, layout: dict) -> list[dict]:
    # 预聚合 layout 中每页的 table bbox。para_blocks 已是 reading order，无需重排。
    by_page: dict[int, list[list]] = {}
    for page_idx, page_layout in enumerate(layout.get("pdf_info", [])):
        for blk in page_layout.get("para_blocks", []):
            if blk.get("type") != "table":
                continue
            by_page.setdefault(page_idx, []).append(blk["bbox"])

    consumed: dict[int, int] = {}
    tables: list[dict] = []
    for page_idx, page_elems in enumerate(cl):
        for elem in page_elems:
            if elem.get("type") != "table":
                continue
            cap_text = _join_text(elem["content"].get("table_caption", []))
            page_no = page_idx + 1

            bbox_norm = None
            avail = by_page.get(page_idx, [])
            i = consumed.get(page_idx, 0)
            if i < len(avail):
                bbox_norm = _norm_bbox_pts(avail[i], layout, page_idx)
                consumed[page_idx] = i + 1

            m = re.search(r"Table\s+(\d+)", cap_text, re.IGNORECASE)
            num = int(m.group(1)) if m else None
            tid = f"table{num}" if num else f"table_unnamed_{len(tables) + 1}"

            tab = {
                "id": tid,
                "kind": "table",
                "num": num,
                "page": page_no,
                "caption": cap_text,
            }
            html = elem["content"].get("html")
            if html:
                tab["html"] = html
            if bbox_norm:
                tab["bbox"] = bbox_norm
                tab["bbox_source"] = "mineru:vlm"
                tab["bbox_confidence"] = "high"
            tables.append(tab)
    return tables


def iter_equations(cl: list, layout: dict) -> list[dict]:
    eqs: list[dict] = []
    seq = 0
    for page_idx, page_elems in enumerate(cl):
        for elem in page_elems:
            if elem.get("type") != "equation_interline":
                continue
            seq += 1
            page_no = page_idx + 1
            bbox = elem.get("bbox")
            bbox_norm = _norm_bbox_pts(bbox, layout, page_idx) if bbox else None
            raw = elem["content"].get("math_content", "") or ""
            eq = {
                "id": f"eq_{seq}",
                "page": page_no,
                "latex": clean_latex(raw),
                "latex_raw": raw,
            }
            if bbox_norm:
                eq["bbox"] = bbox_norm
            eqs.append(eq)
    return eqs


def _appendix_threshold(sections: list[dict]) -> int | None:
    """计算 "附录起始页" 阈值：任何 figure/table/equation 的 page > 此值视为附录。

    优先用 sections 里 `kind == "references"` 的 page_start —— 论文几乎总是把附录排在
    References 之后。若没识别到 references 章节（罕见），fallback 用最后一个非
    references 章节的 page_end。返回 None 表示无法判断（短文/无章节切分），
    此时所有条目 is_appendix=False。
    """
    refs = next((s for s in sections if s.get("kind") == "references"), None)
    if refs and refs.get("page_start") is not None:
        return refs["page_start"]
    non_refs = [s for s in sections if s.get("kind") != "references"]
    if non_refs:
        return max((s.get("page_end") or 0) for s in non_refs)
    return None


def _mark_appendix(items: list[dict], threshold: int | None) -> None:
    """按 threshold 给每条加 is_appendix 字段（in-place）。"""
    for it in items:
        page = it.get("page")
        it["is_appendix"] = bool(
            threshold is not None and page is not None and page > threshold
        )


def count_references(cl: list) -> int:
    found = False
    count = 0
    for page_elems in cl:
        for elem in page_elems:
            t = elem.get("type")
            if t == "title":
                title_text = _join_text(elem["content"].get("title_content", []))
                if re.search(r"references?|bibliography", title_text, re.IGNORECASE):
                    found = True
                elif found:
                    return count
            elif found and t == "list":
                items = elem["content"].get("list_items", []) or []
                count += len(items)
    return count


# --------------------------------------------------------------------------- #
# 高清裁图
# --------------------------------------------------------------------------- #


def crop_high_res(workdir: Path, captions_with_bbox: list[dict],
                  *, pad: float = 0.005) -> None:
    """对每个含 bbox 的 caption 从 pages/page-NN.png 裁出高清版到 figures/<id>.png。

    直接 PIL，不走 page_screenshot 的 hash8 命名（mineru 后端 bbox 稳定，无需防孤儿）。
    在 caption 上写入 high_res_crop_path 字段。
    """
    from PIL import Image
    pages_dir = workdir / "pages"
    figures_dir = workdir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    for c in captions_with_bbox:
        bbox = c.get("bbox")
        if not bbox:
            continue
        page = c["page"]
        candidates = (
            list(pages_dir.glob(f"page-{page}.png"))
            + list(pages_dir.glob(f"page-{page:02d}.png"))
            + list(pages_dir.glob(f"page-{page:03d}.png"))
        )
        if not candidates:
            continue
        with Image.open(candidates[0]) as im:
            W, H = im.size
            x, y, w, h = bbox
            x_p = max(0.0, x - pad)
            y_p = max(0.0, y - pad)
            x2_p = min(1.0, x + w + pad)
            y2_p = min(1.0, y + h + pad)
            box = (int(x_p * W), int(y_p * H), int(x2_p * W), int(y2_p * H))
            out_path = figures_dir / f"{c['id']}.png"
            im.crop(box).save(out_path)
            c["high_res_crop_path"] = str(out_path.relative_to(workdir))


# --------------------------------------------------------------------------- #
# 顶层组装
# --------------------------------------------------------------------------- #


def build_paper_meta(cl: list, layout: dict, *, source_pdf: str) -> dict:
    sections = iter_sections(cl)
    figures = iter_figures(cl, layout)
    tables = iter_tables(cl, layout)
    equations = iter_equations(cl, layout)
    threshold = _appendix_threshold(sections)
    for items in (figures, tables, equations):
        _mark_appendix(items, threshold)
    return {
        "schema_version": "0.1",
        "source_pdf": source_pdf,
        "title": extract_title(cl),
        "authors": extract_authors(cl),
        "venue": None,
        "year": None,
        "abstract": extract_abstract(cl),
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "equations": equations,
        "references_count": count_references(cl),
    }


def build_figures_index(cl: list, layout: dict, *,
                        source_pdf: str, n_pages: int,
                        page_renders: list[dict],
                        mineru_task_id: str | None = None) -> dict:
    figures = iter_figures(cl, layout)
    tables = iter_tables(cl, layout)
    threshold = _appendix_threshold(iter_sections(cl))
    for items in (figures, tables):
        _mark_appendix(items, threshold)
    captions: list[dict] = []
    for f in figures:
        captions.append(dict(f))  # shallow copy 防互改
    for t in tables:
        captions.append(dict(t))
    return {
        "schema_version": "0.1",
        "source_pdf": source_pdf,
        "n_pages": n_pages,
        "extract_backend": "mineru",
        "mineru_task_id": mineru_task_id,
        "captions": captions,
        "embedded_images": [],   # mineru 后端不再产 pdfimages 嵌入图
        "page_renders": page_renders,
    }


def write_outputs(unzipped_dir: Path, workdir: Path, *,
                  source_pdf: str,
                  page_renders: list[dict] | None = None,
                  mineru_task_id: str | None = None) -> tuple[Path, Path]:
    cl, layout = load_mineru_outputs(unzipped_dir)
    n_pages = len(layout.get("pdf_info", []))

    # 若调用方未提供 page_renders（CLI 测试场景），按 workdir/pages 现状收集
    if page_renders is None:
        page_renders = []
        pages_dir = workdir / "pages"
        if pages_dir.exists():
            for p in sorted(pages_dir.glob("page-*.png")):
                m = re.search(r"page-(\d+)\.png$", p.name)
                if m:
                    page_renders.append({
                        "page": int(m.group(1)),
                        "path": str(p.relative_to(workdir)),
                    })

    paper_meta = build_paper_meta(cl, layout, source_pdf=source_pdf)
    figures_index = build_figures_index(
        cl, layout, source_pdf=source_pdf, n_pages=n_pages,
        page_renders=page_renders, mineru_task_id=mineru_task_id,
    )

    # 高清裁图（同步 captions[].high_res_crop_path）
    if (workdir / "pages").exists():
        crop_high_res(workdir, figures_index["captions"])
        # paper_meta 里的 figures/tables 也同步裁图路径
        crop_paths = {c["id"]: c.get("high_res_crop_path")
                      for c in figures_index["captions"]}
        for lst in (paper_meta["figures"], paper_meta["tables"]):
            for item in lst:
                if item["id"] in crop_paths and crop_paths[item["id"]]:
                    item["high_res_crop_path"] = crop_paths[item["id"]]

    workdir.mkdir(parents=True, exist_ok=True)
    paper_meta_path = workdir / "paper_meta.json"
    figures_index_path = workdir / "figures_index.json"
    paper_meta_path.write_text(
        json.dumps(paper_meta, indent=2, ensure_ascii=False),
        encoding="utf-8")
    figures_index_path.write_text(
        json.dumps(figures_index, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return paper_meta_path, figures_index_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> None:
    p = argparse.ArgumentParser(description="MinerU output → paper2slides schema")
    p.add_argument("unzipped_dir", type=Path,
                   help="MinerU 任务下载并解压的目录（含 content_list_v2.json + layout.json）")
    p.add_argument("workdir", type=Path,
                   help="paper2slides 工作目录（写 paper_meta.json + figures_index.json + figures/）")
    p.add_argument("--source-pdf", default="(unknown)",
                   help="原始 PDF 路径（仅记录到产物，不读）")
    p.add_argument("--task-id", default=None,
                   help="MinerU task_id（写入 figures_index.mineru_task_id）")
    args = p.parse_args()

    pm, fi = write_outputs(
        args.unzipped_dir.resolve(),
        args.workdir.resolve(),
        source_pdf=args.source_pdf,
        mineru_task_id=args.task_id,
    )
    print(json.dumps({
        "paper_meta": str(pm),
        "figures_index": str(fi),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
