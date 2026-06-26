"""
mineru_parser.py — MinerU unzipped output → paper2slides schema

Input: the directory of a MinerU parse job after download and unzip (contains content_list_v2.json + layout.json)
Output:
  - paper_meta.json           (title / authors / abstract / sections / figures / tables / equations / references_count)
  - figures_index.json        (contains captions[].bbox and high_res_crop_path)
  - figures/<id>.png          (figure / table / equation cropped hi-res from pages/page-NN.png)

Design notes:
  - bbox source: figure / equation directly from content_list_v2[i].bbox; table paired
    from layout.json's para_blocks (by page + same-page order)
  - all coordinates normalized to 0..1 using layout.pdf_info[page].page_size = [W, H], top-origin
  - LaTeX cleaning: MinerU inserts stray spaces between letters ("A t t e n t i o n"), but the necessary spaces after control sequences must be preserved
  - subfigure merging: an image whose caption lacks "Figure N" is staged, then merged into subfigures when the next numbered caption appears
  - kind classification reuses sectionize.py's keyword table

CLI (offline test):
    python -m scripts.lib.mineru_parser <unzipped_dir> <workdir>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# reuse sectionize's keyword table to classify section titles into a kind
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
# Generic helpers
# --------------------------------------------------------------------------- #


def _join_text(items: list) -> str:
    """Join [{type:'text', content:'...'}, ...] into a single string."""
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
    """[x0, y0, x1, y1] (absolute pixels, top-origin) → [x, y, w, h] (0..1)."""
    W, H = _page_size(layout, page_idx)
    x0, y0, x1, y1 = bbox_pts
    return [
        round(x0 / W, 4),
        round(y0 / H, 4),
        round((x1 - x0) / W, 4),
        round((y1 - y0) / H, 4),
    ]


def _union_bbox(bboxes: list[list]) -> list:
    """Multiple [x, y, w, h] in 0..1 → their union [x, y, w, h]."""
    x0 = min(b[0] for b in bboxes)
    y0 = min(b[1] for b in bboxes)
    x1 = max(b[0] + b[2] for b in bboxes)
    y1 = max(b[1] + b[3] for b in bboxes)
    return [round(x0, 4), round(y0, 4),
            round(x1 - x0, 4), round(y1 - y0, 4)]


def clean_latex(s: str) -> str:
    r"""
    MinerU VLM inserts stray spaces between letters ("A t t e n t i o n" → "Attention").
    Only this single step is needed — what follows a LaTeX control sequence (e.g.
    \operatorname, \frac, \sqrt) is usually `{` or whitespace, which step 1 won't break.

    Don't try to auto-insert a space for `\word + letter`: a greedy quantifier +
    backtracking would split `\operatorname` into `\operatornam e` (the regex shortens
    its match to satisfy the trailing-letter condition).
    """
    if not s:
        return ""
    return re.sub(r'(?<=[A-Za-z])\s+(?=[A-Za-z])', '', s).strip()


def _classify_kind(title_text: str) -> str:
    """Reuse sectionize's keyword table to map a section title to a kind."""
    s = title_text.strip()
    # strip the numbering prefix
    s = re.sub(rf"^{NUMBERING}\s*", "", s, flags=re.IGNORECASE).strip().lower()
    # TOP_LEVEL (standalone word)
    for kw, kind in TOP_LEVEL_KEYWORDS:
        if re.fullmatch(rf"\s*(?:{kw})\s*", s, flags=re.IGNORECASE):
            return kind
    # NUMBERED (0-4 extra words allowed after the keyword)
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
# Metadata extraction
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


# Month names: a date line (e.g. "June 19, 2026"), split on commas and stripped of
# digits, leaves a month word behind that is easily mistaken for an author; exclude explicitly.
_MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}

# Titles such as IEEE membership grades fall out as standalone tokens after comma-splitting and are easily mistaken for authors; exclude explicitly.
_NON_AUTHOR = {
    "member", "senior member", "graduate student member", "student member",
    "associate member", "fellow", "senior fellow", "life fellow", "life member",
    "life senior member", "ieee", "ieee member", "ieee fellow", "acm",
}


def extract_authors(cl: list) -> list[str]:
    if not cl or not cl[0]:
        return []
    page0 = cl[0]
    # position right after the paper title
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
    # up to the abstract (if present)
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
    # superscript symbols (including U+2217 ∗, U+2020 †, U+2021 ‡, U+00A7 §, U+00B6 ¶, etc.)
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
            # mostly composed of letters plus spaces / hyphens / periods
            stripped = re.sub(r"[\s\-\.\']", "", cand)
            if not stripped.isalpha():
                continue
            if cand.lower() in _MONTHS or cand.lower() in _NON_AUTHOR:
                continue
            # each word of an author name should start with a capital or an initial ("J."); those with a lowercase-leading word are mostly abstract sentence fragments
            if not all(w[0].isupper() or re.fullmatch(r"[A-Z]\.?", w)
                       for w in cand.split() if w):
                continue
            # an author name has at least two parts, given + family; a single capitalized word is mostly an abstract sentence-opening word / acronym ("Recently"/"MAs")
            if len(cand.split()) < 2:
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
# Section splitting
# --------------------------------------------------------------------------- #


def _section_depth(title_text: str) -> int:
    """Section depth: "3"→1, "3.1"→2; Roman-numeral section numbers (IEEE style
    "II. System Model")→1; unnumbered→0. A letter subsection number ("A. ...") does
    not count as top-level and still returns 0."""
    s = title_text.strip()
    m = re.match(r"^(\d+(?:\.\d+)*)", s)
    if m:
        return m.group(1).count(".") + 1
    if re.match(r"^[IVX]+[.)\s]", s):
        return 1
    return 0


def iter_sections(cl: list) -> list[dict]:
    flat: list[tuple[int, dict]] = []
    for page_idx, page_elems in enumerate(cl):
        for elem in page_elems:
            flat.append((page_idx, elem))

    # pick titles as split points:
    #   - depth >= 2 treated as a subsection, skip (subsections not split for now)
    #   - depth == 0 and kind == "other" treated as the paper title or license/watermark junk, skip
    #   - everything else kept as a top-level section
    titles: list[tuple[int, str]] = []
    for i, (_, elem) in enumerate(flat):
        if elem.get("type") != "title":
            continue
        # vlm marks the paper title as level 1 and section headings of all levels as
        # level 2; older output may mark subsections as 1 too. Accept both 1 and 2 as
        # split candidates; the paper title is filtered out below by depth==0 & kind==other.
        if elem.get("content", {}).get("level") not in (1, 2):
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
    bbox is always taken from layout.json/pdf_info[].para_blocks[type='image'], paired
    in same-page order. Do **not** use content_list_v2's elem['bbox'] — in practice its
    coordinate system does not match layout.page_size (the former is likely render /
    scaled coordinates), and normalizing with page_size would crop the figure at the
    wrong place. The table path already does it this way; this aligns with it.
    """
    # pre-aggregate the image / chart block bbox of each layout page: vlm marks plots like
    # line charts / heatmaps as type=='chart' and photos / schematics as type=='image';
    # both are paper figures. Do **not** sort — para_blocks is already in reading order
    # (left→right, top→bottom), consistent with content_list_v2's element order; forcing a
    # sort by top would pair the left/right relationship of multiple same-page subfigures
    # in reverse. Pool by kind, and each draws from its own pool when pairing.
    pools: dict[str, dict[int, list[list]]] = {"image": {}, "chart": {}}
    for page_idx, page_layout in enumerate(layout.get("pdf_info", [])):
        for blk in page_layout.get("para_blocks", []):
            bt = blk.get("type")
            if bt in ("image", "chart"):
                pools[bt].setdefault(page_idx, []).append(blk["bbox"])

    consumed: dict[tuple, int] = {}
    figures: list[dict] = []
    staging: list[dict] = []  # images with an unnumbered caption, held until the next numbered one to merge

    def _bbox_for(kind: str, page_idx: int):
        avail = pools[kind].get(page_idx, [])
        i = consumed.get((kind, page_idx), 0)
        if i >= len(avail):
            return None
        consumed[(kind, page_idx)] = i + 1
        return _norm_bbox_pts(avail[i], layout, page_idx)

    for page_idx, page_elems in enumerate(cl):
        for elem in page_elems:
            etype = elem.get("type")
            if etype not in ("image", "chart"):
                continue
            cap_field = "image_caption" if etype == "image" else "chart_caption"
            cap_text = _join_text(elem["content"].get(cap_field, []))
            page_no = page_idx + 1
            bbox = _bbox_for(etype, page_idx)

            m = re.search(r"Fig(?:ure)?\.?\s*(\d+)", cap_text, re.IGNORECASE)
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
                    # multiple subfigures: the current image is itself one subfigure of the
                    # figure (not the "main figure"). bbox is the union of all subfigures;
                    # subfigures fully lists the precise bounds of each one so Stage 3 can
                    # crop them individually as needed.
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
                    # single subfigure (no preceding unnumbered caption): bbox uses the current one directly
                    if bbox:
                        fig["bbox"] = bbox
                        fig["bbox_source"] = "mineru:vlm"
                        fig["bbox_confidence"] = "high"
                figures.append(fig)
            else:
                staging.append({"page": page_no, "bbox": bbox, "caption": cap_text})

    # staging still has leftovers at the end: each becomes its own figure. Drop those with
    # no caption and a tiny area — these are mostly parse noise (QED / marker-symbol
    # fragments, pixel-level remnants); keeping them only makes Stage 3 crop blanks.
    idx = 0
    for s in staging:
        bb = s.get("bbox")
        area = bb[2] * bb[3] if bb else 0.0
        if not (s.get("caption") or "").strip() and area < 0.005:
            continue
        idx += 1
        fig = {
            "id": f"figure_unnamed_{idx}",
            "kind": "figure",
            "num": None,
            "page": s["page"],
            "caption": s["caption"],
        }
        if bb:
            fig["bbox"] = bb
            fig["bbox_source"] = "mineru:vlm"
            fig["bbox_confidence"] = "medium"
        figures.append(fig)
    return figures


def iter_tables(cl: list, layout: dict) -> list[dict]:
    # pre-aggregate the table bbox of each layout page. para_blocks is already in reading order, no reordering needed.
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
    """Compute the "appendix start page" threshold: any figure/table/equation whose page > this value is treated as appendix.

    Prefer the page_start of the `kind == "references"` section in sections — a paper
    almost always places the appendix after References. If no references section is
    detected (rare), fall back to the page_end of the last non-references section.
    Returns None when it cannot be determined (short paper / no section split), in which
    case every item gets is_appendix=False.
    """
    refs = next((s for s in sections if s.get("kind") == "references"), None)
    if refs and refs.get("page_start") is not None:
        return refs["page_start"]
    non_refs = [s for s in sections if s.get("kind") != "references"]
    if non_refs:
        return max((s.get("page_end") or 0) for s in non_refs)
    return None


def _mark_appendix(items: list[dict], threshold: int | None) -> None:
    """Add an is_appendix field to each item according to threshold (in-place)."""
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
# Hi-res cropping
# --------------------------------------------------------------------------- #


def crop_high_res(workdir: Path, captions_with_bbox: list[dict],
                  *, pad: float = 0.005) -> None:
    """For each caption that has a bbox, crop a hi-res version from pages/page-NN.png to figures/<id>.png.

    Use PIL directly, not page_screenshot's hash8 naming (the mineru backend bbox is
    stable, no orphan prevention needed). Write the high_res_crop_path field onto the
    caption.
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
# Top-level assembly
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
        captions.append(dict(f))  # shallow copy to prevent mutual mutation
    for t in tables:
        captions.append(dict(t))
    return {
        "schema_version": "0.1",
        "source_pdf": source_pdf,
        "n_pages": n_pages,
        "extract_backend": "mineru",
        "mineru_task_id": mineru_task_id,
        "captions": captions,
        "embedded_images": [],   # the mineru backend has no pdfimages embedded images (use page_renders / crops)
        "page_renders": page_renders,
    }


def write_outputs(unzipped_dir: Path, workdir: Path, *,
                  source_pdf: str,
                  page_renders: list[dict] | None = None,
                  mineru_task_id: str | None = None) -> tuple[Path, Path]:
    cl, layout = load_mineru_outputs(unzipped_dir)
    n_pages = len(layout.get("pdf_info", []))

    # if the caller didn't provide page_renders (CLI test scenario), collect from the current state of workdir/pages
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

    # hi-res cropping (syncs captions[].high_res_crop_path)
    if (workdir / "pages").exists():
        crop_high_res(workdir, figures_index["captions"])
        # the figures/tables in paper_meta also sync their crop paths
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
                   help="directory of the MinerU job after download and unzip (contains content_list_v2.json + layout.json)")
    p.add_argument("workdir", type=Path,
                   help="paper2slides work directory (writes paper_meta.json + figures_index.json + figures/)")
    p.add_argument("--source-pdf", default="(unknown)",
                   help="original PDF path (recorded into the output only, not read)")
    p.add_argument("--task-id", default=None,
                   help="MinerU task_id (written into figures_index.mineru_task_id)")
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
