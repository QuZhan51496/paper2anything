"""paper2html 机械能力库（解析 / 确定性抽取 / 图片 / QA）。

供 scripts/ 下的 stage 脚本调用：
  PDF/Markdown -> 解析 -> extract_manifest(闸门1:确定性事实)
                       -> [你亲手写 index.html] -> validate_site(闸门2:QA)
本库不含任何 HTML 渲染器——页面的设计与撰写由你在 SKILL.md 的创作步骤完成。
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .config import default_output_root
from .mineru_client import MineruClient, MineruClientLite


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
URL_RE = re.compile(r"https?://[^\s\]\)<>]+")
TABLE_RE = re.compile(r"(Table\s+\d+\s*:[^\n]+)\s*(<table.*?</table>)", re.IGNORECASE | re.DOTALL)


@dataclass
class Figure:
    file: str
    caption: str
    section: str
    role: str = "figure"
    exists: bool = False


@dataclass
class Claim:
    label: str
    description: str
    evidence: str


@dataclass
class TableBlock:
    caption: str
    html: str
    section: str
    image: str = ""
    page: int | None = None


@dataclass
class Links:
    paper: str = ""
    code: str = ""
    project: str = ""
    data: str = ""
    demo: str = ""
    video: str = ""


@dataclass
class PaperManifest:
    title: str
    authors: list[str]
    affiliations: list[str]
    abstract: str
    links: Links
    claims: list[Claim]
    figures: list[Figure]
    tables: list[TableBlock]
    method_components: list[dict[str, str]]
    bibtex: str
    source: str


@dataclass
class QAResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, object] = field(default_factory=dict)


def manifest_from_dict(data: dict) -> PaperManifest:
    """从 manifest.json(asdict 序列化) 重建 PaperManifest，供 stage 校验复用，无需重抽。"""
    return PaperManifest(
        title=data.get("title", ""),
        authors=list(data.get("authors", [])),
        affiliations=list(data.get("affiliations", [])),
        abstract=data.get("abstract", ""),
        links=Links(**data.get("links", {})),
        claims=[Claim(**c) for c in data.get("claims", [])],
        figures=[Figure(**f) for f in data.get("figures", [])],
        tables=[TableBlock(**t) for t in data.get("tables", [])],
        method_components=list(data.get("method_components", [])),
        bibtex=data.get("bibtex", ""),
        source=data.get("source", ""),
    )


def _load_or_parse_source(
    source: Path,
    output_dir: Path,
    use_lite: bool,
    reuse_parsed: bool,
) -> tuple[str, dict[str, str], Path | None]:
    if source.suffix.lower() in {".md", ".markdown"}:
        parsed_dir = _guess_parsed_dir(source)
        images = _collect_images(parsed_dir) if parsed_dir and parsed_dir.exists() else {}
        return source.read_text(encoding="utf-8"), images, parsed_dir

    if source.suffix.lower() != ".pdf":
        raise ValueError(f"Unsupported input type: {source.suffix}. Use a PDF or Markdown file.")

    output_parsed_dir = output_dir / "parsed"
    guessed_parsed_dir = _guess_parsed_dir(source)
    parsed_candidates = [output_parsed_dir]
    if guessed_parsed_dir and guessed_parsed_dir not in parsed_candidates:
        parsed_candidates.append(guessed_parsed_dir)

    if reuse_parsed:
        for parsed_dir in parsed_candidates:
            existing_md = parsed_dir / "full.md"
            if existing_md.exists():
                images = _collect_images(parsed_dir)
                return existing_md.read_text(encoding="utf-8"), images, parsed_dir

    parsed_dir = output_parsed_dir
    parsed_dir.mkdir(parents=True, exist_ok=True)

    client = MineruClientLite() if use_lite else MineruClient()
    result = client.parse_pdf(str(source), str(parsed_dir))
    return result["markdown"], result.get("images", {}), parsed_dir


def _guess_parsed_dir(source: Path) -> Path | None:
    candidates = [
        source.parent / "parsed",
        source.parent.parent / source.stem / "parsed",
        default_output_root(source) / source.stem / "parsed",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def normalize_markdown(markdown: str) -> str:
    """Apply conservative cleanup before extraction."""
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"https://github\.com/\s+", "https://github.com/", text)
    replacements = {
        "Englishto-German": "English-to-German",
        "Englishto-French": "English-to-French",
        "sequencealigned": "sequence-aligned",
        "attentionbased": "attention-based",
        "艁ukasz": "Lukasz",
        "鈭?": "",
        "鈥榤aking鈥?": "'making'",
        "鈥榠ts鈥?": "'its'",
        "0(1)": "O(1)",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


APPENDIX_HEADING_RE = re.compile(
    r"^#{1,6}\s+"
    r"(?:"
    r"(?:appendix|supplementary(?:\s+materials?)?|supplemental(?:\s+materials?)?|附\s*录|补充材料)\b"
    r"|(?:appendix\s+)?[A-H][\.\)]?\s+\S"  # lettered appendix sections like "A Implementation"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def _appendix_offset(markdown: str) -> int | None:
    """Return the byte offset where the appendix begins, or None if not detected.

    Conservative: a lettered "A ..." heading only counts when it appears in the
    later part of the document (likely a real appendix, not a body section).
    """
    best: int | None = None
    total = len(markdown)
    for match in APPENDIX_HEADING_RE.finditer(markdown):
        heading_line = match.group(0)
        lowered = heading_line.lower()
        is_keyword = any(
            kw in lowered for kw in ("appendix", "supplementary", "supplemental", "附录", "补充材料")
        )
        if is_keyword:
            return match.start()
        # Lettered section (A./B. ...): only trust it in the last 40% of the document.
        if match.start() >= total * 0.6:
            if best is None or match.start() < best:
                best = match.start()
    return best


def extract_manifest(
    markdown: str,
    source: Path,
    image_roots: list[Path],
    paper_url: str | None = None,
    code_url: str | None = None,
    parsed_dir: Path | None = None,
) -> PaperManifest:
    headings = _headings(markdown)
    title = _extract_title(markdown, source)
    author_block = _extract_author_block(markdown)
    authors = _extract_authors(author_block)
    affiliations = _extract_affiliations(author_block)
    abstract = _extract_section_text(markdown, "Abstract") or _lead_abstract(markdown)
    links = _extract_links(markdown, source, paper_url=paper_url, code_url=code_url)

    # Exclude appendix/supplementary content from figures/tables/claims/method by feeding
    # the extractors a body-only slice. Abstract/links use the full text (they're up front).
    cutoff = _appendix_offset(markdown)
    body = markdown[:cutoff] if cutoff else markdown
    body_headings = _headings(body) if cutoff else headings

    figures = _extract_figures(body, image_roots, body_headings)
    if cutoff and not figures:
        # Cutoff removed every figure -> likely a false positive; fall back to full text.
        print("[paper2html] appendix filter removed all figures; using full document instead.")
        body, body_headings = markdown, headings
        figures = _extract_figures(body, image_roots, body_headings)
    tables = _extract_tables(body, body_headings, parsed_dir=parsed_dir)
    claims = _extract_claims(body, body_headings)
    method_components = _extract_method_components(body)
    bibtex = _make_bibtex(title, authors, source)

    return PaperManifest(
        title=title,
        authors=authors,
        affiliations=affiliations,
        abstract=_clean_inline(abstract),
        links=links,
        claims=claims,
        figures=figures,
        tables=tables,
        method_components=method_components,
        bibtex=bibtex,
        source=str(source),
    )


def validate_site(html: str, output_dir: Path, manifest: PaperManifest) -> QAResult:
    # 闸门2：你亲手写完 index.html 后校验。结构错误(缺 doctype / 缺图 / 空链)记 error，
    # 内容保真(标题/图/表是否真进了页面)记 warning——只校验成品 HTML 本身。
    errors: list[str] = []
    warnings: list[str] = []

    if not html.lstrip().lower().startswith("<!doctype html>"):
        errors.append("HTML does not start with <!DOCTYPE html>.")
    if "</html>" not in html.lower():
        errors.append("HTML is missing </html>.")

    image_refs = sorted(set(re.findall(r'(?:src|href)="(images/[^"]+)"', html)))
    image_ref_occurrences = re.findall(r'(?:src|href)="(images/[^"]+)"', html)
    duplicate_image_refs = sorted({ref for ref in image_ref_occurrences if image_ref_occurrences.count(ref) > 1})
    missing_images = [ref for ref in image_refs if not (output_dir / ref).exists()]
    if missing_images:
        errors.append(f"Missing image files: {', '.join(missing_images)}")
    if duplicate_image_refs:
        warnings.append(f"Repeated image references: {', '.join(duplicate_image_refs)}")

    hash_links = re.findall(r'href="#"', html)
    if hash_links:
        errors.append(f"Found {len(hash_links)} empty href=\"#\" links.")

    if not manifest.links.paper:
        warnings.append("No paper link was detected.")
    if not manifest.links.code:
        warnings.append("No code link was detected.")
    if len(manifest.claims) < 3:
        warnings.append("Fewer than three impact claims were extracted.")
    if not manifest.figures:
        warnings.append("No figures were detected.")
    table_images = [table.image for table in manifest.tables if table.image]
    if manifest.tables and not table_images:
        warnings.append("No table screenshots were detected; results will use extracted HTML tables.")

    empty_alt = [
        tag
        for tag in re.findall(r"<img\b[^>]*>", html)
        if 'alt=""' in tag and 'aria-hidden="true"' not in tag
    ]
    if empty_alt:
        warnings.append(f"Found {len(empty_alt)} non-decorative images with empty alt text.")

    # 内容保真：确认 manifest 的关键事实真的进了你写的页面（漏了记 warning）。
    lower_html = html.lower()
    title_present = bool(manifest.title) and manifest.title.lower()[:40] in lower_html
    if manifest.title and not title_present:
        warnings.append("Paper title not found in the page.")
    figures_referenced = sum(1 for f in manifest.figures if f.file and f.file.lower() in lower_html)
    if manifest.figures and not figures_referenced:
        warnings.append("None of the extracted figures are referenced in the page.")
    def _table_referenced(t: TableBlock) -> bool:
        if t.image and t.image.lower() in lower_html:
            return True
        # 原生渲染的表（html-authoring.md 推荐做法）不贴截图：图注出现在页面即算引用。
        cap = (t.caption or "").strip().lower()
        return bool(cap) and cap[:30] in lower_html
    tables_referenced = sum(1 for t in manifest.tables if _table_referenced(t))
    if manifest.tables and not tables_referenced:
        warnings.append("None of the extracted result tables are referenced in the page.")

    checks = {
        "image_refs": image_refs,
        "image_ref_occurrences": len(image_ref_occurrences),
        "duplicate_image_refs": duplicate_image_refs,
        "missing_images": missing_images,
        "hash_links": len(hash_links),
        "claims": len(manifest.claims),
        "figures": len(manifest.figures),
        "tables": len(manifest.tables),
        "table_images": len(table_images),
        "html_chars": len(html),
        "title_present": title_present,
        "figures_referenced": figures_referenced,
        "tables_referenced": tables_referenced,
    }
    return QAResult(ok=not errors, errors=errors, warnings=warnings, checks=checks)


def render_qa_report(qa: QAResult, manifest: PaperManifest) -> str:
    lines = [
        "# Paper2HTML QA Report",
        "",
        f"Status: {'PASS' if qa.ok else 'FAIL'}",
        f"Title: {manifest.title}",
        "",
        "## Checks",
    ]
    for key, value in qa.checks.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Errors"])
    lines.extend([f"- {item}" for item in qa.errors] or ["- None"])

    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in qa.warnings] or ["- None"])

    lines.extend(["", "## Links"])
    for key, value in asdict(manifest.links).items():
        if value:
            lines.append(f"- {key}: {value}")

    return "\n".join(lines) + "\n"


def copy_manifest_images(
    manifest: PaperManifest,
    output_dir: Path,
    image_roots: list[Path],
    parsed_images: dict[str, str],
) -> set[str]:
    copied: set[str] = set()
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    parsed_by_name = {Path(path).name: Path(path) for path in parsed_images.values()}
    refs = [fig.file for fig in manifest.figures]
    refs.extend(table.image for table in manifest.tables if table.image)
    for file_ref in refs:
        src = _find_image_source(file_ref, image_roots, parsed_by_name)
        if not src or not src.exists():
            continue
        dst = output_dir / file_ref
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        copied.add(file_ref)
    return copied


def _candidate_image_roots(source: Path, output_dir: Path, images_dir: str | None) -> list[Path]:
    roots: list[Path] = []
    if images_dir:
        roots.append(Path(images_dir).resolve())
    roots.extend(
        [
            source.parent,
            source.parent / "images",
            source.parent / "parsed",
            source.parent / "parsed" / "images",
            output_dir,
            output_dir / "images",
            output_dir / "parsed",
            output_dir / "parsed" / "images",
        ]
    )
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def _find_image_source(file_ref: str, roots: list[Path], parsed_by_name: dict[str, Path]) -> Path | None:
    ref = Path(file_ref)
    if ref.name in parsed_by_name:
        return parsed_by_name[ref.name]
    for root in roots:
        candidates = [root / ref, root / ref.name]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return None


def _collect_images(root: Path) -> dict[str, str]:
    images = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
            images[path.name] = str(path)
    return images


def _headings(markdown: str) -> list[tuple[int, int, str]]:
    return [(match.start(), len(match.group(1)), _clean_inline(match.group(2))) for match in HEADING_RE.finditer(markdown)]


def _section_for_index(headings: list[tuple[int, int, str]], index: int) -> str:
    current = ""
    for pos, _level, title in headings:
        if pos <= index:
            current = title
        else:
            break
    return current


def _extract_title(markdown: str, source: Path) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", markdown, re.MULTILINE)
    if match:
        return _clean_inline(match.group(1))
    return source.stem


def _extract_author_block(markdown: str) -> str:
    title = re.search(r"^#\s+.+?\s*$", markdown, re.MULTILINE)
    abstract = re.search(r"^##\s+Abstract\s*$", markdown, re.MULTILINE | re.IGNORECASE)
    if not title or not abstract:
        return ""
    return markdown[title.end() : abstract.start()].strip()


def _extract_authors(author_block: str) -> list[str]:
    authors = []
    for raw in author_block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "provided proper attribution" in line.lower():
            continue
        # 含 4 位年份（19xx/20xx）的行是日期 / 投稿信息，不是作者——作者名不含年份。
        if re.search(r"\b(19|20)\d{2}\b", line):
            continue
        line = re.sub(r"\S+@\S+", "", line)
        for marker in ["Google Brain", "Google Research", "University of Toronto", "OpenAI", "DeepMind", "Stanford", "MIT"]:
            idx = line.find(marker)
            if idx > 0:
                line = line[:idx]
        line = "".join(ch for ch in line if ch not in "*\u2217\u2020\u2021")
        line = _clean_inline(line).strip(" ,-")
        if line and len(line.split()) <= 5 and line not in authors:
            authors.append(line)
    return authors[:16]


def _extract_affiliations(author_block: str) -> list[str]:
    known = [
        "Google Brain",
        "Google Research",
        "University of Toronto",
        "OpenAI",
        "DeepMind",
        "Stanford University",
        "MIT",
    ]
    found = []
    for item in known:
        if item in author_block and item not in found:
            found.append(item)
    return found


def _extract_section_text(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(markdown)
    return markdown[match.end() : end].strip()


def _first_paragraph(markdown: str) -> str:
    for block in markdown.split("\n\n"):
        text = block.strip()
        if text and not text.startswith("#") and not text.startswith("!"):
            return text
    return ""


def _lead_abstract(markdown: str) -> str:
    """Recover the abstract when the paper has no ``## Abstract`` heading.

    The abstract always precedes Section 1, so we scan the region before the
    first ``## `` section heading and pick the longest prose paragraph. Author /
    affiliation / contact lines living in that same region are short and lose to
    the real abstract. If nothing is abstract-length we return "" rather than
    fall back to the first paragraph (which would grab the author line); the
    empty slot is left for you to fill from the full text.
    """
    first_section = re.search(r"^##\s+", markdown, re.MULTILINE)
    head = markdown[: first_section.start()] if first_section else markdown[:4000]
    best = ""
    for block in head.split("\n\n"):
        text = block.strip()
        if not text or text.startswith("#") or text.startswith("!"):
            continue
        if len(text.split()) > len(best.split()):
            best = text
    return best if len(best.split()) >= 40 else ""


# 库 / 工具官网（pydata 等）常出现在 "Tools and Libraries" 节，不是论文自己的资源链接。
_TOOL_DOMAINS = (
    "pydata.org", "matplotlib.org", "numpy.org", "scipy.org", "scikit-learn.org",
    "pytorch.org", "tensorflow.org", "keras.io", "rdkit.org", "opencv.org",
    "python.org", "readthedocs.io", "huggingface.co/docs",
)
# data 链接要有明确的数据集信号，而非任何含 "data" 子串的 URL（如 py*data*.org）。
_DATA_SIGNALS = (
    "dataset", "zenodo.org", "figshare", "kaggle.com",
    "huggingface.co/datasets", "dryad", "osf.io", "/data/",
)
# code 链接要邻近"代码可得"信号才采纳 github URL，而非全文第一个 github——后者往往是
# 被引工具仓库（lm-eval-harness、nanochat 等），不是本文自己的代码。\bcode\b 用词边界避开
# encode/decode；不含 "code" 字样的纯引用条目（"A framework for…"）因此被正确跳过。
_CODE_SIGNAL_RE = re.compile(r"\bcode\b|\bimplementation\b|\brepositor", re.IGNORECASE)


def _clean_url(url: str) -> str:
    # 去 markdown 转义反斜杠 + 尾随标点：MinerU 把 URL 里的 _ 等转义成 \_，而反斜杠在 URL 中非法，
    # 留着会让带下划线的仓库链接（repo 名常含 _）404。反斜杠从不是合法 URL 字符，整串删安全。
    return url.replace("\\", "").rstrip(".,;")


def _extract_links(markdown: str, source: Path, paper_url: str | None, code_url: str | None) -> Links:
    cleaned = normalize_markdown(markdown)
    urls = [_clean_url(url) for url in URL_RE.findall(cleaned)]
    links = Links()

    if paper_url:
        links.paper = paper_url
    # Don't auto-guess the paper's own link from body URLs: those are almost always
    # cited papers / external resources, so any pick links to the wrong thing. There is
    # no reliable canonical-link heuristic — supply it via --paper-url, else leave empty.

    if code_url:
        links.code = code_url
    else:
        # 只采纳邻近出现"代码可得"信号的 github URL（与 data 链接需数据信号同理）。
        # 全文第一个 github 往往是被引工具仓库，裸抓必错；找不到带信号的就留空交兜底。
        for m in re.finditer(r"https?://[^\s)]*github\.com[^\s)]*", cleaned, re.IGNORECASE):
            window = cleaned[max(0, m.start() - 90):m.end() + 20]
            if _CODE_SIGNAL_RE.search(window):
                links.code = _clean_url(m.group(0))
                break

    for url in urls:
        lower = url.lower()
        if any(dom in lower for dom in _TOOL_DOMAINS):
            continue  # 库 / 工具官网不是论文的资源链接
        if not links.project and any(word in lower for word in ["github.io", "project", "demo"]):
            links.project = url
        if not links.data and any(word in lower for word in _DATA_SIGNALS):
            links.data = url
        if not links.video and any(word in lower for word in ["youtube", "youtu.be", "video"]):
            links.video = url
    return links


def _extract_figures(markdown: str, image_roots: list[Path], headings: list[tuple[int, int, str]]) -> list[Figure]:
    figures: list[Figure] = []
    lines = markdown.splitlines()
    offset = 0
    for idx, line in enumerate(lines):
        match = IMAGE_RE.search(line)
        if not match:
            offset += len(line) + 1
            continue
        file_ref = match.group(1).strip()
        if file_ref.startswith("http"):
            offset += len(line) + 1
            continue
        caption = ""
        for next_line in lines[idx + 1 : idx + 4]:
            text = next_line.strip()
            if text and not text.startswith("!") and not text.startswith("#"):
                caption = _clean_inline(text)
                break
        role = _infer_figure_role(caption)
        exists = any((root / file_ref).exists() or (root / Path(file_ref).name).exists() for root in image_roots)
        figures.append(
            Figure(
                file=file_ref,
                caption=caption or Path(file_ref).name,
                section=_section_for_index(headings, offset),
                role=role,
                exists=exists,
            )
        )
        offset += len(line) + 1
    return _dedupe_figures(figures)


def _infer_figure_role(caption: str) -> str:
    lower = caption.lower()
    if any(word in lower for word in ["architecture", "pipeline", "model"]):
        return "architecture"
    if any(word in lower for word in ["visualization", "example", "qualitative"]):
        return "qualitative"
    if any(word in lower for word in ["result", "comparison"]):
        return "result"
    return "figure"


def _dedupe_figures(figures: Iterable[Figure]) -> list[Figure]:
    seen = set()
    unique = []
    for fig in figures:
        if fig.file in seen:
            continue
        seen.add(fig.file)
        unique.append(fig)
    return unique


def _extract_tables(
    markdown: str,
    headings: list[tuple[int, int, str]],
    parsed_dir: Path | None = None,
) -> list[TableBlock]:
    tables: list[TableBlock] = []
    table_images = _extract_table_images(parsed_dir)
    for match in TABLE_RE.finditer(markdown):
        caption = _clean_inline(match.group(1))
        html = match.group(2).strip()
        image_info = _match_table_image(caption, table_images, len(tables))
        tables.append(
            TableBlock(
                caption=caption,
                html=html,
                section=_section_for_index(headings, match.start()),
                image=image_info.get("image", ""),
                page=image_info.get("page"),
            )
        )
    # MinerU usually renders result tables as images, so the markdown carries no
    # <table> pipe-tables for TABLE_RE to match and `tables` stays empty even though
    # the table crops exist. Fall back to the extracted images directly so the
    # results section isn't silently dropped.
    if not tables and table_images:
        for item in table_images:
            image = str(item.get("image", ""))
            if not image:
                continue
            tables.append(
                TableBlock(
                    caption=_clean_inline(str(item.get("caption", ""))) or "Table",
                    html="",
                    section="",
                    image=image,
                    page=item.get("page") if isinstance(item.get("page"), int) else None,
                )
            )
    return tables[:4]


def _extract_table_images(parsed_dir: Path | None) -> list[dict[str, object]]:
    if not parsed_dir or not parsed_dir.exists():
        return []
    content_files = sorted(parsed_dir.glob("*_content_list.json"))
    for path in content_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tables = []
        for item in data:
            if isinstance(item, dict) and item.get("type") == "table":
                image = item.get("img_path") or _nested_image_path(item)
                caption = _flatten_content(item.get("table_caption") or item.get("caption") or "")
                tables.append(
                    {
                        "caption": _clean_inline(caption),
                        "image": image or "",
                        "page": item.get("page_idx"),
                    }
                )
        if tables:
            return tables
    return []


def _match_table_image(caption: str, table_images: list[dict[str, object]], index: int) -> dict[str, object]:
    if not table_images:
        return {}
    number = _table_number(caption)
    if number:
        for item in table_images:
            if _table_number(str(item.get("caption", ""))) == number:
                return item
    if index < len(table_images):
        return table_images[index]
    return {}


def _table_number(caption: str) -> str:
    match = re.search(r"\bTable\s+(\d+)", caption, re.IGNORECASE)
    return match.group(1) if match else ""


def _nested_image_path(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    content = item.get("content")
    if isinstance(content, dict):
        source = content.get("image_source")
        if isinstance(source, dict):
            return str(source.get("path") or "")
    return ""


def _flatten_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flatten_content(item) for item in value if item is not None)
    if isinstance(value, dict):
        if "content" in value:
            return _flatten_content(value.get("content"))
        return " ".join(_flatten_content(item) for item in value.values())
    return ""


def _extract_claims(markdown: str, headings: list[tuple[int, int, str]]) -> list[Claim]:
    claims: list[Claim] = []
    text = _text_for_claims(markdown)
    # Domain-agnostic quantitative signals: percentages, x-factors, scores with units,
    # plain metrics, and big-O complexity. No field-specific (e.g. BLEU) hardcoding.
    patterns = [
        re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*[x×]\b", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*(?:hours?|days?|minutes?|seconds?|ms|GPUs?|TPUs?|FLOPs?|params?|parameters|points?|fps|tokens?/s)\b", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s+(?!(?:We|The|This|These|Our|In|As|For|To|It|Of|And|But|A|An)\b)[A-Z][A-Za-z][A-Za-z0-9\-]*\b"),  # number + metric/proper noun (e.g. "28.4 BLEU"); skip number + sentence word (e.g. "2026 We")
        re.compile(r"O\([^)]+\)", re.IGNORECASE),
    ]

    for sentence in _claim_sentences(text):
        clean_sentence = _clean_inline(sentence)
        matches = []
        for pattern in patterns:
            matches.extend(match.group(0) for match in pattern.finditer(clean_sentence))
        for label in _rank_claim_labels(matches, clean_sentence):
            _add_claim(
                claims,
                label=label,
                description=_limit_text(clean_sentence, 180),
                evidence=_section_for_index(headings, markdown.find(sentence)) or "paper text",
            )
        if len(claims) >= 6:
            break

    if len(claims) < 3:
        abstract = _extract_section_text(markdown, "Abstract")
        for pattern in patterns:
            for match in pattern.finditer(abstract):
                _add_claim(claims, match.group(0),
                           _limit_text(_clean_inline(abstract), 180), "Abstract")
                if len(claims) >= 3:
                    break
            if len(claims) >= 3:
                break
    return claims[:5]


def _claim_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    sentences = re.split(r"(?<!\d)[.!?]\s+", text)
    signal = re.compile(r"\b\d+(?:\.\d+)?\b|O\([^)]+\)", re.IGNORECASE)
    return [sentence.strip() for sentence in sentences if signal.search(sentence)]


def _rank_claim_labels(labels: list[str], sentence: str) -> list[str]:
    # Domain-agnostic ranking: prefer percentages / x-factors / units / complexity over
    # bare numbers, but never privilege any specific field's metric.
    ranked: list[str] = []
    priority_markers = ["%", "x", "×", "O(", "hour", "day", "fps", "param", "flop", "gpu", "tpu"]
    for marker in priority_markers:
        for label in labels:
            if marker.lower() in label.lower() and label not in ranked:
                ranked.append(label)
    for label in labels:
        if label not in ranked:
            ranked.append(label)
    normalized: list[str] = []
    for label in ranked:
        label = label.strip()
        if label and label not in normalized:
            normalized.append(label)
    return normalized[:2]


def _strip_markdown_structure(text: str) -> str:
    # Drop heading / image / structural lines so section titles ("## 2 Methods",
    # "## 1 Introduction"), image refs, and stray markdown (e.g. "# Contact: ...")
    # are never mined as claims. A heading like "1 Introduction" otherwise matches
    # the "<number> <ProperNoun>" metric pattern and surfaces as a bogus claim.
    return "\n".join(
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "!"))
    )


def _text_for_claims(markdown: str) -> str:
    # Pull from common result-bearing sections by generic name, then fall back to the
    # document head. Section names are matched leniently by _extract_section_text.
    chunks = [
        _extract_section_text(markdown, "Abstract"),
        _extract_section_text(markdown, "Introduction"),
        _extract_section_text(markdown, "Results"),
        _extract_section_text(markdown, "Experiments"),
        _extract_section_text(markdown, "Evaluation"),
        markdown[:12000],
    ]
    return _strip_markdown_structure("\n".join(chunk for chunk in chunks if chunk))


def _add_claim(claims: list[Claim], label: str, description: str, evidence: str) -> None:
    key = _claim_key(label)
    if any(_claim_key(claim.label) == key for claim in claims):
        return
    claims.append(Claim(label=label, description=description, evidence=evidence))


def _claim_key(label: str) -> str:
    # Normalize so a value and its percent variant collapse (e.g. "92.5" == "92.5%"),
    # while distinct units stay separate ("12 hours" != "12 layers").
    key = label.lower().strip().rstrip("%").strip()
    return key


def _extract_method_components(markdown: str) -> list[dict[str, str]]:
    components = []
    for match in re.finditer(r"^##+\s+(?:\d+(?:\.\d+)*)?\s*(.+?)\s*$", markdown, re.MULTILINE):
        title = _clean_inline(match.group(1))
        if not _is_method_heading(title):
            continue
        start = match.end()
        next_match = re.search(r"^##+\s+", markdown[start:], re.MULTILINE)
        end = start + next_match.start() if next_match else min(len(markdown), start + 900)
        paragraph = _first_paragraph(markdown[start:end])
        if paragraph:
            components.append({"name": title, "description": _limit_text(_clean_inline(paragraph), 210)})
        if len(components) >= 5:
            break
    return components


def _is_method_heading(title: str) -> bool:
    lower = title.lower()
    return any(
        word in lower
        for word in [
            "method", "approach", "model", "architecture", "framework", "system",
            "design", "algorithm", "training", "implementation", "pipeline", "network",
            "formulation", "preliminaries",
        ]
    )


def _make_bibtex(title: str, authors: list[str], source: Path) -> str:
    # Take the year only if the filename carries a standalone 4-digit year (an
    # arxiv-style id like 2606.19789 does not), else leave it empty. Emit @misc
    # (no venue) rather than hardcoding a journal — the publication venue is unknown.
    year_match = re.search(r"\b(19|20)\d{2}\b", source.stem)
    year = year_match.group(0) if year_match else ""
    key_author = "paper"
    if authors:
        key_author = re.sub(r"[^a-zA-Z0-9]", "", authors[0].split()[-1]).lower() or "paper"
    key_title = re.sub(r"[^a-zA-Z0-9]", "", title.split()[0]).lower() if title.split() else "project"
    key = f"{key_author}{year}{key_title}"
    author_field = " and ".join(authors) if authors else "Unknown"
    return "\n".join(
        [
            f"@misc{{{key},",
            f"  title={{{title}}},",
            f"  author={{{author_field}}},",
            f"  year={{{year}}}",
            "}",
        ]
    )


def _clean_inline(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _limit_text(text: str, limit: int) -> str:
    text = _clean_inline(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "..."
