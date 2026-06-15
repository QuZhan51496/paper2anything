"""
lib/sectionize.py — Stage 2: 启发式章节切分

读 raw_text.txt（含页分隔），用正则识别已知章节标题，输出 paper_meta.json。

为什么用启发式：论文章节结构高度规律（Abstract / Introduction / Method / ...），
90% 用正则就够。剩 10% 边界 case 由 Claude 在 Stage 3 进入前修订。脚本快、稳定、
零 token，是合理的"前置过滤"。

输出 paper_meta.json：
  schema_version, source_pdf, title, authors, venue, year, abstract,
  sections: [{id, kind, title, page_start, page_end, text, subsections: []}],
  figures, tables, references_count

figures/tables 字段从 figures_index.json 拷过来，方便 Stage 3-4 单文件读完。

CLI:
    python -m scripts.lib.sectionize <workdir>
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# 设计取舍：避免误匹配的核心办法是"独词 + 行尾"过于宽松（如单独一行 "model"
# 会被当章节）。我们把识别分两类：
#
# 1) TOP_LEVEL_KEYWORDS — 不需要 numbering 也能识别（这些标题不容易在正文里独占一行）
# 2) NUMBERED_KEYWORDS  — 必须配带 numbering 前缀才匹配（"3 Method" / "3.1 Encoder ..."）
#
# 漏检比误检容易补：Stage 3 的 Claude 可以补上少量被漏掉的章节，但难以剔除大量误识别。

TOP_LEVEL_KEYWORDS: list[tuple[str, str]] = [
    (r"abstract",                                          "abstract"),
    (r"references?|bibliography",                          "references"),
    (r"acknowledg(?:e?ments?)",                            "other"),
    (r"appendix(?:\s+\w+)?|supplement(?:ary)?(?:\s+material)?", "other"),
]

# 注意：用 \s* 而不是 \s+，因为 pdfplumber 在某些字体下会把单词间空格吃掉
# （如 "Model Architecture" → "ModelArchitecture"），只在数字与文字间还保留空格。
NUMBERED_KEYWORDS: list[tuple[str, str]] = [
    (r"introduction",                                      "introduction"),
    (r"background(?:\s*and\s*motivation)?",                "background"),
    (r"preliminaries|notation",                            "background"),
    (r"related\s*work|prior\s*work",                       "related"),
    (r"method(?:s|ology)?|approach|"
     r"(?:model\s*)?architecture|proposed(?:\s*method)?|framework",
                                                           "method"),
    (r"why\s*self-?attention",                             "method"),
    (r"experiment(?:s|al\s*setup)?|evaluation|"
     r"implementation(?:\s*details?)?|training",           "experiment"),
    (r"results?|main\s*results?|findings",                 "result"),
    (r"analysis|ablation(?:\s*studies?|s)?",               "result"),
    (r"discussion|limitations?",                           "discussion"),
    (r"conclusion(?:s)?|summary|concluding\s*remarks",     "conclusion"),
]

# numbering 前缀：1 / 1. / 1.2 / 1.2. / I. / A.（论文常见三种）
NUMBERING = r"(?:\d+(?:\.\d+)*\.?|[IVXLCDM]+\.|[A-Z]\.)"

PAGE_HEADER_RE = re.compile(r"^=====\s*PAGE\s+(\d+)\s*=====\s*$", re.MULTILINE)


def split_pages(raw_text: str) -> list[tuple[int, str]]:
    """raw_text.txt → [(page_no, text), ...]"""
    parts = PAGE_HEADER_RE.split(raw_text)
    pages: list[tuple[int, str]] = []
    # split 结果：[before_first, page1_no, page1_text, page2_no, page2_text, ...]
    for i in range(1, len(parts), 2):
        pages.append((int(parts[i]), parts[i + 1]))
    return pages


def _build_pos_to_page(pages: list[tuple[int, str]]) -> list[int]:
    """构造一个数组 a，a[pos] = pos 处所在的页号（基于 join("\\n") 后的位置）。"""
    out: list[int] = []
    for pno, t in pages:
        out.extend([pno] * (len(t) + 1))  # +1 for the "\n" join
    return out


def detect_sections(pages: list[tuple[int, str]]) -> list[dict]:
    raw = "\n".join(t for _, t in pages)
    pos_page = _build_pos_to_page(pages)

    found: list[dict] = []

    # 1) Top-level: 无 numbering 也匹配（abstract / references / appendix / acks）
    for keyword_pat, kind in TOP_LEVEL_KEYWORDS:
        pat = re.compile(rf"^[ \t]*(?:{keyword_pat})\s*$",
                         re.IGNORECASE | re.MULTILINE)
        for m in pat.finditer(raw):
            pos = m.start()
            page = pos_page[pos] if pos < len(pos_page) else pages[-1][0]
            found.append({"kind": kind, "title": m.group(0).strip(),
                          "page_start": page, "char_start": pos})

    # 2) Numbered: 必须配 numbering 前缀，关键词后允许跟最多 4 个补充词
    #    （如 "3 Model Architecture"、"6.1 Machine Translation"）
    for keyword_pat, kind in NUMBERED_KEYWORDS:
        pat = re.compile(
            rf"^[ \t]*{NUMBERING}[ \t]+(?:{keyword_pat})(?:[ \t]+\S+){{0,4}}\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        for m in pat.finditer(raw):
            pos = m.start()
            page = pos_page[pos] if pos < len(pos_page) else pages[-1][0]
            found.append({"kind": kind, "title": m.group(0).strip(),
                          "page_start": page, "char_start": pos})

    found.sort(key=lambda s: s["char_start"])

    # 去重位置非常接近的多个 hit（同一行被多个正则同时命中）
    deduped: list[dict] = []
    last_pos = -100
    for s in found:
        if s["char_start"] - last_pos < 5:
            continue
        deduped.append(s)
        last_pos = s["char_start"]

    # 子章节会引入同 kind 多条（如 "5 Training" + "5.1 ...")。短期：保留所有，
    # Stage 3 的 Claude 视情况合并/挑选。给 id 加递增序号区分。
    for i, s in enumerate(deduped):
        n = 1 + sum(1 for ss in deduped[:i] if ss["kind"] == s["kind"])
        s["id"] = f"{s['kind']}{'' if n == 1 else n}"
    return deduped


def fill_section_bodies(sections: list[dict],
                        full_text: str,
                        pages: list[tuple[int, str]]) -> list[dict]:
    pos_page = _build_pos_to_page(pages)
    end_of_doc = len(full_text)
    for i, s in enumerate(sections):
        end = (sections[i + 1]["char_start"]
               if i + 1 < len(sections) else end_of_doc)
        body = full_text[s["char_start"]:end]
        # 去掉首行（标题本身）
        body = body.split("\n", 1)[1] if "\n" in body else body
        # 剔除 PAGE 分隔行
        body = PAGE_HEADER_RE.sub("", body).strip()
        s["text"] = body
        s["page_end"] = (pos_page[end - 1]
                         if 0 < end <= len(pos_page) else s["page_start"])
        s["subsections"] = []  # 短期不切子节
        del s["char_start"]
    return sections


def extract_title_authors(pages: list[tuple[int, str]]) -> tuple[str, list[str]]:
    """从首页粗略抽 title 与 authors。失败时返回 ("", [])，让 Claude 在 Stage 3 补。"""
    if not pages:
        return "", []
    first = pages[0][1]
    lines = [ln.strip() for ln in first.splitlines() if ln.strip()]
    title = lines[0] if lines else ""
    authors: list[str] = []
    for line in lines[1:6]:
        if any(tok in line.lower() for tok in (" and ", ",", "·", ";")):
            for raw in re.split(r",| and |·|;", line):
                a = raw.strip(" .*†‡§¶0123456789")
                if 2 < len(a) < 40 and not any(ch.isdigit() for ch in a):
                    authors.append(a)
            if authors:
                break
    return title, authors


def extract_abstract(pages: list[tuple[int, str]]) -> str:
    if not pages:
        return ""
    first = pages[0][1]
    m = re.search(r"(?im)^\s*abstract\s*[:\.]?\s*$", first)
    if not m:
        m = re.search(r"(?i)\babstract\s*[:.]\s", first)
        if not m:
            return ""
    rest = first[m.end():]
    stop = re.search(
        r"\n\s*(?:1\.\s*Introduction\b|^Introduction\b|Keywords|CCS Concepts)",
        rest, re.IGNORECASE | re.MULTILINE,
    )
    abstract = rest[: stop.start()] if stop else rest[:1500]
    return abstract.strip()


def estimate_references_count(sections: list[dict]) -> int:
    for s in sections:
        if s["kind"] == "references":
            t = s["text"]
            return max(
                len(re.findall(r"^\s*\[\d+\]", t, re.MULTILINE)),
                len(re.findall(r"^\s*\d+\.\s+\w", t, re.MULTILINE)),
            )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="paper2slides Stage 2: sectionize")
    p.add_argument("workdir", type=Path,
                   help="工作目录（含 raw_text.txt 与 figures_index.json）")
    args = p.parse_args()

    wd = args.workdir.resolve()
    raw = (wd / "raw_text.txt").read_text(encoding="utf-8")
    fi = json.loads((wd / "figures_index.json").read_text(encoding="utf-8"))

    pages = split_pages(raw)
    full_text = "\n".join(t for _, t in pages)

    sections = detect_sections(pages)
    sections = fill_section_bodies(sections, full_text, pages)

    title, authors = extract_title_authors(pages)
    abstract = extract_abstract(pages)
    refs_count = estimate_references_count(sections)

    figures = [dict(c) for c in fi.get("captions", []) if c["kind"] == "figure"]
    tables = [dict(c) for c in fi.get("captions", []) if c["kind"] == "table"]

    # 标 is_appendix：page > references.page_start 视为附录（详见 mineru_parser._appendix_threshold）
    refs = next((s for s in sections if s.get("kind") == "references"), None)
    threshold: int | None = None
    if refs and refs.get("page_start") is not None:
        threshold = refs["page_start"]
    elif sections:
        non_refs = [s for s in sections if s.get("kind") != "references"]
        if non_refs:
            threshold = max((s.get("page_end") or 0) for s in non_refs)
    for items in (figures, tables):
        for it in items:
            page = it.get("page")
            it["is_appendix"] = bool(
                threshold is not None and page is not None and page > threshold
            )

    meta = {
        "schema_version": "0.1",
        "source_pdf": fi.get("source_pdf", ""),
        "title": title,
        "authors": authors,
        "venue": None,
        "year": None,
        "abstract": abstract,
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "references_count": refs_count,
    }
    out = wd / "paper_meta.json"
    out.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    print(json.dumps({
        "stage": "sectionize",
        "n_sections": len(sections),
        "section_kinds": [s["kind"] for s in sections],
        "title": title[:100],
        "n_figures": len(meta["figures"]),
        "n_tables": len(meta["tables"]),
        "references_count": refs_count,
        "paper_meta_path": str(out),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
