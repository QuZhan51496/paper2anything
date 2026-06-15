"""
auto_outline.py — Build a structured digest of a paper from MinerU output.

Reads `parsed/mineru_raw.json` + `parsed/metadata.json` and produces a
compact `digest.json` that groups blocks by section heading, attaches each
figure/table to its nearest section, and exposes captions, list items, and
plain text. Claude then writes outline.json from this digest instead of
slogging through the full markdown.

Usage:
    python auto_outline.py --parsed-dir <parsed/> --output digest.json
"""
import argparse
import json
import os
import re


HEAD_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.+)$")
SPECIAL_HEADINGS = {
    "abstract", "introduction", "related work", "background",
    "method", "methods", "approach", "experiments", "experiment",
    "results", "evaluation", "discussion", "conclusion", "conclusions",
    "references", "acknowledgments", "acknowledgements", "appendix",
    "limitations", "ethics statement", "broader impact",
}
STOP_HEADINGS = {"references", "acknowledgments", "acknowledgements", "appendix"}


def _span_text(block):
    """Concatenate all span text in a leaf block (one with `lines`)."""
    out = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            t = span.get("content", "")
            if t:
                out.append(t)
    return "".join(out).strip()


def _walk_text(block):
    """Concatenate text from a block, recursing into nested `blocks` if any."""
    if "lines" in block:
        return _span_text(block)
    parts = []
    for sub in block.get("blocks", []):
        parts.append(_walk_text(sub))
    return " ".join(p for p in parts if p).strip()


def _classify_heading(text):
    """Return (level, normalized_text). level=1 for top, 2/3 for subsections."""
    text = text.strip()
    m = HEAD_PATTERN.match(text)
    if m:
        num, _ = m.group(1), m.group(2)
        level = num.count(".") + 1
        return level, text
    low = text.lower().strip(" :.")
    if low in SPECIAL_HEADINGS:
        return 1, text
    # Fallback: treat as section but lowest priority
    return 3, text


def _extract_figure(block):
    """Return (image_path, caption) or (None, None) if not extractable."""
    img_path = None
    caption_parts = []
    for sub in block.get("blocks", []):
        st = sub.get("type", "")
        if st == "image_body":
            for line in sub.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("image_path"):
                        img_path = span["image_path"]
        elif st in ("image_caption", "image_footnote"):
            caption_parts.append(_walk_text(sub))
    caption = " ".join(c for c in caption_parts if c).strip()
    return img_path, caption


def _extract_table(block):
    img_path = None
    html = None
    caption_parts = []
    for sub in block.get("blocks", []):
        st = sub.get("type", "")
        if st == "table_body":
            for line in sub.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("image_path") and not img_path:
                        img_path = span["image_path"]
                    if span.get("html") and not html:
                        html = span["html"]
        elif st in ("table_caption", "table_footnote"):
            caption_parts.append(_walk_text(sub))
    caption = " ".join(c for c in caption_parts if c).strip()
    return img_path, caption, html


def _extract_list(block):
    items = []
    for sub in block.get("blocks", []):
        t = _walk_text(sub)
        if t:
            items.append(t)
    return items


def _flat_content_text(value):
    """Extract text from MinerU's alternate flat/list JSON format."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(
            t for t in (_flat_content_text(item) for item in value) if t
        ).strip()
    if not isinstance(value, dict):
        return str(value).strip()
    if value.get("type") == "text" and value.get("content"):
        return str(value.get("content", "")).strip()
    parts = []
    for key in (
        "title_content",
        "paragraph_content",
        "item_content",
        "algorithm_caption",
        "algorithm_content",
        "image_caption",
        "chart_caption",
        "table_caption",
        "content",
        "math_content",
    ):
        if key in value:
            text = _flat_content_text(value.get(key))
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def _flat_caption(content, *keys):
    for key in keys:
        text = _flat_content_text((content or {}).get(key))
        if text:
            return text
    return ""


def _flat_image_path(content):
    source = (content or {}).get("image_source") or {}
    path = source.get("path") if isinstance(source, dict) else None
    return path or None


def _build_digest_from_flat_pages(raw, metadata):
    """Handle MinerU JSON shaped as pages -> flat typed blocks.

    Some MinerU exports use `{"pdf_info": ...}` while others return a top-level
    list of pages. The latter still carries enough block semantics for poster
    extraction, so normalize it here instead of failing.
    """
    metadata["n_pages"] = len(raw)
    sections = []
    figures = []
    tables = []
    current = None
    stopped = False
    fig_counter = 0
    tab_counter = 0

    def _flush():
        nonlocal current
        if current is not None:
            current["text"] = current["text"].strip()
            sections.append(current)
            current = None

    def _ensure_section(page_idx):
        nonlocal current
        if current is None:
            current = {
                "heading": "_preamble",
                "level": 0,
                "page_start": page_idx,
                "page_end": page_idx,
                "text": "",
                "lists": [],
                "figures": [],
                "tables": [],
            }
        current["page_end"] = page_idx

    for p_idx, page in enumerate(raw):
        blocks = page if isinstance(page, list) else []
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            t = blk.get("type")
            content = blk.get("content") if isinstance(blk.get("content"), dict) else {}

            if t == "title":
                heading_text = _flat_content_text(content.get("title_content"))
                if not heading_text:
                    continue
                level = int(content.get("level") or _classify_heading(heading_text)[0])
                norm = heading_text.strip()
                low = re.sub(r"^[\d\.\s]+", "", norm).lower().strip(" :.")
                if low in STOP_HEADINGS:
                    stopped = True
                    _flush()
                    continue
                _flush()
                stopped = False
                current = {
                    "heading": norm,
                    "level": level,
                    "page_start": p_idx,
                    "page_end": p_idx,
                    "text": "",
                    "lists": [],
                    "figures": [],
                    "tables": [],
                }
                continue

            if stopped or t in {"page_number", "page_footer", "page_footnote"}:
                continue

            _ensure_section(p_idx)

            if t == "paragraph":
                txt = _flat_content_text(content.get("paragraph_content"))
                if txt:
                    current["text"] += (" " if current["text"] else "") + txt
            elif t == "list":
                items = []
                for item in content.get("list_items", []) or []:
                    item_text = _flat_content_text(item.get("item_content"))
                    if item_text:
                        items.append(item_text)
                current["lists"].extend(items)
            elif t in {"image", "chart"}:
                img = _flat_image_path(content)
                cap = _flat_caption(content, "image_caption", "chart_caption")
                extra = content.get("content")
                if t == "chart" and isinstance(extra, str) and extra.strip():
                    cap = (cap + " " + extra.strip()).strip()
                if img:
                    fig_counter += 1
                    fid = f"fig{fig_counter}"
                    figures.append({
                        "id": fid,
                        "image_path": img,
                        "caption": cap,
                        "page": p_idx,
                        "section": current["heading"],
                    })
                    current["figures"].append(fid)
            elif t == "table":
                img = _flat_image_path(content)
                cap = _flat_caption(content, "table_caption")
                html = content.get("html")
                tab_counter += 1
                tid = f"tab{tab_counter}"
                tables.append({
                    "id": tid,
                    "image_path": img,
                    "caption": cap,
                    "html": (html[:2000] + "...") if html and len(html) > 2000 else html,
                    "page": p_idx,
                    "section": current["heading"],
                })
                current["tables"].append(tid)
            elif t == "algorithm":
                txt = _flat_content_text(content)
                if txt:
                    current["text"] += (" " if current["text"] else "") + txt
            elif t == "equation_interline":
                eq = _flat_content_text(content.get("math_content"))
                if eq:
                    current["text"] += f" $${eq}$$"

    _flush()
    sections = [s for s in sections if (
        s["text"] or s["lists"] or s["figures"] or s["tables"]
    )]
    return {
        "metadata": metadata,
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "assets": _build_asset_library(sections, figures, tables),
        "stats": {
            "n_sections": len(sections),
            "n_figures": len(figures),
            "n_tables": len(tables),
        },
    }


ROLE_KEYWORDS = (
    ("problem",      ("introduction", "motivation", "background", "problem",
                      "challenge")),
    ("contribution", ("contribution", "summary", "overview")),
    ("method",       ("method", "approach", "framework", "model",
                      "architecture", "design", "system", "construction",
                      "pipeline", "algorithm")),
    ("result",       ("experiment", "result", "evaluation", "analysis",
                      "ablation", "benchmark", "study", "performance")),
    ("takeaway",     ("conclusion", "discussion", "future")),
    ("limitation",   ("limitation",)),
)


_NUMBER_HINT = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*(?:%|percent|x|×|fps|ms|s\b|GB|MB|K|M|B)?\b"
    r"|\bSOTA\b|\bstate-of-the-art\b|\boutperform[s]?\b|\bimprov[a-z]+\b)",
    re.IGNORECASE,
)


def _classify_role(heading):
    low = re.sub(r"^[\d\.\s]+", "", str(heading or "")).lower().strip(" :.")
    for role, kws in ROLE_KEYWORDS:
        for kw in kws:
            if kw in low:
                return role
    return "other"


def _split_sentences(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    return [p.strip() for p in parts if p and len(p.strip()) > 8]


def _claim_priority(role, has_number):
    base = {
        "result": 5,
        "method": 4,
        "contribution": 4,
        "problem": 3,
        "takeaway": 3,
        "limitation": 2,
    }.get(role, 2)
    if has_number and role in {"result", "contribution"}:
        base = min(5, base + 1)
    return base


def _figure_priority(role, caption):
    cap = (caption or "").lower()
    base = {"method": 4, "result": 5, "problem": 3}.get(role, 3)
    if any(k in cap for k in ("pipeline", "framework", "architecture", "overview")):
        base = max(base, 4 if role != "result" else base)
    return min(5, base)


def _build_asset_library(sections, figures, tables):
    """Derive a typed, role-tagged asset list from a built digest.

    Backward compatible: this only adds a new `assets` field; existing
    `sections`, `figures`, `tables` arrays are untouched and existing
    callers (digest_to_outline.py, poster_agents.py) keep working.
    """
    assets = []
    next_id = 0

    def _next_id(prefix):
        nonlocal next_id
        next_id += 1
        return f"{prefix}{next_id}"

    figures_by_id = {f.get("id"): f for f in figures}
    tables_by_id = {t.get("id"): t for t in tables}

    for sec in sections:
        heading = sec.get("heading") or ""
        if heading.startswith("_"):
            continue
        role = _classify_role(heading)

        # Claims and metrics from prose: take the first ~3 informative sentences.
        sentences = _split_sentences(sec.get("text"))[:4]
        for sent in sentences:
            has_number = bool(_NUMBER_HINT.search(sent))
            kind = "metric" if has_number and role in {"result", "contribution"} else "claim"
            assets.append({
                "id": _next_id("a"),
                "type": kind,
                "role": role,
                "priority": _claim_priority(role, has_number),
                "text": sent,
                "source_section": heading,
            })

        # List items become bullet-style claims.
        for item in (sec.get("lists") or [])[:6]:
            has_number = bool(_NUMBER_HINT.search(item))
            assets.append({
                "id": _next_id("a"),
                "type": "metric" if has_number else "claim",
                "role": role,
                "priority": _claim_priority(role, has_number),
                "text": item,
                "source_section": heading,
            })

        # Figures attached to this section.
        for fig_id in sec.get("figures") or []:
            fig = figures_by_id.get(fig_id) or {}
            assets.append({
                "id": _next_id("a"),
                "type": "figure",
                "role": role,
                "priority": _figure_priority(role, fig.get("caption")),
                "text": fig.get("caption") or "",
                "source_section": heading,
                "figure_id": fig_id,
                "image_path": fig.get("image_path"),
            })

        # Tables attached to this section.
        for tab_id in sec.get("tables") or []:
            tab = tables_by_id.get(tab_id) or {}
            assets.append({
                "id": _next_id("a"),
                "type": "table",
                "role": role,
                "priority": _figure_priority(role, tab.get("caption")),
                "text": tab.get("caption") or "",
                "source_section": heading,
                "table_id": tab_id,
                "image_path": tab.get("image_path"),
            })

    # Sort by priority desc so consumers can `assets[:N]` to grab the strongest.
    assets.sort(key=lambda a: (-int(a.get("priority", 0)),
                               {"figure": 0, "table": 1, "metric": 2,
                                "claim": 3, "equation": 4}.get(a.get("type"), 5)))
    return assets


def build_digest(parsed_dir):
    raw_path = os.path.join(parsed_dir, "mineru_raw.json")
    meta_path = os.path.join(parsed_dir, "metadata.json")
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"mineru_raw.json not found in {parsed_dir}. "
                                f"Run parse_pdf.py with the mineru parser first.")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    metadata = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

    if isinstance(raw, list):
        return _build_digest_from_flat_pages(raw, metadata)

    pages = raw.get("pdf_info", [])
    metadata["n_pages"] = len(pages)

    sections = []
    figures = []
    tables = []

    current = None
    stopped = False  # set True after we see References — skip remainder
    fig_counter = 0
    tab_counter = 0

    def _flush():
        nonlocal current
        if current is not None:
            current["text"] = current["text"].strip()
            sections.append(current)
            current = None
    for p_idx, page in enumerate(pages):
        for blk in page.get("para_blocks", []):
            t = blk.get("type")

            if t == "title":
                heading_text = _walk_text(blk)
                if not heading_text:
                    continue
                level, norm = _classify_heading(heading_text)
                low = re.sub(r"^[\d\.\s]+", "", norm).lower().strip(" :.")
                if low in STOP_HEADINGS:
                    stopped = True
                    _flush()
                    continue
                _flush()
                stopped = False
                current = {
                    "heading": norm,
                    "level": level,
                    "page_start": p_idx,
                    "page_end": p_idx,
                    "text": "",
                    "lists": [],
                    "figures": [],
                    "tables": [],
                }
                continue

            if stopped:
                continue

            if current is None:
                # Pre-heading content (e.g. author block) — open a synthetic section
                current = {
                    "heading": "_preamble",
                    "level": 0,
                    "page_start": p_idx,
                    "page_end": p_idx,
                    "text": "",
                    "lists": [],
                    "figures": [],
                    "tables": [],
                }

            current["page_end"] = p_idx

            if t == "text":
                txt = _walk_text(blk)
                if txt:
                    current["text"] += (" " if current["text"] else "") + txt
            elif t == "list":
                items = _extract_list(blk)
                current["lists"].extend(items)
            elif t == "image":
                img, cap = _extract_figure(blk)
                if img:
                    fig_counter += 1
                    fid = f"fig{fig_counter}"
                    figures.append({
                        "id": fid,
                        "image_path": img,
                        "caption": cap,
                        "page": p_idx,
                        "section": current["heading"],
                    })
                    current["figures"].append(fid)
            elif t == "table":
                img, cap, html = _extract_table(blk)
                tab_counter += 1
                tid = f"tab{tab_counter}"
                tables.append({
                    "id": tid,
                    "image_path": img,
                    "caption": cap,
                    "html": (html[:2000] + "...") if html and len(html) > 2000 else html,
                    "page": p_idx,
                    "section": current["heading"],
                })
                current["tables"].append(tid)
            elif t == "interline_equation":
                eq = _walk_text(blk)
                if eq:
                    current["text"] += f" $${eq}$$"

    _flush()

    # Drop empty sections (heading-only with no content/figures/tables/lists)
    sections = [s for s in sections if (
        s["text"] or s["lists"] or s["figures"] or s["tables"]
    )]

    return {
        "metadata": metadata,
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "assets": _build_asset_library(sections, figures, tables),
        "stats": {
            "n_sections": len(sections),
            "n_figures": len(figures),
            "n_tables": len(tables),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="Build digest.json from MinerU output")
    ap.add_argument("--parsed-dir", required=True,
                    help="Directory containing mineru_raw.json + metadata.json")
    ap.add_argument("--output", required=True, help="Output digest.json path")
    args = ap.parse_args()

    digest = build_digest(args.parsed_dir)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(digest, f, indent=2, ensure_ascii=False)

    s = digest["stats"]
    print(f"Digest written to {args.output}")
    print(f"  sections : {s['n_sections']}")
    print(f"  figures  : {s['n_figures']}")
    print(f"  tables   : {s['n_tables']}")
    print(f"  assets   : {len(digest.get('assets') or [])}")
    print(f"  pages    : {digest['metadata'].get('n_pages')}")
    print(f"  title    : {digest['metadata'].get('title','')[:80]}")
    print()
    print("Section headings:")
    for sec in digest["sections"]:
        marker = "  " * (sec["level"] - 1 if sec["level"] >= 1 else 0)
        n_fig = len(sec["figures"])
        n_tab = len(sec["tables"])
        n_chars = len(sec["text"])
        extras = []
        if n_fig:
            extras.append(f"{n_fig} fig")
        if n_tab:
            extras.append(f"{n_tab} tab")
        if sec["lists"]:
            extras.append(f"{len(sec['lists'])} list")
        tag = f" [{', '.join(extras)}]" if extras else ""
        print(f"  {marker}- {sec['heading'][:70]} ({n_chars} chars){tag}")


if __name__ == "__main__":
    main()
