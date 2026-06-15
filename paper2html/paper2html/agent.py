"""Paper2HTML Agent v2.

This module builds a more controllable paper project page pipeline:

input PDF/Markdown -> manifest/style references/site plan -> deterministic HTML -> QA report.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict, dataclass, field, fields
from html import escape
from pathlib import Path
from string import Template
from typing import Iterable
from urllib.parse import urlparse

import requests

from paper2html.config import default_output_root, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_REQUEST_TIMEOUT
from paper2html.mineru_client import MineruClient, MineruClientLite


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
URL_RE = re.compile(r"https?://[^\s\]\)<>]+")
TABLE_RE = re.compile(r"(Table\s+\d+\s*:[^\n]+)\s*(<table.*?</table>)", re.IGNORECASE | re.DOTALL)
ARXIV_ID_RE = re.compile(r"(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?")


STYLE_REFERENCES = [
    {
        "name": "Nerfies",
        "url": "https://nerfies.github.io/",
        "pattern": "centered academic hero, compact links, teaser before abstract, then video/results/BibTeX",
    },
    {
        "name": "DreamFusion",
        "url": "https://dreamfusion3d.github.io/",
        "pattern": "title/authors first, paper/project/gallery links, abstract early, examples and method below",
    },
    {
        "name": "3D Gaussian Splatting",
        "url": "https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/",
        "pattern": "publication-style header, resource links, abstract, video/evaluation/visual comparisons, BibTeX",
    },
    {
        "name": "Segment Anything",
        "url": "https://ai.meta.com/research/publications/segment-anything/",
        "pattern": "research publication hierarchy with date/topic, abstract, authors, paper link, related work",
    },
]

STYLE_CHOICES = ["classic", "visual", "technical", "minimal", "dark"]

PROJECT_PAGE_STYLE_RULES = [
    "Keep the first screen editorial and light: title, authors, affiliations, resource buttons.",
    "Show the primary figure once as a readable teaser instead of using it as a repeated background.",
    "Put the abstract immediately after the teaser, then claims, method, results, supporting figures, citation.",
    "Prefer paper-cropped table screenshots for results, because extracted table HTML often loses math and alignment.",
    "Use restrained cards only for repeated claims, story beats, tables, and figure items.",
    "Size figures by role: architecture figures get a large inspectable stage, method figures are secondary, galleries are capped.",
]


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
class SitePlan:
    mode: str
    theme: str
    accent: str
    sections: list[str]
    hero_visual: str
    primary_figure: str
    featured_figures: list[str]
    result_tables: list[str]
    interactive: str = ""


@dataclass
class ProjectBrief:
    audience: str
    goal: str
    style: str
    emphasis: list[str]
    narrative_angle: str
    hero_message: str
    teaser_heading: str
    table_mode: str = "auto"
    figure_strategy: str = "one-primary-figure"
    sections: list[str] = field(default_factory=list)
    ascii_wireframe: str = ""
    wireframe_source: str = "local"
    revision_history: list[str] = field(default_factory=list)
    notes: str = ""
    source_brief: str = ""
    confirmed: bool = False
    image_rotations: dict[str, int] = field(default_factory=dict)
    method: str = "inspect-ask-propose-revise-confirm-build-qa"


@dataclass
class QAResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, object] = field(default_factory=dict)


def build_agent_page(
    input_path: str,
    output_dir: str | None = None,
    images_dir: str | None = None,
    mode: str = "showcase",
    table_mode: str = "auto",
    brief: ProjectBrief | None = None,
    use_lite: bool = False,
    reuse_parsed: bool = True,
    paper_url: str | None = None,
    code_url: str | None = None,
    copy_images: bool = True,
    renderer: str = "template",
    rotate_spec: str | None = None,
    variant: int | None = None,
) -> dict[str, str]:
    """Run the agent pipeline and return generated artifact paths."""
    source = _resolve_existing_path(input_path)
    if not source.exists():
        raise FileNotFoundError(f"Input not found: {source}")
    if table_mode not in {"auto", "image", "html"}:
        raise ValueError("table_mode must be one of: auto, image, html")
    if renderer not in {"template", "llm"}:
        raise ValueError("renderer must be one of: template, llm")

    out_dir = Path(output_dir) if output_dir else default_output_root(source) / f"{source.stem}_agent"
    out_dir.mkdir(parents=True, exist_ok=True)

    markdown, parsed_images, parsed_dir = _load_or_parse_source(source, out_dir, use_lite=use_lite, reuse_parsed=reuse_parsed)
    markdown = normalize_markdown(markdown)

    image_roots = _candidate_image_roots(source, out_dir, images_dir)
    manifest = extract_manifest(
        markdown,
        source=source,
        image_roots=image_roots,
        paper_url=paper_url,
        code_url=code_url,
        parsed_dir=parsed_dir,
    )

    # Merge any CLI --rotate spec (figure-number based) into the brief's image_rotations.
    if rotate_spec:
        spec_rotations = _parse_rotate_spec(rotate_spec, manifest)
        if spec_rotations:
            if brief is None:
                brief = _default_brief(manifest, table_mode)
            brief.image_rotations.update(spec_rotations)

    if copy_images:
        copied = copy_manifest_images(manifest, out_dir, image_roots, parsed_images)
        for fig in manifest.figures:
            fig.exists = fig.file in copied or (out_dir / fig.file).exists()

    # Apply user-requested rotations to the copied images (never touches the source cache).
    if brief and brief.image_rotations:
        _apply_image_rotations(out_dir, brief.image_rotations)

    site_plan = plan_site(manifest, mode=mode, brief=brief)

    if renderer == "llm" and not _can_call_design_llm():
        print("[agent] LLM renderer unavailable (missing API config); falling back to template renderer.")
        renderer = "template"

    precomputed_qa: QAResult | None = None
    if renderer == "llm":
        html, precomputed_qa = _generate_llm_site_with_qa(
            manifest, site_plan, out_dir, table_mode=table_mode, brief=brief, variant_seed=variant
        )
    else:
        html = render_site(manifest, site_plan, table_mode=table_mode, brief=brief)

    html_path = out_dir / "index.html"
    clean_md_path = out_dir / "clean.md"
    manifest_path = out_dir / "manifest.json"
    plan_path = out_dir / "site_plan.json"
    style_reference_path = out_dir / "style_reference.json"
    brief_path = out_dir / "project_brief.json"
    validation_path = out_dir / "validation.json"
    qa_path = out_dir / "qa_report.md"

    html_path.write_text(html, encoding="utf-8")
    clean_md_path.write_text(markdown, encoding="utf-8")
    manifest_path.write_text(_json_dumps(asdict(manifest)), encoding="utf-8")
    plan_path.write_text(_json_dumps(asdict(site_plan)), encoding="utf-8")
    style_reference_path.write_text(
        _json_dumps(
            {
                "references": STYLE_REFERENCES,
                "rules": PROJECT_PAGE_STYLE_RULES,
                "table_mode": table_mode,
                "renderer": renderer,
                "agent_method": "inspect-ask-propose-revise-confirm-build-qa",
            }
        ),
        encoding="utf-8",
    )
    if brief:
        _refresh_wireframe(brief, manifest)
        brief_path.write_text(_json_dumps(asdict(brief)), encoding="utf-8")

    qa = precomputed_qa if precomputed_qa is not None else validate_site(html, out_dir, manifest, brief=brief, plan=site_plan)
    validation_path.write_text(_json_dumps(asdict(qa)), encoding="utf-8")
    qa_path.write_text(render_qa_report(qa, manifest, site_plan), encoding="utf-8")

    return {
        "html": str(html_path),
        "markdown": str(clean_md_path),
        "manifest": str(manifest_path),
        "site_plan": str(plan_path),
        "style_reference": str(style_reference_path),
        "project_brief": str(brief_path) if brief else "",
        "validation": str(validation_path),
        "qa_report": str(qa_path),
    }


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
        default_output_root(source) / f"{source.stem}_agent" / "parsed",
        default_output_root(source) / source.stem / "parsed",
        default_output_root(source) / source.stem.replace("_agent", "") / "parsed",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def normalize_markdown(markdown: str) -> str:
    """Apply conservative cleanup before extraction."""
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"https://github\.com/\s+", "https://github.com/", text)
    text = re.sub(r"https://arxiv\.org/\s+", "https://arxiv.org/", text)
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
    abstract = _extract_section_text(markdown, "Abstract") or _first_paragraph(markdown)
    links = _extract_links(markdown, source, paper_url=paper_url, code_url=code_url)

    # Exclude appendix/supplementary content from figures/tables/claims/method by feeding
    # the extractors a body-only slice. Abstract/links use the full text (they're up front).
    cutoff = _appendix_offset(markdown)
    body = markdown[:cutoff] if cutoff else markdown
    body_headings = _headings(body) if cutoff else headings

    figures = _extract_figures(body, image_roots, body_headings)
    if cutoff and not figures:
        # Cutoff removed every figure -> likely a false positive; fall back to full text.
        print("[agent] appendix filter removed all figures; using full document instead.")
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


def plan_site(manifest: PaperManifest, mode: str = "showcase", brief: ProjectBrief | None = None) -> SitePlan:
    text = f"{manifest.title} {manifest.abstract}".lower()
    interactive = ""
    if any(word in text for word in ["image", "vision", "render", "video", "diffusion", "3d", "segmentation"]):
        theme = "vision-showcase"
        accent = "#7c3aed"
    else:
        theme = "classic-research"
        accent = "#1f6feb"

    if brief:
        if brief.style == "classic":
            theme = "classic-paper-project"
            accent = "#0f766e"
        elif brief.style == "visual":
            theme = "vision-showcase"
            accent = "#7c3aed"
        elif brief.style == "technical":
            theme = "technical-reader"
            accent = "#1f6feb"
        elif brief.style == "minimal":
            theme = "minimal-paper"
            accent = "#334155"
        elif brief.style == "dark":
            theme = "dark-paper-showcase"
            accent = "#8b5cf6"
        brief_text = _brief_text(brief)
        if any(word in brief_text for word in ["green", "forest", "绿色", "绿"]):
            theme = "green-academic-promo"
            accent = "#16a34a"
        if any(word in brief_text for word in ["promotional", "promotion", "宣传"]):
            theme = theme.replace("vision-showcase", "green-academic-promo")

    primary = _choose_primary_figure(manifest.figures)
    method_figure = _choose_method_figure(manifest.figures, primary)
    featured = [fig.file for fig in manifest.figures if fig.file not in {primary, method_figure}][:4]
    result_tables = [table.caption for table in manifest.tables[:4]]
    sections = ["hero", "teaser", "abstract", "impact", "story", "method", "results", "gallery", "bibtex"]
    if brief and _should_render_promo_site(brief):
        sections = ["hero", "abstract", "architecture", "idea", "results", "why", "bibtex"]
        table2 = [table.caption for table in manifest.tables if "Table 2" in table.caption]
        result_tables = table2[:1] or result_tables[:1]
        interactive = ""
    if interactive:
        sections.insert(6, "interactive")

    return SitePlan(
        mode=mode,
        theme=theme,
        accent=accent,
        sections=sections,
        hero_visual="centered_project_hero" if primary else "centered_text_hero",
        primary_figure=primary,
        featured_figures=([method_figure] if method_figure else []) + featured,
        result_tables=result_tables,
        interactive=interactive,
    )


def render_site(
    manifest: PaperManifest,
    plan: SitePlan,
    table_mode: str = "auto",
    brief: ProjectBrief | None = None,
) -> str:
    if brief and _should_render_promo_site(brief):
        return _render_promotional_site(manifest, plan, table_mode=table_mode, brief=brief)

    title = escape(manifest.title)
    tagline = brief.hero_message if brief and brief.hero_message else _make_tagline(manifest)
    author_html = _render_authors(manifest)
    link_html = _render_links(manifest.links)
    claims_html = _render_claims(manifest.claims)
    story_html = _render_story(manifest, plan, brief=brief)
    teaser_html = _render_teaser(manifest, plan, brief=brief)
    method_html = _render_method(manifest, plan, brief=brief)
    interactive_html = _render_interactive(plan)
    results_html = _render_results(manifest, table_mode=table_mode, brief=brief)
    gallery_html = _render_gallery(manifest, plan)
    retrospective_html = _render_retrospective(manifest, brief)
    bibtex_html = escape(manifest.bibtex)
    abstract = escape(_limit_text(manifest.abstract, 950))
    body_class = ' class="theme-dark"' if brief and brief.style == "dark" else ""

    template = Template(
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>$title</title>
  <meta name="description" content="$description" />
  <script>
    window.MathJax = {
      tex: { inlineMath: [['\\\\(', '\\\\)']], displayMath: [['\\\\[', '\\\\]']] },
      svg: { fontCache: 'global' }
    };
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
  <style>
    :root {
      --accent: $accent;
      --accent-2: #c2410c;
      --ink: #111827;
      --muted: #5f6878;
      --soft: #eef7f5;
      --paper: #ffffff;
      --line: rgba(17, 24, 39, 0.12);
      --bg: #f8fafc;
      --warm: #fff7ed;
      --radius: 8px;
      --max: 1120px;
      --content: 920px;
    }
    body.theme-dark {
      --accent: $accent;
      --accent-2: #22d3ee;
      --ink: #f8fafc;
      --muted: #aab4c5;
      --soft: rgba(139, 92, 246, 0.16);
      --paper: #121826;
      --line: rgba(226, 232, 240, 0.16);
      --bg: #070b13;
      --warm: rgba(34, 211, 238, 0.12);
    }
    body.theme-dark .figure-stage,
    body.theme-dark .figure-card,
    body.theme-dark .table-shell,
    body.theme-dark .panel,
    body.theme-dark .impact-card,
    body.theme-dark .story-card,
    body.theme-dark .section-item {
      box-shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
    }
    body.theme-dark .figure-stage {
      background: #0d1320;
    }
    body.theme-dark .btn.primary {
      color: #ffffff;
    }
    body.theme-dark .bibtex pre {
      background: #050812;
      color: #c7d2fe;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; scroll-padding-top: 82px; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.6;
      overflow-x: hidden;
    }
    a { color: inherit; text-decoration: none; }
    .nav {
      position: sticky;
      top: 0;
      z-index: 20;
      background: color-mix(in srgb, var(--paper) 88%, transparent);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--line);
    }
    .nav-inner {
      max-width: var(--max);
      margin: 0 auto;
      padding: 12px 22px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 18px;
    }
    .brand { font-weight: 800; letter-spacing: 0; }
    .nav-links { display: flex; gap: 14px; flex-wrap: wrap; color: var(--muted); font-size: 14px; }
    .nav-links a:hover { color: var(--accent); }
    .hero {
      position: relative;
      display: grid;
      place-items: center;
      overflow: hidden;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--accent) 16%, transparent), transparent 64%),
        var(--paper);
    }
    .hero-inner {
      position: relative;
      z-index: 1;
      width: min(var(--content), calc(100% - 44px));
      margin: 0 auto;
      padding: 52px 0 40px;
      color: var(--ink);
      text-align: center;
    }
    .kicker {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    h1 {
      max-width: 980px;
      margin: 14px auto 14px;
      font-size: clamp(42px, 6.2vw, 76px);
      line-height: 1.03;
      letter-spacing: 0;
      overflow-wrap: anywhere;
    }
    .tagline {
      max-width: 760px;
      font-size: clamp(17px, 2vw, 23px);
      color: var(--muted);
      margin: 0 auto 20px;
      overflow-wrap: break-word;
    }
    .authors {
      display: flex;
      flex-wrap: wrap;
      gap: 4px 10px;
      margin: 18px auto 8px;
      min-width: 0;
      max-width: 100%;
      justify-content: center;
    }
    .author-chip, .affiliation-chip {
      min-width: 0;
      max-width: 100%;
      flex: 0 1 auto;
      color: var(--muted);
      font-size: 14px;
      white-space: normal;
      overflow-wrap: anywhere;
    }
    .author-chip { color: var(--ink); font-weight: 700; }
    .author-chip:not(:last-child)::after, .affiliation-chip:not(:last-child)::after {
      content: ",";
      color: var(--muted);
      font-weight: 400;
    }
    .affiliations { display: flex; gap: 4px 10px; flex-wrap: wrap; margin: 0 auto 22px; min-width: 0; max-width: 100%; justify-content: center; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; min-width: 0; max-width: 100%; justify-content: center; }
    .btn {
      display: inline-flex;
      align-items: center;
      min-height: 42px;
      padding: 0 16px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: var(--paper);
      color: var(--ink);
      font-weight: 800;
    }
    .btn.primary { background: var(--accent); border-color: var(--accent); color: white; }
    .style-note {
      max-width: var(--content);
      margin: 16px auto 0;
      color: var(--muted);
      font-size: 12px;
      text-align: center;
    }
    main { max-width: var(--max); margin: 0 auto; padding: 36px 22px 92px; }
    section { margin: 0 0 66px; }
    .section-head { max-width: 780px; margin-bottom: 24px; }
    .eyebrow {
      color: var(--accent);
      font-size: 13px;
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    h2 {
      max-width: 100%;
      margin: 8px 0 12px;
      font-size: clamp(28px, 4.5vw, 48px);
      line-height: 1.05;
      letter-spacing: 0;
      overflow-wrap: break-word;
    }
    .lead { color: var(--muted); font-size: 18px; max-width: 760px; overflow-wrap: break-word; }
    .teaser {
      margin-bottom: 58px;
    }
    .teaser .section-head {
      max-width: var(--content);
      margin-left: auto;
      margin-right: auto;
      text-align: center;
    }
    .story-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
    .story-card {
      padding: 22px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 14px 36px rgba(15, 23, 42, 0.06);
    }
    .story-step {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: var(--soft);
      color: var(--accent);
      font-weight: 900;
      margin-bottom: 14px;
    }
    .story-card h3 { margin: 0 0 8px; font-size: 18px; }
    .story-card p { margin: 0; color: var(--muted); }
    .impact-grid, .section-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }
    .impact-card, .panel, .figure-card, .table-shell, .bibtex, .section-item {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 14px 36px rgba(15, 23, 42, 0.06);
    }
    .impact-card { padding: 20px; min-height: 178px; }
    .impact-label { font-size: 32px; line-height: 1; font-weight: 900; color: var(--accent); }
    .impact-text { margin-top: 12px; color: var(--muted); font-size: 14px; }
    .impact-evidence { margin-top: 12px; color: var(--accent); font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.06em; }
    .section-item { padding: 18px; }
    .section-item strong { display: block; margin-bottom: 6px; }
    .section-item span { color: var(--muted); font-size: 14px; }
    .figure-card { overflow: hidden; margin: 0; }
    .figure-card img { display: block; width: 100%; height: auto; background: #f2f4f7; }
    .figure-stage {
      background: color-mix(in srgb, var(--paper) 88%, #ffffff 12%);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
      padding: clamp(16px, 3vw, 34px);
    }
    .figure-stage .figure-card {
      box-shadow: none;
      border: 0;
      border-radius: 0;
    }
    .figure-wide img {
      width: auto;
      max-width: 100%;
      max-height: 740px;
      object-fit: contain;
      padding: 0;
      margin: 0 auto;
      background: #ffffff;
    }
    .method-figure img {
      height: 420px;
      object-fit: contain;
      padding: 18px;
      background: #ffffff;
    }
    .gallery .figure-card img {
      height: 260px;
      object-fit: contain;
      padding: 14px;
      background: #ffffff;
    }
    figcaption { padding: 12px 14px; color: var(--muted); font-size: 14px; border-top: 1px solid var(--line); }
    .method-grid { display: grid; grid-template-columns: minmax(0, 0.88fr) minmax(360px, 1.12fr); gap: 18px; align-items: start; }
    .panel { padding: 22px; }
    .component-list { display: grid; gap: 10px; margin-top: 18px; }
    .component { padding-top: 10px; border-top: 1px solid var(--line); }
    .component strong { display: block; margin-bottom: 4px; }
    .abstract { color: var(--muted); }
    .attention-demo {
      display: grid;
      gap: 18px;
      background:
        linear-gradient(135deg, color-mix(in srgb, var(--accent) 18%, transparent), color-mix(in srgb, var(--accent-2) 12%, transparent)),
        var(--paper);
      color: var(--ink);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 22px;
      overflow: hidden;
    }
    .token-row { display: flex; flex-wrap: wrap; gap: 8px; }
    .token {
      padding: 8px 10px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: var(--paper);
      font-size: 13px;
    }
    .matrix { display: grid; grid-template-columns: repeat(6, minmax(22px, 1fr)); gap: 6px; }
    .matrix span {
      aspect-ratio: 1;
      border-radius: 4px;
      background: color-mix(in srgb, var(--accent) var(--weight), var(--bg) 20%);
      border: 1px solid color-mix(in srgb, var(--accent) 20%, transparent);
    }
    .result-spotlight {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .result-card {
      padding: 18px;
      border-radius: var(--radius);
      border: 1px solid color-mix(in srgb, var(--accent) 26%, transparent);
      background: color-mix(in srgb, var(--accent) 10%, var(--paper));
    }
    .result-card strong { display: block; color: var(--accent); font-size: 26px; line-height: 1; margin-bottom: 10px; }
    .table-caption {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--paper) 92%, var(--bg) 8%);
      font-weight: 800;
    }
    .table-page {
      flex: 0 0 auto;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .table-shell { overflow-x: auto; }
    .table-image-shell {
      overflow: hidden;
    }
    .table-image {
      display: block;
      width: 100%;
      height: auto;
      background: #ffffff;
    }
    .table-fallback {
      margin-top: 10px;
      padding: 10px 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      background: color-mix(in srgb, var(--paper) 92%, var(--bg) 8%);
      font-size: 13px;
    }
    .table-fallback summary {
      cursor: pointer;
      font-weight: 800;
      color: var(--accent);
    }
    .table-fallback .table-shell {
      margin-top: 10px;
      box-shadow: none;
      border: 1px solid var(--line);
    }
    table { width: 100%; border-collapse: collapse; min-width: 720px; font-size: 14px; }
    th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    tr:nth-child(even) td { background: color-mix(in srgb, var(--paper) 78%, var(--bg) 22%); }
    .results-grid { display: grid; gap: 16px; }
    .gallery {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }
    .bibtex { position: relative; padding: 0; overflow: hidden; }
    .bibtex pre {
      margin: 0;
      padding: 22px;
      overflow-x: auto;
      background: #101827;
      color: #d8f3dc;
      font-size: 13px;
    }
    .copy {
      margin-bottom: 12px;
      border: 1px solid var(--line);
      background: var(--paper);
      border-radius: var(--radius);
      padding: 8px 12px;
      font-weight: 800;
      cursor: pointer;
    }
    footer {
      max-width: var(--max);
      margin: 0 auto;
      padding: 28px 22px 48px;
      color: var(--muted);
      border-top: 1px solid var(--line);
      font-size: 14px;
    }
    @media (max-width: 840px) {
      .hero { min-height: auto; }
      .hero-inner { padding: 40px 0 34px; }
      .impact-grid, .method-grid, .gallery, .story-grid { grid-template-columns: 1fr; }
      .method-figure img, .gallery .figure-card img { height: auto; max-height: 420px; }
      .nav-inner { align-items: flex-start; flex-direction: column; }
      main { padding-top: 30px; }
    }
    @media (max-width: 520px) {
      .nav-inner { padding: 12px 16px; }
      .nav-links { gap: 12px; font-size: 14px; }
      .hero-inner { width: min(320px, calc(100% - 56px)); max-width: min(320px, calc(100% - 56px)); padding: 32px 0 28px; }
      .section-head, .teaser .section-head { width: min(320px, 100%); max-width: min(320px, 100%); }
      h1 { font-size: 28px; line-height: 1.1; max-width: 100%; }
      h2 { font-size: 26px; line-height: 1.14; }
      .tagline { font-size: 15px; line-height: 1.5; max-width: 100%; }
      .lead { font-size: 15px; line-height: 1.55; max-width: 100%; }
      .authors, .affiliations { gap: 2px 8px; }
      .authors { width: min(320px, 100%); }
      .affiliations { width: min(280px, 100%); }
      .author-chip, .affiliation-chip { font-size: 12px; }
      .actions { gap: 8px; }
      .btn { min-height: 38px; padding: 0 13px; }
      main { padding-left: 16px; padding-right: 16px; }
      section { margin-bottom: 48px; }
      .figure-stage { padding: 12px; }
      .figure-wide img { max-height: 520px; }
      .impact-label { font-size: 28px; }
      .table-caption { align-items: flex-start; flex-direction: column; }
      table { min-width: 640px; }
    }
  </style>
</head>
<body$body_class>
  <nav class="nav" aria-label="Primary navigation">
    <div class="nav-inner">
      <a class="brand" href="#top">$title</a>
      <div class="nav-links">
        <a href="#teaser">Teaser</a>
        <a href="#abstract">Abstract</a>
        <a href="#impact">Impact</a>
        <a href="#method">Method</a>
        <a href="#results">Results</a>
      </div>
    </div>
  </nav>

  <header id="top" class="hero">
    <div class="hero-inner">
      <div class="kicker">$theme</div>
      <h1>$title</h1>
      <p class="tagline">$tagline</p>
      $author_html
      $link_html
    </div>
  </header>

  <main>
    $teaser_html

    <section id="abstract">
      <div class="section-head">
        <div class="eyebrow">Abstract</div>
        <h2>The paper in one pass.</h2>
      </div>
      <div class="panel abstract">$abstract</div>
    </section>

    <section id="impact">
      <div class="section-head">
        <div class="eyebrow">Impact</div>
        <h2>What to remember first.</h2>
        <p class="lead">A compact, evidence-backed view of the paper's central claims.</p>
      </div>
      <div class="impact-grid">$claims_html</div>
    </section>

    $story_html

    $method_html
    $interactive_html
    $results_html
    $retrospective_html
    $gallery_html

    <section id="bibtex">
      <div class="section-head">
        <div class="eyebrow">Citation</div>
        <h2>BibTeX</h2>
      </div>
      <button class="copy" type="button" data-copy="bibtex-code">Copy BibTeX</button>
      <div class="bibtex"><pre id="bibtex-code">$bibtex_html</pre></div>
    </section>
  </main>

  <footer>
    Generated by Paper2HTML Agent v2. Style-referenced, manifest-driven project page with local QA checks.
  </footer>

  <script>
    document.querySelectorAll('[data-copy]').forEach((button) => {
      button.addEventListener('click', async () => {
        const target = document.getElementById(button.getAttribute('data-copy'));
        if (!target) return;
        try {
          await navigator.clipboard.writeText(target.textContent);
          const original = button.textContent;
          button.textContent = 'Copied';
          setTimeout(() => { button.textContent = original; }, 1200);
        } catch (error) {
          target.focus();
        }
      });
    });
  </script>
</body>
</html>
"""
    )

    return template.substitute(
        title=title,
        description=escape(f"Project page for {manifest.title}.", quote=True),
        accent=plan.accent,
        body_class=body_class,
        theme=escape(plan.theme.replace("-", " ")),
        tagline=escape(tagline),
        author_html=author_html,
        link_html=link_html,
        story_html=story_html,
        claims_html=claims_html,
        teaser_html=teaser_html,
        abstract=abstract,
        method_html=method_html,
        interactive_html=interactive_html,
        results_html=results_html,
        retrospective_html=retrospective_html,
        gallery_html=gallery_html,
        bibtex_html=bibtex_html,
    )


def _should_render_promo_site(brief: ProjectBrief) -> bool:
    text = _brief_text(brief)
    signals = [
        "promotional",
        "promotion",
        "short",
        "concise",
        "animated",
        "dynamic",
        "green",
        "claim cards 去掉",
        "no claim cards",
        "宣传",
        "简洁",
        "动态",
        "绿色",
    ]
    return any(signal in text for signal in signals)


def _render_promotional_site(
    manifest: PaperManifest,
    plan: SitePlan,
    table_mode: str,
    brief: ProjectBrief,
) -> str:
    title = escape(manifest.title)
    tagline = escape(brief.hero_message or _make_tagline(manifest))
    author_html = _render_authors(manifest)
    link_html = _render_links(manifest.links)
    primary = next((item for item in manifest.figures if item.file == plan.primary_figure), None)
    abstract = escape(_limit_text(manifest.abstract, 680))
    figure_html = _promo_primary_figure(primary)
    method_chips = _promo_method_chips(brief, manifest)
    results = _promo_result_strip(manifest)
    optional_asset = _promo_optional_asset(manifest, table_mode)
    theme_label = escape(plan.theme.replace("-", " "))
    bibtex_html = escape(manifest.bibtex)
    template = Template(
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>$title</title>
  <meta name="description" content="$description" />
  <style>
    :root {
      --bg: #07130d;
      --bg-2: #0d2317;
      --ink: #f5fff8;
      --muted: #b8c9bf;
      --accent: $accent;
      --accent-2: #86efac;
      --paper: #fffdf7;
      --paper-ink: #172017;
      --line: rgba(220, 252, 231, 0.18);
      --shadow: 0 26px 70px rgba(0, 0, 0, 0.32);
      --radius: 8px;
      --max: 1080px;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 8%, rgba(34, 197, 94, 0.28), transparent 34%),
        linear-gradient(140deg, var(--bg), var(--bg-2) 48%, #05100a);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.6;
      overflow-x: hidden;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(110deg, transparent 0 46%, rgba(134, 239, 172, 0.08) 47%, transparent 49%),
        linear-gradient(70deg, transparent 0 54%, rgba(34, 197, 94, 0.08) 55%, transparent 57%);
      background-size: 280px 280px, 340px 340px;
      animation: drift 22s linear infinite;
      opacity: 0.7;
    }
    @keyframes drift { from { background-position: 0 0, 0 0; } to { background-position: 280px 160px, -340px 180px; } }
    @keyframes fadeUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
    a { color: inherit; text-decoration: none; }
    .nav {
      position: sticky;
      top: 0;
      z-index: 10;
      border-bottom: 1px solid var(--line);
      background: rgba(7, 19, 13, 0.82);
      backdrop-filter: blur(16px);
    }
    .nav-inner {
      max-width: var(--max);
      margin: 0 auto;
      padding: 12px 22px;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
    }
    .brand { font-weight: 850; }
    .nav-links { display: flex; gap: 14px; color: var(--muted); font-size: 14px; flex-wrap: wrap; }
    .hero {
      position: relative;
      min-height: 76vh;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 54px 22px 34px;
    }
    .hero-inner { width: min(920px, 100%); animation: fadeUp 640ms ease both; }
    .kicker {
      color: var(--accent-2);
      font-size: 13px;
      font-weight: 850;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    h1 {
      margin: 12px auto 14px;
      font-size: clamp(42px, 7vw, 82px);
      line-height: 1.02;
      letter-spacing: 0;
    }
    .tagline {
      max-width: 760px;
      margin: 0 auto 20px;
      color: #d9fbe3;
      font-size: clamp(18px, 2vw, 24px);
    }
    .authors, .affiliations, .actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px 10px; }
    .author-chip, .affiliation-chip { color: var(--muted); font-size: 14px; }
    .author-chip { color: #eefdf2; font-weight: 750; }
    .author-chip:not(:last-child)::after, .affiliation-chip:not(:last-child)::after { content: ","; color: var(--muted); }
    .actions { margin-top: 18px; }
    .btn {
      display: inline-flex;
      align-items: center;
      min-height: 42px;
      padding: 0 16px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.07);
      font-weight: 850;
    }
    .btn.primary { background: var(--accent); border-color: var(--accent); color: white; }
    main { max-width: var(--max); margin: 0 auto; padding: 18px 22px 88px; }
    section { margin: 0 0 54px; animation: fadeUp 640ms ease both; }
    .section-head { max-width: 760px; margin-bottom: 20px; }
    .eyebrow { color: var(--accent-2); font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.08em; }
    h2 { margin: 7px 0 10px; font-size: clamp(28px, 4vw, 48px); line-height: 1.08; letter-spacing: 0; }
    .lead { color: var(--muted); font-size: 18px; max-width: 780px; }
    .abstract-panel, .light-card, .chip, .result-pill, .bibtex {
      border-radius: var(--radius);
      border: 1px solid rgba(22, 101, 52, 0.18);
      box-shadow: var(--shadow);
    }
    .abstract-panel {
      padding: 24px;
      color: #17311e;
      background: linear-gradient(180deg, #fbfff7, #ecfdf3);
      font-size: 17px;
    }
    .light-card {
      overflow: hidden;
      color: var(--paper-ink);
      background: var(--paper);
      transition: transform 180ms ease, box-shadow 180ms ease;
    }
    .light-card:hover { transform: translateY(-3px); box-shadow: 0 30px 80px rgba(0,0,0,0.38); }
    .light-card img { display: block; width: 100%; height: auto; max-height: 720px; object-fit: contain; background: white; }
    .light-card figcaption { padding: 12px 14px; color: #3f4c42; border-top: 1px solid rgba(15, 23, 42, 0.12); font-size: 14px; }
    .chip-grid, .result-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
    .chip, .result-pill {
      padding: 18px;
      background: rgba(255, 255, 255, 0.08);
      border-color: var(--line);
    }
    .chip strong, .result-pill strong { display: block; color: var(--accent-2); font-size: 22px; margin-bottom: 6px; }
    .chip span, .result-pill span { color: var(--muted); font-size: 14px; }
    .optional-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; }
    .bibtex { overflow: hidden; background: #07110c; }
    .bibtex pre { margin: 0; padding: 20px; overflow-x: auto; color: #d9fbe3; }
    .copy { margin-bottom: 12px; border: 1px solid var(--line); background: rgba(255,255,255,0.08); color: var(--ink); border-radius: var(--radius); padding: 8px 12px; font-weight: 850; cursor: pointer; }
    footer { max-width: var(--max); margin: 0 auto; padding: 28px 22px 48px; color: var(--muted); border-top: 1px solid var(--line); font-size: 14px; }
    @media (max-width: 680px) {
      .hero { min-height: auto; }
      h1 { font-size: 34px; }
      .tagline, .lead { font-size: 16px; }
      main { padding-left: 16px; padding-right: 16px; }
    }
  </style>
</head>
<body>
  <nav class="nav" aria-label="Primary navigation">
    <div class="nav-inner">
      <a class="brand" href="#top">$title</a>
      <div class="nav-links">
        <a href="#abstract">Abstract</a>
        <a href="#architecture">Architecture</a>
        <a href="#idea">Idea</a>
        <a href="#results">Results</a>
      </div>
    </div>
  </nav>
  <header id="top" class="hero">
    <div class="hero-inner">
      <div class="kicker">$theme_label</div>
      <h1>$title</h1>
      <p class="tagline">$tagline</p>
      $author_html
      $link_html
    </div>
  </header>
  <main>
    <section id="abstract">
      <div class="section-head"><div class="eyebrow">Abstract</div><h2>The paper, compressed.</h2></div>
      <div class="abstract-panel">$abstract</div>
    </section>
    <section id="architecture">
      <div class="section-head"><div class="eyebrow">Main Visual</div><h2>$teaser_heading</h2><p class="lead">The original architecture figure stays on a light card so the paper asset remains readable inside the green interface.</p></div>
      $figure_html
    </section>
    <section id="idea">
      <div class="section-head"><div class="eyebrow">Core Idea</div><h2>The core idea.</h2><p class="lead">$narrative</p></div>
      <div class="chip-grid">$method_chips</div>
    </section>
    <section id="results">
      <div class="section-head"><div class="eyebrow">Key Results</div><h2>Only the headline evidence.</h2><p class="lead">The page keeps the experimental story short and uses paper-supported numbers.</p></div>
      <div class="result-strip">$results</div>
      $optional_asset
    </section>
    <section id="why">
      <div class="section-head"><div class="eyebrow">Why It Matters</div><h2>Why it matters.</h2><p class="lead">$why_matters</p></div>
    </section>
    <section id="bibtex">
      <div class="section-head"><div class="eyebrow">Citation</div><h2>BibTeX</h2></div>
      <button class="copy" type="button" data-copy="bibtex-code">Copy BibTeX</button>
      <div class="bibtex"><pre id="bibtex-code">$bibtex_html</pre></div>
    </section>
  </main>
  <footer>Generated by Paper2HTML Agent v2. Plan-driven promotional renderer with local QA checks.</footer>
  <script>
    document.querySelectorAll('[data-copy]').forEach((button) => {
      button.addEventListener('click', async () => {
        const target = document.getElementById(button.getAttribute('data-copy'));
        if (!target) return;
        try {
          await navigator.clipboard.writeText(target.textContent);
          const original = button.textContent;
          button.textContent = 'Copied';
          setTimeout(() => { button.textContent = original; }, 1200);
        } catch (error) {
          target.focus();
        }
      });
    });
  </script>
</body>
</html>
"""
    )
    return template.substitute(
        title=title,
        description=escape(f"Project page for {manifest.title}.", quote=True),
        accent=plan.accent,
        theme_label=theme_label,
        tagline=tagline,
        author_html=author_html,
        link_html=link_html,
        abstract=abstract,
        teaser_heading=escape(brief.teaser_heading or _default_teaser_heading(manifest)),
        figure_html=figure_html,
        narrative=escape(_limit_text(brief.narrative_angle, 220)),
        method_chips=method_chips,
        results=results,
        optional_asset=optional_asset,
        why_matters=escape(
            _limit_text(manifest.claims[0].description, 220)
            if manifest.claims
            else _limit_text(manifest.abstract, 220)
        ),
        bibtex_html=bibtex_html,
    )


def _promo_primary_figure(fig: Figure | None) -> str:
    if not fig:
        return '<div class="light-card"><figcaption>Primary paper figure was not detected.</figcaption></div>'
    return (
        '<figure class="light-card">'
        f'<img src="{escape(fig.file, quote=True)}" alt="{escape(fig.caption, quote=True)}" />'
        f'<figcaption>{escape(fig.caption)}</figcaption></figure>'
    )


def _promo_method_chips(brief: ProjectBrief, manifest: PaperManifest) -> str:
    # Derive chips from the paper's own method components; fall back to emphasis terms.
    labels: list[tuple[str, str]] = []
    for comp in manifest.method_components[:4]:
        labels.append((_limit_text(comp.get("name", ""), 40), _limit_text(comp.get("description", ""), 120)))
    if not labels:
        for item in brief.emphasis[:4]:
            labels.append((_limit_text(item, 40), ""))
    if not labels:
        labels.append(("Core idea", _limit_text(manifest.abstract, 120)))
    return "".join(
        f'<article class="chip"><strong>{escape(label)}</strong><span>{escape(body)}</span></article>'
        for label, body in labels[:4]
    )


def _promo_result_strip(manifest: PaperManifest) -> str:
    cards = _result_spotlight_cards(manifest)
    return "".join(
        f'<article class="result-pill"><strong>{escape(label)}</strong><span>{escape(text)}</span></article>'
        for label, text in cards[:3]
    )


def _promo_optional_asset(manifest: PaperManifest, table_mode: str) -> str:
    table2 = next((table for table in manifest.tables if "Table 2" in table.caption), None)
    if table2 and table2.image:
        return (
            '<div class="optional-grid" style="margin-top:14px">'
            f'{_render_table_block(table2, table_mode="image" if table_mode in {"auto", "image"} else table_mode)}'
            "</div>"
        )
    figure2 = next((fig for fig in manifest.figures if "Figure 2" in fig.caption), None)
    if figure2:
        return (
            '<div class="optional-grid" style="margin-top:14px"><figure class="light-card">'
            f'<img src="{escape(figure2.file, quote=True)}" alt="{escape(figure2.caption, quote=True)}" />'
            f'<figcaption>{escape(figure2.caption)}</figcaption></figure></div>'
        )
    return ""


def validate_site(
    html: str,
    output_dir: Path,
    manifest: PaperManifest,
    brief: ProjectBrief | None = None,
    plan: SitePlan | None = None,
    strict_alignment: bool = True,
) -> QAResult:
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

    alignment = _validate_plan_alignment(html, brief, plan, strict=strict_alignment)
    errors.extend(alignment["errors"])
    warnings.extend(alignment["warnings"])

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
        "plan_alignment": alignment["checks"],
    }
    return QAResult(ok=not errors, errors=errors, warnings=warnings, checks=checks)


def _validate_plan_alignment(
    html: str, brief: ProjectBrief | None, plan: SitePlan | None, strict: bool = True
) -> dict[str, object]:
    """Check that things the user explicitly asked for actually appear.

    Renderer-agnostic: checks are SEMANTIC (does the page contain a table? an abstract heading?
    a keyframe animation?) rather than tied to the template renderer's CSS class names. When
    ``strict`` is False (e.g. the free-form LLM renderer), unmet expectations are reported as
    warnings instead of errors, so we never force the LLM back toward a fixed structure.
    """
    if not brief:
        return {"errors": [], "warnings": [], "checks": {}}
    text = _brief_text(brief)
    lower_html = html.lower()
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, object] = {}

    def require(condition: bool, label: str, severity: str = "error") -> None:
        checks[label] = condition
        if condition:
            return
        message = f"Plan alignment failed: {label}"
        if severity == "error" and not strict:
            severity = "warning"
        if severity == "warning":
            warnings.append(message)
        else:
            errors.append(message)

    if any(word in text for word in ["animated", "dynamic", "motion", "fade", "hover", "动态"]):
        require("@keyframes" in lower_html or "transition:" in lower_html or "intersectionobserver" in lower_html,
                "motion/animation present")
    if "abstract" in text:
        require("abstract" in lower_html, "abstract content present")
    if "figure 1" in text or "architecture" in text or "primary figure" in text:
        require(
            plan is not None and bool(plan.primary_figure) and plan.primary_figure.lower() in lower_html,
            "primary figure rendered",
        )
    if "key results" in text or "result badges" in text:
        require("<table" in lower_html or "result" in lower_html, "results content present")
    if plan:
        checks["theme"] = plan.theme
    return {"errors": errors, "warnings": warnings, "checks": checks}


def render_qa_report(qa: QAResult, manifest: PaperManifest, plan: SitePlan) -> str:
    lines = [
        "# Paper2HTML Agent QA Report",
        "",
        f"Status: {'PASS' if qa.ok else 'FAIL'}",
        f"Title: {manifest.title}",
        f"Theme: {plan.theme}",
        f"Style references: {', '.join(item['name'] for item in STYLE_REFERENCES)}",
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


def _parse_rotate_spec(spec: str, manifest: PaperManifest) -> dict[str, int]:
    """Parse a CLI --rotate spec like "3:90,5:90" into {filename: degrees}.

    Figure numbers are 1-based and refer to the order figures appear in manifest.figures.
    """
    rotations: dict[str, int] = {}
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            print(f"[agent] ignoring rotate token '{chunk}' (expected NUMBER:DEGREES)")
            continue
        num_str, deg_str = chunk.split(":", 1)
        try:
            idx = int(num_str.strip())
            deg = int(deg_str.strip())
        except ValueError:
            print(f"[agent] ignoring rotate token '{chunk}' (non-integer)")
            continue
        if not (1 <= idx <= len(manifest.figures)):
            print(f"[agent] ignoring rotate token '{chunk}' (no figure #{idx}; {len(manifest.figures)} figures)")
            continue
        deg = deg % 360
        if deg == 0:
            continue
        if deg not in (90, 180, 270):
            print(f"[agent] ignoring rotate token '{chunk}' (degrees must be 90/180/270)")
            continue
        rotations[manifest.figures[idx - 1].file] = deg
    return rotations


def _apply_image_rotations(output_dir: Path, rotations: dict[str, int]) -> None:
    """Rotate already-copied images in place so they read upright. Clockwise degrees.

    Operates only on the copied files under output_dir, never the source cache. Degrades
    gracefully if Pillow is unavailable.
    """
    if not rotations:
        return
    try:
        from PIL import Image
    except ImportError:
        print("[agent] Pillow not installed; skipping image rotation. Run: pip install Pillow")
        return
    for file_ref, deg in rotations.items():
        deg = deg % 360
        if deg == 0:
            continue
        # Accept keys with or without an "images/" prefix; images are copied under out_dir/<file_ref>
        # but a hand-written brief may use the bare filename.
        candidates = [output_dir / file_ref, output_dir / "images" / Path(file_ref).name]
        target = next((c for c in candidates if c.exists()), None)
        if target is None:
            print(f"[agent] rotate: image not found in output, skipping: {file_ref}")
            continue
        try:
            with Image.open(target) as img:
                # PIL rotate is counter-clockwise; negate for clockwise (paper figures are
                # usually stored rotated counter-clockwise and need a clockwise correction).
                rotated = img.rotate(-deg, expand=True)
                fmt = img.format or ("JPEG" if target.suffix.lower() in {".jpg", ".jpeg"} else "PNG")
                save_kwargs = {"quality": 92} if fmt == "JPEG" else {}
                rotated.save(target, format=fmt, **save_kwargs)
            print(f"[agent] rotated {file_ref} by {deg} deg clockwise")
        except Exception as exc:  # noqa: BLE001 - one bad image shouldn't abort the build
            print(f"[agent] rotate failed for {file_ref}: {exc}")


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


def _extract_links(markdown: str, source: Path, paper_url: str | None, code_url: str | None) -> Links:
    cleaned = normalize_markdown(markdown)
    urls = [url.rstrip(".,;") for url in URL_RE.findall(cleaned)]
    links = Links()

    arxiv = next((url for url in urls if "arxiv.org" in url.lower()), "")
    if paper_url:
        links.paper = paper_url
    elif arxiv:
        links.paper = arxiv
    else:
        arxiv_id = _infer_arxiv_id(source)
        if arxiv_id:
            links.paper = f"https://arxiv.org/abs/{arxiv_id}"

    github = next((url for url in urls if "github.com" in url.lower()), "")
    if code_url:
        links.code = code_url
    elif github:
        links.code = github

    for url in urls:
        lower = url.lower()
        if not links.project and any(word in lower for word in ["github.io", "project", "demo"]):
            links.project = url
        if not links.data and any(word in lower for word in ["dataset", "data"]):
            links.data = url
        if not links.video and any(word in lower for word in ["youtube", "youtu.be", "video"]):
            links.video = url
    return links


def _infer_arxiv_id(source: Path) -> str:
    match = ARXIV_ID_RE.search(source.stem)
    if not match:
        return ""
    return match.group("id") + (match.group("version") or "")


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
    if any(word in lower for word in ["attention", "visualization", "example"]):
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
        re.compile(r"\b\d+(?:\.\d+)?\s+[A-Z][A-Za-z][A-Za-z0-9\-]*\b"),  # number followed by a metric/proper noun (e.g. "28.4 BLEU", "92.1 F1")
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
        for item in re.findall(r"\b\d+(?:\.\d+)?\b", abstract):
            _add_claim(claims, item, _limit_text(_clean_inline(abstract), 180), "Abstract")
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
    return "\n".join(chunk for chunk in chunks if chunk)


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
    year_match = re.search(r"(19|20)\d{2}", source.stem)
    year = year_match.group(0) if year_match else ""
    key_author = "paper"
    if authors:
        key_author = re.sub(r"[^a-zA-Z0-9]", "", authors[0].split()[-1]).lower() or "paper"
    key_title = re.sub(r"[^a-zA-Z0-9]", "", title.split()[0]).lower() if title.split() else "project"
    key = f"{key_author}{year}{key_title}"
    author_field = " and ".join(authors) if authors else "Unknown"
    return "\n".join(
        [
            f"@article{{{key},",
            f"  title={{{title}}},",
            f"  author={{{author_field}}},",
            "  journal={arXiv preprint},",
            f"  year={{{year}}}",
            "}",
        ]
    )


def _choose_primary_figure(figures: list[Figure]) -> str:
    if not figures:
        return ""
    for role in ["architecture", "result", "qualitative"]:
        for fig in figures:
            if fig.role == role:
                return fig.file
    return figures[0].file


def _choose_method_figure(figures: list[Figure], primary: str) -> str:
    # Prefer a non-primary figure that looks method/architecture-related by caption.
    for fig in figures:
        lower = fig.caption.lower()
        if fig.file != primary and any(
            word in lower for word in ["method", "architecture", "framework", "pipeline", "overview", "model", "diagram", "system"]
        ):
            return fig.file
    for fig in figures:
        if fig.file != primary:
            return fig.file
    return ""


def _make_tagline(manifest: PaperManifest) -> str:
    if manifest.claims:
        claim = manifest.claims[0]
        return f"The idea, evidence, and design story behind {claim.label}."
    if manifest.abstract:
        return _limit_text(manifest.abstract, 150)
    return "A structured project page generated from the paper."


def _story_cards(manifest: PaperManifest) -> list[tuple[str, str]]:
    first_claim = manifest.claims[0].description if manifest.claims else "The paper reports its central evidence in the extracted results."
    return [
        ("Problem", _limit_text(manifest.abstract, 170)),
        ("Method", "The agent extracts method components and figures, then turns them into a reader-facing explanation."),
        ("Evidence", _limit_text(first_claim, 170)),
    ]


def _method_cards(manifest: PaperManifest) -> list[dict[str, str]]:
    if manifest.method_components:
        return manifest.method_components[:4]
    return [{"name": "Core idea", "description": _limit_text(manifest.abstract, 220)}]


def _render_result_spotlight(manifest: PaperManifest) -> str:
    cards = _result_spotlight_cards(manifest)
    if not cards:
        return ""
    card_html = "".join(
        f'<article class="result-card"><strong>{escape(label)}</strong><span>{escape(text)}</span></article>'
        for label, text in cards
    )
    return f'<div class="result-spotlight">{card_html}</div>'


def _result_spotlight_cards(manifest: PaperManifest) -> list[tuple[str, str]]:
    return [(claim.label, claim.description) for claim in manifest.claims[:3]]


def _render_authors(manifest: PaperManifest) -> str:
    if not manifest.authors and not manifest.affiliations:
        return ""
    author_chips = "".join(f'<span class="author-chip">{escape(_display_name(author))}</span>' for author in manifest.authors)
    affiliation_chips = "".join(
        f'<span class="affiliation-chip">{escape(affiliation)}</span>' for affiliation in manifest.affiliations
    )
    affiliations = f'<div class="affiliations">{affiliation_chips}</div>' if affiliation_chips else ""
    return f'<div class="authors">{author_chips}</div>{affiliations}'


def _display_name(name: str) -> str:
    replacements = {
        "艁ukasz Kaiser": "Lukasz Kaiser",
    }
    return replacements.get(name, name)


def _render_links(links: Links) -> str:
    items = []
    labels = [
        ("paper", "Paper"),
        ("code", "Code"),
        ("project", "Project"),
        ("demo", "Demo"),
        ("data", "Data"),
        ("video", "Video"),
    ]
    for key, label in labels:
        url = getattr(links, key)
        if not url:
            continue
        cls = "btn primary" if key == "paper" else "btn"
        items.append(f'<a class="{cls}" href="{escape(url, quote=True)}">{label}</a>')
    return f'<div class="actions">{"".join(items)}</div>' if items else ""


def _render_claims(claims: list[Claim]) -> str:
    if not claims:
        claims = [Claim("Ready", "The agent extracted the paper and generated a structured project page.", "Agent")]
    return "".join(
        f'<article class="impact-card"><div class="impact-label">{escape(claim.label)}</div>'
        f'<div class="impact-text">{escape(claim.description)}</div>'
        f'<div class="impact-evidence">{escape(claim.evidence)}</div></article>'
        for claim in claims[:4]
    )


def _render_story(manifest: PaperManifest, plan: SitePlan, brief: ProjectBrief | None = None) -> str:
    cards = _story_cards(manifest)
    card_html = "".join(
        f'<article class="story-card"><div class="story-step">{idx}</div>'
        f'<h3>{escape(title)}</h3><p>{escape(body)}</p></article>'
        for idx, (title, body) in enumerate(cards, start=1)
    )
    section_html = ""
    if brief and brief.sections:
        section_cards = "".join(
            f'<article class="section-item"><strong>{escape(title)}</strong><span>{escape(body)}</span></article>'
            for title, body in _brief_section_cards(brief.sections)
        )
        section_html = (
            '<div class="section-head"><div class="eyebrow">Page Plan</div>'
            '<h2>The requested layout, made explicit.</h2>'
            '<p class="lead">The terminal brief is preserved as a concrete page plan before rendering.</p></div>'
            f'<div class="section-list">{section_cards}</div>'
        )
    return (
        '<section id="story"><div class="section-head"><div class="eyebrow">Paper Story</div>'
        '<h2>Read the paper through its argument.</h2>'
        '<p class="lead">The page starts with the problem, then the mechanism, then the evidence.</p></div>'
        f'<div class="story-grid">{card_html}</div>{section_html}</section>'
    )


def _render_teaser(manifest: PaperManifest, plan: SitePlan, brief: ProjectBrief | None = None) -> str:
    fig = next((item for item in manifest.figures if item.file == plan.primary_figure), None)
    if not fig:
        return ""
    heading = brief.teaser_heading if brief and brief.teaser_heading else (_limit_text(fig.caption, 80) if fig.caption else "Overview")
    lead = (
        "The primary paper figure appears once, at reading scale, so the page starts from the actual contribution instead of decoration."
    )
    if brief and brief.narrative_angle:
        lead = f"{brief.narrative_angle} The primary paper figure appears once, at reading scale."
    return (
        '<section id="teaser" class="teaser">'
        '<div class="section-head"><div class="eyebrow">Teaser</div>'
        f'<h2>{escape(heading)}</h2>'
        f'<p class="lead">{escape(lead)}</p>'
        "</div>"
        '<div class="figure-stage">'
        f'<figure class="figure-card figure-wide"><img src="{escape(fig.file, quote=True)}" alt="{escape(fig.caption, quote=True)}" />'
        f"<figcaption>{escape(fig.caption)}</figcaption></figure></div></section>"
    )


def _render_method(manifest: PaperManifest, plan: SitePlan, brief: ProjectBrief | None = None) -> str:
    components = _method_cards(manifest)
    component_html = "".join(
        f'<div class="component"><strong>{escape(item["name"])}</strong>'
        f'<span>{escape(item["description"])}</span></div>'
        for item in components
    )
    method_file = _method_figure_from_plan(plan)
    figure = next((fig for fig in manifest.figures if fig.file == method_file), None)
    figure_html = ""
    if figure:
        figure_html = (
            f'<figure class="figure-card method-figure"><img src="{escape(figure.file, quote=True)}" '
            f'alt="{escape(figure.caption, quote=True)}" /><figcaption>{escape(figure.caption)}</figcaption></figure>'
        )
    heading = "How it works."
    lead = "A reader-facing explanation of the method, paired with a supporting figure rather than repeating the primary figure."
    return (
        '<section id="method">'
        '<div class="section-head"><div class="eyebrow">Method</div>'
        f'<h2>{escape(heading)}</h2>'
        f'<p class="lead">{escape(lead)}</p></div>'
        '<div class="method-grid">'
        f'<div class="panel"><div class="component-list">{component_html}</div></div>'
        f"{figure_html}</div></section>"
    )


def _render_interactive(plan: SitePlan) -> str:
    # No paper-specific interactive widget; the deterministic renderer stays content-agnostic.
    return ""


def _render_results(manifest: PaperManifest, table_mode: str = "auto", brief: ProjectBrief | None = None) -> str:
    if not manifest.tables and not manifest.claims:
        return ""
    table_html = ""
    for table in manifest.tables[:4]:
        table_html += _render_table_block(table, table_mode=table_mode)
    if not table_html:
        rows = "".join(
            f"<tr><td>{escape(claim.label)}</td><td>{escape(claim.description)}</td><td>{escape(claim.evidence)}</td></tr>"
            for claim in manifest.claims
        )
        table_html = (
            '<div class="table-shell"><table><thead><tr><th>Signal</th><th>Meaning</th><th>Evidence</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>"
        )
    heading = "The evidence, summarized first."
    lead = "Key quantitative results are surfaced before the full tables, so the reader sees the conclusion before the details."
    if brief and any("table" in item.lower() or "result" in item.lower() for item in brief.emphasis):
        heading = "Key results, then paper-original tables."
        lead = "Compact result cards lead into cropped paper tables, preserving the original layout where the parser would lose math or alignment."
    return (
        '<section id="results"><div class="section-head"><div class="eyebrow">Results</div>'
        f'<h2>{escape(heading)}</h2>'
        f'<p class="lead">{escape(lead)}</p></div>'
        f'{_render_result_spotlight(manifest)}<div class="results-grid">{table_html}</div></section>'
    )


def _render_table_block(table: TableBlock, table_mode: str = "auto") -> str:
    caption = escape(table.caption)
    alt = escape(table.caption, quote=True)
    html_table = _normalize_table_html(table.html)
    use_image = table_mode in {"auto", "image"} and table.image
    if use_image:
        fallback = ""
        if table_mode == "auto" and html_table:
            fallback = (
                '<details class="table-fallback">'
                '<summary>Extracted HTML table</summary>'
                f'<div class="table-shell">{html_table}</div>'
                '</details>'
            )
        page = f'<span class="table-page">Page {table.page + 1}</span>' if table.page is not None else ""
        return (
            '<figure class="table-shell table-image-shell">'
            f'<div class="table-caption">{caption}{page}</div>'
            f'<img class="table-image" src="{escape(table.image, quote=True)}" alt="{alt}" />'
            f"{fallback}</figure>"
        )
    if html_table:
        return (
            '<div class="table-shell">'
            f'<div class="table-caption">{caption}</div>'
            f"{html_table}</div>"
        )
    return ""


def _render_retrospective(manifest: PaperManifest, brief: ProjectBrief | None) -> str:
    if not brief:
        return ""
    text = " ".join([brief.goal, brief.narrative_angle, brief.notes, brief.source_brief]).lower()
    if not any(word in text for word in ["impact", "foundational", "language model", "retrospective", "modern"]):
        return ""
    body = (
        "This page separates the paper's own claims from later influence, so the broader context remains useful without "
        "overstating what the original work directly demonstrated."
    )
    return (
        '<section id="retrospective"><div class="section-head"><div class="eyebrow">Broader Context</div>'
        '<h2>Why the paper mattered later.</h2>'
        f'<p class="lead">{escape(body)}</p></div></section>'
    )


def _brief_section_cards(sections: list[str]) -> list[tuple[str, str]]:
    cards: list[tuple[str, str]] = []
    for raw in sections[:8]:
        text = re.sub(r"^\s*\d+[\.)]\s*", "", raw).strip()
        if not text:
            continue
        parts = re.split(r"\s+(?:containing|explaining|using|for|with)\s+", text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            title, body = parts[0], parts[1]
        else:
            title, body = text.split(":", 1) if ":" in text else (text, "Included from the confirmed terminal brief.")
        cards.append((_limit_text(title.strip().capitalize(), 72), _limit_text(body.strip(), 170)))
    return cards


def _normalize_table_html(html: str) -> str:
    html = html.strip()
    html = html.replace("0(1)", "O(1)")
    return html


def _render_gallery(manifest: PaperManifest, plan: SitePlan) -> str:
    method_file = _method_figure_from_plan(plan)
    used = {plan.primary_figure, method_file}
    figs = [fig for fig in manifest.figures if fig.file in plan.featured_figures and fig.file not in used]
    if not figs:
        return ""
    cards = "".join(
        f'<figure class="figure-card"><img src="{escape(fig.file, quote=True)}" alt="{escape(fig.caption, quote=True)}" />'
        f"<figcaption>{escape(fig.caption)}</figcaption></figure>"
        for fig in figs[:4]
    )
    return (
        '<section id="gallery"><div class="section-head"><div class="eyebrow">Figures</div>'
        '<h2>Attention patterns and supporting figures.</h2>'
        '<p class="lead">Figures are capped to a readable size and kept on a white canvas for inspection.</p></div>'
        f'<div class="gallery">{cards}</div></section>'
    )


def _method_figure_from_plan(plan: SitePlan) -> str:
    if plan.featured_figures:
        return plan.featured_figures[0]
    return ""


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


def _brief_text(brief: ProjectBrief) -> str:
    return " ".join(
        [
            brief.audience,
            brief.goal,
            brief.style,
            " ".join(brief.emphasis),
            brief.narrative_angle,
            brief.hero_message,
            brief.teaser_heading,
            brief.table_mode,
            brief.figure_strategy,
            " ".join(brief.sections),
            brief.ascii_wireframe,
            brief.notes,
            brief.source_brief,
        ]
    ).lower()


def _json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _inspect_input_for_brief(
    input_path: str,
    output_dir: str | None,
    images_dir: str | None,
    use_lite: bool,
    reuse_parsed: bool,
    paper_url: str | None,
    code_url: str | None,
) -> tuple[PaperManifest, Path | None, list[Path]]:
    source = _resolve_existing_path(input_path)
    probe_out = Path(output_dir) if output_dir else default_output_root(source) / f"{source.stem}_agent"
    markdown, _parsed_images, parsed_dir = _load_or_parse_source(
        source,
        probe_out,
        use_lite=use_lite,
        reuse_parsed=reuse_parsed,
    )
    markdown = normalize_markdown(markdown)
    image_roots = _candidate_image_roots(source, probe_out, images_dir)
    manifest = extract_manifest(
        markdown,
        source=source,
        image_roots=image_roots,
        paper_url=paper_url,
        code_url=code_url,
        parsed_dir=parsed_dir,
    )
    return manifest, parsed_dir, image_roots


def _diagnose_manifest(manifest: PaperManifest, parsed_dir: Path | None) -> list[str]:
    table_images = sum(1 for table in manifest.tables if table.image)
    diagnostics = [
        f"Title: {manifest.title}",
        f"Authors: {len(manifest.authors)} detected",
        f"Figures: {len(manifest.figures)} detected",
        f"Tables: {len(manifest.tables)} detected, {table_images} with paper-cropped screenshots",
        f"Claims: {len(manifest.claims)} extracted",
        f"Parsed cache: {parsed_dir if parsed_dir else 'not detected'}",
    ]
    if manifest.claims:
        diagnostics.append("Top claims: " + "; ".join(claim.label for claim in manifest.claims[:4]))
    if manifest.figures:
        diagnostics.append("Primary figure candidate: " + manifest.figures[0].caption)
    return diagnostics


def _default_brief(manifest: PaperManifest, table_mode: str) -> ProjectBrief:
    return ProjectBrief(
        audience="Readers who want a fast but faithful project-page version of the paper",
        goal="Communicate the paper's core contribution, evidence, and reusable figures in a polished project page.",
        style="classic",
        emphasis=["main idea", "method diagram", "quantitative results", "paper-original tables"],
        narrative_angle="Frame the page around the paper's problem, method, and strongest evidence.",
        hero_message=_make_tagline(manifest),
        teaser_heading=_default_teaser_heading(manifest),
        table_mode=table_mode,
    )


def _default_teaser_heading(manifest: PaperManifest) -> str:
    """Pick a teaser heading from the primary/architecture figure caption, else generic."""
    for fig in manifest.figures:
        if fig.role == "architecture" and fig.caption:
            return _limit_text(fig.caption, 80)
    if manifest.figures and manifest.figures[0].caption:
        return _limit_text(manifest.figures[0].caption, 80)
    return "The paper's central visual."


def _print_agent_method() -> None:
    print("")
    print("[Paper2HTML-Agent] Method")
    print("  1. Inspect: read the parsed paper, figures, tables, links, and claims.")
    print("  2. Ask: collect your free-form page intent.")
    print("  3. Sketch: produce a structured brief, build plan, and ASCII wireframe.")
    print("  4. Revise: accept terminal feedback and redraw the plan until it feels right.")
    print("  5. Confirm: freeze the reviewed brief as project_brief.json.")
    print("  6. Build: render deterministic HTML from the confirmed brief.")
    print("  7. QA: check missing images, repeated images, table screenshots, and links.")
    print("")


def _print_brief(brief: ProjectBrief) -> None:
    print("")
    print("[Paper2HTML-Agent] Proposed brief")
    print(f"  Audience: {brief.audience}")
    print(f"  Goal: {brief.goal}")
    print(f"  Style: {brief.style}")
    print(f"  Emphasis: {', '.join(brief.emphasis)}")
    print(f"  Narrative: {brief.narrative_angle}")
    print(f"  Hero message: {brief.hero_message}")
    print(f"  Teaser heading: {brief.teaser_heading}")
    print(f"  Table mode: {brief.table_mode}")
    print(f"  Figure strategy: {brief.figure_strategy}")
    if brief.sections:
        print("  Sections:")
        for item in brief.sections:
            print(f"    - {item}")
    if brief.notes:
        print(f"  Notes: {brief.notes}")
    if brief.image_rotations:
        rots = ", ".join(f"{Path(f).name[:8]}..={d}deg" for f, d in brief.image_rotations.items())
        print(f"  Image rotations: {rots}")
    if brief.revision_history:
        print("  Revision history:")
        for item in brief.revision_history[-3:]:
            print(f"    - {item}")
    print("")


def _print_review_package(brief: ProjectBrief, manifest: PaperManifest) -> None:
    _refresh_wireframe(brief, manifest)
    _print_brief(brief)
    print("[Paper2HTML-Agent] ASCII wireframe")
    print(brief.ascii_wireframe)
    print("[Paper2HTML-Agent] Build plan")
    for line in _build_plan_lines(brief, manifest):
        print(f"  - {line}")
    print("")


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:  # noqa: BLE001
        return None


def _image_dims_payload(path: Path) -> dict[str, object]:
    """Width/height/aspect/orientation for an image, for LLM layout decisions. Empty on failure."""
    wh = _image_dimensions(path)
    if not wh:
        return {}
    w, h = wh
    if h == 0:
        return {}
    aspect = round(w / h, 2)
    if aspect >= 2.5:
        orientation = "ultra-wide"
    elif aspect >= 1.3:
        orientation = "wide"
    elif aspect <= 0.8:
        orientation = "tall"
    else:
        orientation = "square"
    return {"width": w, "height": h, "aspect": aspect, "orientation": orientation}


def _print_figures(manifest: PaperManifest, image_roots: list[Path] | None = None) -> None:
    """List figures with a stable 1-based number, role, caption, and orientation hint."""
    if not manifest.figures:
        print("  (no figures detected)")
        return
    print("")
    print("Figures (use the number with 'rotate <n> <deg>'):")
    src = Path(manifest.source).parent if manifest.source else None
    for i, fig in enumerate(manifest.figures, start=1):
        dims = ""
        hint = ""
        path = None
        for root in (image_roots or []):
            cand = root / fig.file
            if cand.exists():
                path = cand
                break
        if path is None and src is not None:
            for cand in (src / fig.file, src / "images" / Path(fig.file).name, src / "parsed" / "images" / Path(fig.file).name):
                if cand.exists():
                    path = cand
                    break
        if path is not None:
            wh = _image_dimensions(path)
            if wh:
                w, h = wh
                orient = "portrait" if h > w else ("square" if abs(w - h) < 40 else "landscape")
                dims = f"  {w}x{h}"
                if h > w:
                    hint = "  [portrait - may be rotated]"
        caption = _limit_text(fig.caption, 70)
        print(f"  #{i}  [{fig.role}]{dims}{hint}  {caption}")
    print("Tip: paper attention/visualization figures stored sideways usually need 'rotate <n> 90'.")
    print("")


def _handle_rotate_command(command: str, brief: ProjectBrief, manifest: PaperManifest) -> None:
    """Parse 'rotate <n> <deg>' (also tolerant of 'rotate figure 3 by 90' / '第3张转90')."""
    numbers = re.findall(r"\d+", command)
    if len(numbers) < 1:
        print("  usage: rotate <figure-number> <degrees 90|180|270>  (e.g. rotate 3 90)")
        return
    idx = int(numbers[0])
    deg = int(numbers[1]) % 360 if len(numbers) >= 2 else 90
    if not (1 <= idx <= len(manifest.figures)):
        print(f"  no figure #{idx} (there are {len(manifest.figures)}). Type 'figures' to list them.")
        return
    file_ref = manifest.figures[idx - 1].file
    if deg == 0:
        brief.image_rotations.pop(file_ref, None)
        print(f"  cleared rotation for figure #{idx}")
        return
    if deg not in (90, 180, 270):
        print("  degrees must be 90, 180, or 270")
        return
    brief.image_rotations[file_ref] = deg
    brief.revision_history.append(f"rotate figure #{idx} by {deg} deg clockwise")
    print(f"  figure #{idx} will be rotated {deg} deg clockwise at build time.")


def _collect_brief(manifest: PaperManifest, default_table_mode: str) -> ProjectBrief:
    brief = _default_brief(manifest, default_table_mode)
    print("")
    print("[Paper2HTML-Agent] Intent collection")
    print("Paste a full design brief if you have one, or press Enter for guided defaults.")
    print("For multi-line input, finish with a line containing only END.")
    freeform = _prompt_multiline("Design brief")
    if freeform:
        brief = _brief_from_freeform(manifest, default_table_mode, freeform)
    else:
        print("Press Enter to accept a recommendation. You can revise the final brief before building.")
        brief.audience = _prompt_text("Audience", brief.audience)
        brief.goal = _prompt_text("Goal", brief.goal)
        brief.style = _prompt_choice("Style", STYLE_CHOICES, brief.style)
        emphasis = _prompt_text("Emphasis, comma separated", ", ".join(brief.emphasis))
        brief.emphasis = [item.strip() for item in emphasis.split(",") if item.strip()]
        brief.narrative_angle = _prompt_text("Narrative angle", brief.narrative_angle)
        brief.hero_message = _prompt_text("Hero message", brief.hero_message)
        brief.teaser_heading = _prompt_text("Teaser heading", brief.teaser_heading)
        brief.table_mode = _prompt_choice("Table rendering", ["auto", "image", "html"], brief.table_mode)
        brief.notes = _prompt_text("Extra constraints or notes", brief.notes)
    return _revise_brief_loop(brief, manifest)


def _revise_brief_loop(brief: ProjectBrief, manifest: PaperManifest) -> ProjectBrief:
    while True:
        _print_review_package(brief, manifest)
        print("Type 'confirm' to build, 'edit' for guided edits, 'note <text>' to append a note,")
        print("'figures' to list figures, 'rotate <n> <deg>' to fix a sideways figure, or describe a revision in natural language.")
        command = _prompt_text("Decision", "confirm").strip()
        lower = command.lower()
        if lower in {"confirm", "c", "yes", "y"}:
            _refresh_wireframe(brief, manifest)
            brief.confirmed = True
            return brief
        if lower in {"abort", "quit", "exit"}:
            raise SystemExit("Interactive generation aborted before build.")
        if lower in {"figures", "figs", "list", "images"}:
            _print_figures(manifest)
            continue
        if lower.startswith("rotate"):
            _handle_rotate_command(command, brief, manifest)
            continue
        if lower.startswith("note "):
            note = command[5:].strip()
            if note.lower().startswith("note "):
                note = note[5:].strip()
            if note:
                _revise_with_ai_or_rules(brief, manifest, note)
            continue
        if lower == "edit":
            field = _prompt_choice(
                "Field",
                ["audience", "goal", "style", "emphasis", "narrative", "hero", "teaser", "table", "sections", "notes"],
                "goal",
            )
            if field == "audience":
                brief.audience = _prompt_text("Audience", brief.audience)
                brief.revision_history.append("Edited audience.")
            elif field == "goal":
                brief.goal = _prompt_text("Goal", brief.goal)
                brief.revision_history.append("Edited goal.")
            elif field == "style":
                brief.style = _prompt_choice("Style", STYLE_CHOICES, brief.style)
                brief.revision_history.append(f"Edited style to {brief.style}.")
            elif field == "emphasis":
                emphasis = _prompt_text("Emphasis, comma separated", ", ".join(brief.emphasis))
                brief.emphasis = [item.strip() for item in emphasis.split(",") if item.strip()]
                brief.revision_history.append("Edited emphasis.")
            elif field == "narrative":
                brief.narrative_angle = _prompt_text("Narrative angle", brief.narrative_angle)
                brief.revision_history.append("Edited narrative.")
            elif field == "hero":
                brief.hero_message = _prompt_text("Hero message", brief.hero_message)
                brief.revision_history.append("Edited hero message.")
            elif field == "teaser":
                brief.teaser_heading = _prompt_text("Teaser heading", brief.teaser_heading)
                brief.revision_history.append("Edited teaser heading.")
            elif field == "table":
                brief.table_mode = _prompt_choice("Table rendering", ["auto", "image", "html"], brief.table_mode)
                brief.revision_history.append(f"Edited table mode to {brief.table_mode}.")
            elif field == "sections":
                sections = _prompt_multiline("Sections")
                if sections:
                    brief.sections = _extract_requested_sections(sections)
                    brief.revision_history.append("Edited section plan.")
            elif field == "notes":
                brief.notes = _prompt_text("Extra constraints or notes", brief.notes)
                brief.revision_history.append("Edited notes.")
            continue
        _revise_with_ai_or_rules(brief, manifest, command)


def _brief_from_freeform(manifest: PaperManifest, default_table_mode: str, text: str) -> ProjectBrief:
    brief = _default_brief(manifest, default_table_mode)
    clean = _clean_inline(text)
    brief.source_brief = text.strip()
    brief.audience = _extract_audience(text, brief.audience)
    brief.goal = _extract_goal(text, brief.goal)
    brief.style = _infer_style(text, brief.style)
    brief.emphasis = _extract_emphasis(text, brief.emphasis)
    brief.narrative_angle = _extract_narrative(text, brief.narrative_angle)
    brief.hero_message = _extract_hero_message(manifest, text, brief.hero_message)
    brief.teaser_heading = _extract_teaser_heading(manifest, text, brief.teaser_heading)
    brief.table_mode = _infer_table_mode(text, brief.table_mode)
    brief.sections = _extract_requested_sections(text)
    brief.notes = _extract_constraints(text, clean)
    return brief


def _refresh_wireframe(brief: ProjectBrief, manifest: PaperManifest) -> None:
    if brief.ascii_wireframe and brief.wireframe_source == "llm":
        return
    brief.ascii_wireframe = _render_ascii_wireframe(brief, manifest)
    brief.wireframe_source = "local"


def _render_ascii_wireframe(brief: ProjectBrief, manifest: PaperManifest) -> str:
    width = 76
    title = _ascii_trim(manifest.title, width - 4)
    theme = f"{brief.style.upper()} / {brief.table_mode.upper()} tables"
    claims = " | ".join(claim.label for claim in manifest.claims[:4]) or "claims"
    primary = brief.teaser_heading or "Primary figure"
    method = (
        " + ".join(c["name"] for c in manifest.method_components[:3])
        if manifest.method_components
        else "Method components"
    )
    sections = brief.sections or [
        "Hero with title, authors, links, contribution",
        "Primary figure teaser",
        "Abstract and central claims",
        "Method explanation",
        "Results and paper tables",
        "Citation",
    ]
    rows = [
        "+" + "-" * width + "+",
        f"| {_ascii_trim('HERO: ' + title, width - 2):<{width}} |",
        f"| {_ascii_trim(brief.hero_message, width - 2):<{width}} |",
        f"| {_ascii_trim('theme: ' + theme + '    links: Paper / Code', width - 2):<{width}} |",
        "+" + "-" * width + "+",
        f"| {_ascii_trim('TEASER: ' + primary, width - 2):<{width}} |",
        f"| {_ascii_trim('[large readable paper figure; used once]', width - 2):<{width}} |",
        "+" + "-" * width + "+",
        f"| {_ascii_trim('CLAIMS: ' + claims, width - 2):<{width}} |",
        f"| {_ascii_trim('STORY: ' + brief.narrative_angle, width - 2):<{width}} |",
        "+" + "-" * width + "+",
        f"| {_ascii_trim('METHOD: ' + method, width - 2):<{width}} |",
        f"| {_ascii_trim('RESULTS: cards + ' + _table_wireframe_label(brief), width - 2):<{width}} |",
        "+" + "-" * width + "+",
    ]
    for idx, section in enumerate(sections[:8], start=1):
        rows.append(f"| {_ascii_trim(str(idx) + '. ' + section, width - 2):<{width}} |")
    rows.append("+" + "-" * width + "+")
    return "\n".join(rows)


def _table_wireframe_label(brief: ProjectBrief) -> str:
    if brief.table_mode == "image":
        return "paper-cropped table screenshots"
    if brief.table_mode == "html":
        return "editable HTML tables"
    return "paper screenshots with HTML fallback"


def _build_plan_lines(brief: ProjectBrief, manifest: PaperManifest) -> list[str]:
    figure_policy = "Use the primary paper figure once as the large teaser."
    if "repeat" in brief.notes.lower():
        figure_policy = "Avoid repeated hero imagery; keep figures role-based and inspectable."
    if _should_render_promo_site(brief):
        result_policy = "Results: render a compact result strip and at most one supporting Table 2/Figure 2 paper asset."
        if any(word in _brief_text(brief) for word in ["no claim cards", "remove claim", "claim cards"]):
            result_policy = "Results: omit legacy claim cards; render the abstract plus a compact result strip."
        theme_target = "green-academic-promo" if "green" in _brief_text(brief) else "plan-driven promotional page"
        return [
            f"Theme: {brief.style} -> {theme_target}.",
            figure_policy,
            "Layout: hero, abstract, architecture, core idea, key results, why it matters, citation.",
            result_policy,
            f"Evidence assets: {len(manifest.figures)} figures and {sum(1 for table in manifest.tables if table.image)} cropped table screenshots detected.",
            "Write project_brief.json, site_plan.json, index.html, validation.json, and qa_report.md after confirmation.",
        ]
    return [
        f"Theme: {brief.style} -> {'dark-paper-showcase' if brief.style == 'dark' else 'style-referenced project page'}.",
        figure_policy,
        f"Results: render {len(manifest.claims[:4])} claim cards, then {brief.table_mode} table mode.",
        f"Evidence assets: {len(manifest.figures)} figures and {sum(1 for table in manifest.tables if table.image)} cropped table screenshots detected.",
        "Write project_brief.json, site_plan.json, index.html, validation.json, and qa_report.md after confirmation.",
    ]


def _apply_review_feedback(brief: ProjectBrief, feedback: str) -> None:
    text = feedback.strip()
    if not text:
        return
    lower = text.lower()
    before = _brief_signature(brief)
    wants_dark = any(word in lower for word in ["dark", "black", "midnight", "深色", "黑色", "暗色"])
    if wants_dark:
        brief.style = "dark"
    if any(word in lower for word in ["light", "white", "浅色", "白色"]):
        brief.style = "classic"
    if any(word in lower for word in ["technical", "dense", "技术", "更技术"]):
        brief.style = "technical"
    if any(word in lower for word in ["minimal", "simple", "简洁", "极简"]):
        brief.style = "minimal"
    if any(word in lower for word in ["visual", "showcase", "更像项目页", "展示"]) and not wants_dark:
        if brief.style != "dark":
            brief.style = "visual"
    if any(word in lower for word in ["screenshot", "cropped", "截图", "原表", "论文表格"]):
        brief.table_mode = "auto"
        _add_unique(brief.emphasis, "paper-original tables")
    if "html table" in lower or "可编辑表格" in lower:
        brief.table_mode = "html"
    if any(word in lower for word in ["result", "results", "结果", "指标"]):
        _add_unique(brief.emphasis, "quantitative results")
        _promote_section(brief, "Key results section with compact cards and paper-original evidence")
    if any(word in lower for word in ["claim card", "claim cards", "short label", "context"]):
        _add_unique(brief.emphasis, "claim cards with labels and context")
    if any(word in lower for word in ["figure 1", "architecture", "diagram", "架构", "主图", "结构图"]):
        _add_unique(brief.emphasis, "primary figure as the lead visual")
        _promote_section(brief, "Section centered on the primary paper figure")
    if any(word in lower for word in ["light card", "light cards", "readable", "可读"]):
        _add_unique(brief.emphasis, "light cards for paper assets")
    if any(word in lower for word in ["component card", "component cards", "method card", "步骤", "组件"]):
        _add_unique(brief.emphasis, "method component cards")
        _promote_section(brief, "Method component cards walking through the paper's parts")
    if any(word in lower for word in ["hero", "首屏", "首页"]):
        _promote_section(brief, "Hero section with title, authors, contribution, links, and key result badges")
    if any(word in lower for word in ["impact", "foundational", "影响", "意义"]):
        _promote_section(brief, "Broader impact section discussing implications")
    if "why it matters" in lower:
        _promote_section(brief, "Why it matters section explaining the significance of the contribution")
    if any(word in lower for word in ["table", "tables", "表格"]):
        _promote_section(brief, "Results evidence section using paper-cropped table screenshots")
    if any(word in lower for word in ["less", "reduce", "简化", "不要太多", "克制", "restrained"]):
        _add_unique(brief.emphasis, "restrained visual hierarchy")
    if any(word in lower for word in ["bigger", "large", "放大", "更大"]):
        _add_unique(brief.emphasis, "large readable figures")
    if any(word in lower for word in ["not neon", "不要霓虹", "no neon"]):
        text = f"{text} Keep accents restrained rather than neon."
    if "hero" in lower and any(word in lower for word in ["short", "shorter", "简短", "压缩"]):
        brief.hero_message = _limit_text(brief.hero_message, 115)
    brief.notes = f"{brief.notes}\nReview feedback: {text}".strip()
    after = _brief_signature(brief)
    if before == after:
        brief.revision_history.append(f"Recorded feedback: {_limit_text(text, 120)}")
    else:
        brief.wireframe_source = "local"
        brief.revision_history.append(f"Applied feedback: {_limit_text(text, 120)}")


def _revise_with_ai_or_rules(brief: ProjectBrief, manifest: PaperManifest, feedback: str) -> None:
    if _can_call_design_llm():
        try:
            updated = _revise_brief_with_llm(brief, manifest, feedback)
        except Exception as exc:
            brief.revision_history.append(f"LLM revision failed; used local planner: {exc}")
        else:
            _merge_llm_brief(brief, updated)
            brief.revision_history.append(f"AI revised plan from feedback: {_limit_text(feedback, 120)}")
            return
    _apply_review_feedback(brief, feedback)


def _can_call_design_llm() -> bool:
    return bool(LLM_API_KEY and LLM_BASE_URL and LLM_MODEL)


HTML_PROMPT_PATH = Path(__file__).parent / "prompts" / "html_generate_agent.txt"


def _generate_llm_site_with_qa(
    manifest: PaperManifest,
    plan: SitePlan,
    output_dir: Path,
    table_mode: str = "auto",
    brief: ProjectBrief | None = None,
    max_retries: int = 2,
    variant_seed: int | None = None,
) -> tuple[str, "QAResult"]:
    """Generate a full page with the LLM, then validate; on QA errors, feed them back and regenerate."""
    feedback = ""
    html = ""
    qa: QAResult | None = None
    for attempt in range(max_retries + 1):
        html = _render_llm_site(
            manifest, plan, output_dir, table_mode=table_mode, brief=brief,
            qa_feedback=feedback, variant_seed=variant_seed,
        )
        qa = validate_site(html, output_dir, manifest, brief=brief, plan=plan, strict_alignment=False)
        if qa.ok:
            if attempt:
                print(f"[agent] LLM renderer passed QA after {attempt} revision(s).")
            break
        if attempt < max_retries:
            print(f"[agent] LLM renderer QA attempt {attempt + 1} found {len(qa.errors)} error(s); regenerating.")
            feedback = "Previous attempt failed validation. Fix these issues: " + "; ".join(qa.errors)
        else:
            print(f"[agent] LLM renderer still has {len(qa.errors)} QA error(s) after {max_retries} retries; keeping last version.")
    assert qa is not None
    return html, qa


_VARIANT_BIASES = [
    "EDITORIAL / MAGAZINE: a print-magazine art direction — a bold masthead, serif or high-contrast display "
    "type for headings, multi-column text moments, pull quotes lifted from the abstract, generous margins, "
    "and figures treated as full-bleed editorial spreads. Calm, sophisticated, paper-like palette.",
    "PRODUCT LANDING PAGE: a polished SaaS/product launch feel — a punchy value-proposition hero, vivid accent "
    "gradient, rounded feature cards, big benefit-driven stat callouts, clear section bands with alternating "
    "backgrounds, and confident call-to-action buttons. Bright, modern, marketing-forward.",
    "TERMINAL / TECHNICAL: a developer/console aesthetic — dark canvas, mono or mono-accented type, hairline "
    "rules, code-block styling, a compact information-dense grid, subtle neon or phosphor accent. Reads like "
    "elite engineering documentation, not a brochure.",
    "ACADEMIC POSTER: a conference-poster layout — a strong title band, a clear column/zone structure, the "
    "key figure as a central anchor, numbered findings, restrained scholarly palette with one accent, and "
    "tight figure-caption pairing. Authoritative and structured.",
    "MINIMAL ARCHIVE: extreme restraint — near-monochrome, a single hairline accent, enormous whitespace, "
    "small understated type, almost no cards or shadows, content carried by typography and rhythm alone. "
    "Quiet, gallery-like, confident.",
    "DATA-VISUAL / DASHBOARD: an analytics dashboard art direction — oversized numerals, chart-like framing "
    "around metrics and tables, a tight modular grid, badge/tag accents, and results treated as the visual "
    "centerpiece. Crisp, quantitative, high signal density.",
]


def _variant_directive(variant_seed: int | None) -> str:
    """Return a design-paradigm instruction. None => stable/reproducible (no forced variation)."""
    if variant_seed is None:
        return (
            "(no specific variant requested — invent the design concept that best fits this paper; "
            "be deterministic and consistent.)"
        )
    paradigm = _VARIANT_BIASES[variant_seed % len(_VARIANT_BIASES)]
    return (
        f"This is design variant #{variant_seed}. Commit fully to the following DESIGN LANGUAGE as the art "
        f"direction for the whole page — its palette, typography, spacing, section shapes, and overall mood: "
        f"{paradigm} Express this paradigm consistently from hero to footer; another variant of the same paper "
        "should look like it came from a different studio. Keep all facts, images, links, and hard constraints "
        "identical — only the visual language and composition change."
    )


def _render_llm_site(
    manifest: PaperManifest,
    plan: SitePlan,
    output_dir: Path,
    table_mode: str = "auto",
    brief: ProjectBrief | None = None,
    qa_feedback: str = "",
    variant_seed: int | None = None,
) -> str:
    """Render a self-contained page by asking the LLM to design from the verified manifest."""
    manifest_payload = _manifest_for_llm(manifest, output_dir=output_dir)
    template = HTML_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{manifest_json}", _json_dumps(manifest_payload))
        .replace("{brief_json}", _json_dumps(asdict(brief)) if brief else "{}")
        .replace("{plan_json}", _json_dumps(asdict(plan)))
        .replace("{table_mode}", table_mode)
        .replace("{qa_feedback}", qa_feedback or "(none — this is the first attempt)")
        .replace("{variant_directive}", _variant_directive(variant_seed))
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are Paper2HTML's page designer. You build a single self-contained academic project "
                "page from a verified manifest. Output only valid, complete HTML — no markdown fences, no commentary."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    return _call_html_llm(messages)


def _manifest_for_llm(manifest: PaperManifest, output_dir: Path) -> dict[str, object]:
    """Project the manifest into a fact-only payload, exposing ONLY images that actually exist on disk.

    This keeps the LLM from referencing image files that were never copied, which would otherwise
    trip validate_site's missing-image check.
    """
    figures = []
    for fig in manifest.figures:
        if not (fig.exists or (output_dir / fig.file).exists()):
            continue
        entry = {"file": fig.file, "caption": _limit_text(fig.caption, 300), "role": fig.role, "section": fig.section}
        entry.update(_image_dims_payload(output_dir / fig.file))
        figures.append(entry)
    tables = []
    for table in manifest.tables:
        image_ok = bool(table.image) and (output_dir / table.image).exists()
        entry = {
            "caption": _limit_text(table.caption, 300),
            "image": table.image if image_ok else "",
            "html": _normalize_table_html(table.html) if table.html else "",
            "page": table.page,
        }
        if image_ok:
            entry.update(_image_dims_payload(output_dir / table.image))
        tables.append(entry)
    return {
        "title": manifest.title,
        "authors": manifest.authors,
        "affiliations": manifest.affiliations,
        "abstract": _limit_text(manifest.abstract, 1200),
        "links": asdict(manifest.links),
        "claims": [asdict(claim) for claim in manifest.claims],
        "figures": figures,
        "tables": tables,
        "method_components": manifest.method_components,
        "bibtex": manifest.bibtex,
    }


def _is_anthropic_endpoint() -> bool:
    """Detect an Anthropic-native gateway (uses /v1/messages, x-api-key, content blocks)."""
    return "anthropic" in LLM_BASE_URL.lower() or "claude" in LLM_MODEL.lower()


def _call_html_llm(messages: list[dict], max_tokens: int = 32000, transport_retries: int = 2) -> str:
    """Call the LLM for full-page HTML generation and return cleaned HTML text (no JSON parsing).

    Auto-detects the API dialect from the configured base URL / model:
      - Anthropic-native gateways  -> POST {base}/v1/messages  (x-api-key, system separated, content blocks)
      - OpenAI-compatible gateways -> POST {base}/chat/completions  (Bearer, choices[].message.content)
    Retries transient gateway failures (5xx / connection errors) before giving up.
    """
    anthropic = _is_anthropic_endpoint()
    if anthropic:
        base_url = LLM_BASE_URL.rstrip("/")
        url = f"{base_url}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": LLM_API_KEY,
            "anthropic-version": "2023-06-01",
        }
        system_text = " ".join(m["content"] for m in messages if m["role"] == "system")
        chat = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        payload = {
            "model": LLM_MODEL,
            "max_tokens": max_tokens,
            "messages": chat,
        }
        if system_text:
            payload["system"] = system_text
    else:
        base_url = _normalize_llm_base_url(LLM_BASE_URL)
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        }
        payload = {
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": max_tokens,
        }

    body = json.dumps(payload).encode("utf-8")
    last_error = ""
    for attempt in range(transport_retries + 1):
        try:
            resp = requests.post(url, headers=headers, data=body, timeout=LLM_REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"connection error: {exc}"
        else:
            if resp.status_code == 200:
                return _clean_llm_html(_extract_llm_text(resp.json(), anthropic))
            last_error = f"LLM API error {resp.status_code}: {_limit_text(resp.text, 240)}"
            if resp.status_code < 500 and resp.status_code != 429:
                break  # client error (4xx) won't be fixed by retrying
        if attempt < transport_retries:
            print(f"[agent] HTML LLM call failed ({last_error}); retry {attempt + 1}/{transport_retries}.")
    raise RuntimeError(last_error or "LLM API call failed")


def _extract_llm_text(data: dict, anthropic: bool) -> str:
    if anthropic:
        blocks = data.get("content") or []
        return "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
    return data["choices"][0]["message"]["content"]


def _clean_llm_html(html: str) -> str:
    html = re.sub(r"^```html?\s*\n?", "", html.strip())
    html = re.sub(r"\n?```\s*$", "", html.strip())
    if not html.lower().startswith("<!doctype"):
        html = "<!DOCTYPE html>\n" + html
    return html


def _revise_brief_with_llm(brief: ProjectBrief, manifest: PaperManifest, feedback: str) -> dict[str, object]:
    prompt = {
        "task": "Revise a paper project-page generation brief from terminal review feedback.",
        "rules": [
            "Return only JSON.",
            "Do not invent unsupported paper claims.",
            "Keep the plan implementable by a deterministic HTML renderer.",
            "Use concise English values.",
            "For style use one of: classic, visual, technical, minimal, dark.",
            "For table_mode use one of: auto, image, html.",
            "Update sections and ascii_wireframe to reflect the feedback.",
        ],
        "paper": {
            "title": manifest.title,
            "claims": [asdict(claim) for claim in manifest.claims[:4]],
            "figures": [asdict(fig) for fig in manifest.figures[:6]],
            "tables": [
                {"caption": table.caption, "has_image": bool(table.image), "page": table.page}
                for table in manifest.tables[:4]
            ],
        },
        "current_brief": asdict(brief),
        "feedback": feedback,
        "output_schema": {
            "audience": "string",
            "goal": "string",
            "style": "classic|visual|technical|minimal|dark",
            "emphasis": ["string"],
            "narrative_angle": "string",
            "hero_message": "string",
            "teaser_heading": "string",
            "table_mode": "auto|image|html",
            "figure_strategy": "string",
            "sections": ["string"],
            "notes": "string",
            "ascii_wireframe": "string",
        },
    }
    data = _call_design_llm(json.dumps(prompt, ensure_ascii=False, indent=2))
    if not isinstance(data, dict):
        raise ValueError("LLM did not return a JSON object")
    return data


def _call_design_llm(prompt: str) -> object:
    base_url = _normalize_llm_base_url(LLM_BASE_URL)
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Paper2HTML's planning agent. You revise structured project-page briefs "
                    "and ASCII wireframes from user review feedback. Return only valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4000,
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload).encode("utf-8"), timeout=LLM_REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM API error {resp.status_code}: {_limit_text(resp.text, 240)}")
    content = resp.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())
    return json.loads(content)


def _normalize_llm_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.path in ("", "/"):
        return f"{normalized}/v1"
    return normalized


def _merge_llm_brief(brief: ProjectBrief, data: dict[str, object]) -> None:
    if isinstance(data.get("audience"), str):
        brief.audience = str(data["audience"])
    if isinstance(data.get("goal"), str):
        brief.goal = str(data["goal"])
    if data.get("style") in STYLE_CHOICES:
        brief.style = str(data["style"])
    if isinstance(data.get("emphasis"), list):
        brief.emphasis = [str(item).strip() for item in data["emphasis"] if str(item).strip()][:12]
    if isinstance(data.get("narrative_angle"), str):
        brief.narrative_angle = str(data["narrative_angle"])
    if isinstance(data.get("hero_message"), str):
        brief.hero_message = str(data["hero_message"])
    if isinstance(data.get("teaser_heading"), str):
        brief.teaser_heading = str(data["teaser_heading"])
    if data.get("table_mode") in {"auto", "image", "html"}:
        brief.table_mode = str(data["table_mode"])
    if isinstance(data.get("figure_strategy"), str):
        brief.figure_strategy = str(data["figure_strategy"])
    if isinstance(data.get("sections"), list):
        brief.sections = [str(item).strip() for item in data["sections"] if str(item).strip()][:8]
    if isinstance(data.get("notes"), str):
        brief.notes = str(data["notes"])
    if isinstance(data.get("ascii_wireframe"), str):
        brief.ascii_wireframe = str(data["ascii_wireframe"])
        brief.wireframe_source = "llm"


def _brief_signature(brief: ProjectBrief) -> tuple[object, ...]:
    return (
        brief.style,
        tuple(brief.emphasis),
        brief.table_mode,
        tuple(brief.sections),
        brief.hero_message,
        brief.teaser_heading,
    )


def _add_unique(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


def _promote_section(brief: ProjectBrief, section: str) -> None:
    if section in brief.sections:
        brief.sections.remove(section)
    brief.sections.insert(0, section)
    brief.sections = brief.sections[:8]


def _ascii_trim(text: str, limit: int) -> str:
    text = _clean_inline(text)
    text = text.replace("|", "/")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _extract_audience(text: str, default: str) -> str:
    match = re.search(r"\baudience\s+is\s+(.+?)(?:\.|\n|$)", text, re.IGNORECASE)
    if match:
        return _limit_text(match.group(1), 220)
    match = re.search(r"\bintended\s+for\s+(.+?)(?:\.|\n|$)", text, re.IGNORECASE)
    if match:
        return _limit_text(match.group(1), 220)
    return default


def _extract_goal(text: str, default: str) -> str:
    match = re.search(r"\bbuild\s+(.+?)(?:\.|\n|$)", text, re.IGNORECASE)
    if match:
        return _limit_text("Build " + match.group(1), 220)
    match = re.search(r"\bgoal\s*(?:is|:)\s*(.+?)(?:\.|\n|$)", text, re.IGNORECASE)
    if match:
        return _limit_text(match.group(1), 220)
    return default


def _infer_style(text: str, default: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["dark", "black", "midnight", "深色", "黑色", "暗色"]):
        return "dark"
    if any(word in lower for word in ["visual", "showcase", "hero", "project-page", "project page"]):
        return "visual"
    if any(word in lower for word in ["technical", "dense", "engineer", "researcher"]):
        return "technical"
    if any(word in lower for word in ["minimal", "simple", "plain"]):
        return "minimal"
    if any(word in lower for word in ["classic", "academic", "faithful"]):
        return "classic"
    return default


def _extract_emphasis(text: str, default: list[str]) -> list[str]:
    lower = text.lower()
    items: list[str] = []
    signals = [
        ("central contribution", "central contribution"),
        ("architecture", "architecture figure as primary visual"),
        ("figure 1", "primary figure as the lead visual"),
        ("method", "method components"),
        ("result", "quantitative results"),
        ("table", "paper-original tables"),
        ("impact", "broader impact"),
        ("ablation", "ablation results"),
        ("benchmark", "benchmark results"),
    ]
    for needle, label in signals:
        if needle in lower and label not in items:
            items.append(label)
    return items or default


def _extract_narrative(text: str, default: str) -> str:
    patterns = [
        r"storytelling should be (.+?)(?:\.|\n|$)",
        r"narrative(?: angle)?\s*(?:is|:)\s*(.+?)(?:\.|\n|$)",
        r"central contribution:\s*(.+?)(?:\.|\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _limit_text(match.group(1), 240)
    return default


def _extract_hero_message(manifest: PaperManifest, text: str, default: str) -> str:
    match = re.search(r"one-sentence contribution\s*(?:,|:)?\s*(.+?)(?:\.|\n|$)", text, re.IGNORECASE)
    if match and not any(word in match.group(1).lower() for word in ["badge", "figure", "title", "authors"]):
        return _limit_text(match.group(1), 180)
    return default


def _extract_teaser_heading(manifest: PaperManifest, text: str, default: str) -> str:
    # Honor an explicit user request to lead with a specific figure; otherwise keep the default
    # (which is derived generically from the primary figure caption in _default_brief).
    match = re.search(r"(?:use|lead with|teaser)[^.\n]*\bfigure\s+(\d+)\b", text, re.IGNORECASE)
    if match:
        return f"Figure {match.group(1)}"
    return default


def _infer_table_mode(text: str, default: str) -> str:
    lower = text.lower()
    if "cropped table" in lower or "paper-original table" in lower or "faithful reuse" in lower:
        return "auto"
    if "image table" in lower or "screenshot" in lower:
        return "image"
    if "html table" in lower:
        return "html"
    return default


def _extract_requested_sections(text: str) -> list[str]:
    sections: list[str] = []
    for line in text.splitlines():
        match = re.match(r"\s*(?:[-*]\s*)?(\d+)[\.)]\s+(.+)", line)
        if match:
            sections.append(match.group(2).strip())
    if sections:
        return sections[:8]
    lower = text.lower()
    candidates = [
        ("hero", "Hero section with title, authors, contribution, result badges, and the primary figure"),
        ("core idea", "Core idea section explaining the paper's central contribution in plain language"),
        ("method", "Method section walking through the paper's components"),
        ("architecture", "Architecture section explaining the model/system structure"),
        ("key results", "Key results section with compact cards and paper-original tables"),
        ("broader impact", "Broader impact section discussing implications"),
        ("citation", "Citation and paper information section"),
    ]
    for needle, section in candidates:
        if needle in lower:
            sections.append(section)
    return sections[:8]


def _extract_constraints(text: str, fallback: str) -> str:
    match = re.search(r"(?:extra constraints|constraints|visual style)\s*(?:or notes)?\s*(?:should be|:)\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    if match:
        return _limit_text(match.group(1), 900)
    return _limit_text(fallback, 900)


def _prompt_text(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = _clean_prompt_value(input(f"{label}{suffix}: "))
    except EOFError as exc:
        if default:
            return default
        raise SystemExit(f"{label} is required in interactive mode.") from exc
    return value or default


def _prompt_multiline(label: str) -> str:
    try:
        first = _clean_prompt_value(input(f"{label}: "))
    except EOFError:
        return ""
    if not first:
        return ""
    lines = [first]
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == "END":
            break
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _clean_prompt_value(value: str) -> str:
    value = value.strip().replace("\ufeff", "")
    for marker in ("ï»¿", "ďťż"):
        value = value.replace(marker, "")
    return value.strip().strip('"').strip("'")


def _clean_path_prompt(value: str) -> str:
    value = _clean_prompt_value(value)
    value = re.sub(r"(?<![A-Za-z])(?:\u9518\u7e00|\u569c\u6fc0):", "E:", value)
    match = re.search(r"(?:[A-Za-z]:[\\/]|\.{1,2}[\\/]|~(?:[\\/]|$))", value)
    if match and 0 < match.start() <= 8:
        value = value[match.start() :]
    elif match and re.match(r"^[A-Za-z]:[\\/]", value):
        positions = [m.start() for m in re.finditer(r"[A-Za-z]:[\\/]", value)]
        if len(positions) > 1:
            value = value[positions[-1] :]
    if value.startswith(("\\", "/")) and not value.startswith(("\\\\", "//")):
        value = "." + value
    return value


def _resolve_existing_path(value: str) -> Path:
    raw = str(value)
    cleaned = _clean_path_prompt(raw)
    candidates: list[str] = []
    drive_positions = [match.start() for match in re.finditer(r"[A-Za-z]:[\\/]", raw)]
    candidates.extend(raw[pos:] for pos in drive_positions)
    if drive_positions:
        candidates.append(raw[drive_positions[-1] :])
    candidates.append(cleaned)
    candidates.extend(match.group(0) for match in re.finditer(r"[A-Za-z]:[\\/][^\r\n]+", raw))
    candidates.extend(match.group(0) for match in re.finditer(r"\.{1,2}[\\/][^\r\n]+", raw))
    seen: set[str] = set()
    for candidate in candidates:
        candidate = _clean_path_prompt(candidate)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate).expanduser()
        if path.exists():
            return path.resolve()
    return Path(cleaned).expanduser().resolve()


def _prompt_bool(label: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        value = input(f"{label} [{hint}]: ").strip().lower()
    except EOFError:
        return default
    if not value:
        return default
    return value in {"y", "yes", "1", "true", "t"}


def _prompt_choice(label: str, choices: list[str], default: str) -> str:
    choice_text = "/".join(choices)
    while True:
        try:
            value = input(f"{label} ({choice_text}) [{default}]: ").strip().lower() or default
        except EOFError:
            return default
        if value in choices:
            return value
        print(f"Please choose one of: {choice_text}")


def _interactive_args(args: argparse.Namespace) -> argparse.Namespace:
    _print_agent_method()
    print("[Paper2HTML-Agent] Project setup")
    args.input = _clean_path_prompt(_prompt_text("Input PDF or Markdown", args.input or ""))
    if not args.input:
        raise SystemExit("Input path is required.")
    args.input = str(_resolve_existing_path(args.input))

    source = Path(args.input)
    default_images = args.images or ""
    if not default_images and source.suffix.lower() in {".md", ".markdown"}:
        if (source.parent / "images").exists():
            default_images = str(source.parent / "images")
        elif (source.parent / "parsed" / "images").exists():
            default_images = str(source.parent / "parsed" / "images")
        args.images = _clean_path_prompt(_prompt_text("Images directory", default_images))
    elif source.suffix.lower() == ".pdf":
        args.images = ""
        guessed = _guess_parsed_dir(source)
        if guessed:
            print(f"Images directory: auto, using parsed cache at {guessed}")
        else:
            print("Images directory: auto, will use images produced by PDF parsing")
    else:
        args.images = _clean_path_prompt(_prompt_text("Images directory", default_images))

    default_output = args.output or str(default_output_root(source) / f"{source.stem}_agent")
    args.output = _clean_path_prompt(_prompt_text("Output directory", default_output))
    args.paper_url = _prompt_text("Paper URL", args.paper_url or "")
    args.code_url = _prompt_text("Code URL", args.code_url or "")
    args.lite = _prompt_bool("Use MinerU lite parser", args.lite)
    reuse = _prompt_bool("Reuse existing parsed/full.md when available", not args.no_reuse_parsed)
    args.no_reuse_parsed = not reuse
    args.no_copy_images = not _prompt_bool("Copy referenced images into output", not args.no_copy_images)

    print("")
    print("[Paper2HTML-Agent] Inspecting paper before asking design questions...")
    manifest, parsed_dir, _image_roots = _inspect_input_for_brief(
        input_path=args.input,
        output_dir=args.output,
        images_dir=args.images,
        use_lite=args.lite,
        reuse_parsed=not args.no_reuse_parsed,
        paper_url=args.paper_url,
        code_url=args.code_url,
    )
    for line in _diagnose_manifest(manifest, parsed_dir):
        print(f"  - {line}")

    args.mode = _prompt_choice("Page mode", ["showcase", "reader"], args.mode)
    args.renderer = _prompt_choice(
        "Renderer (template=deterministic, llm=free LLM design + QA auto-repair)",
        ["template", "llm"],
        getattr(args, "renderer", "template"),
    )
    args.brief = _collect_brief(manifest, args.table_mode)
    args.table_mode = args.brief.table_mode
    return args


def _load_brief(path: str | None) -> ProjectBrief | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    valid = {item.name for item in fields(ProjectBrief)}
    filtered = {key: value for key, value in data.items() if key in valid}
    return ProjectBrief(**filtered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a manifest-driven paper project page.")
    parser.add_argument("input", nargs="?", help="Input PDF or Markdown file")
    parser.add_argument("-o", "--output", help="Output directory")
    parser.add_argument("--images", help="Directory containing parsed images")
    parser.add_argument("--mode", choices=["showcase", "reader"], default="showcase")
    parser.add_argument("--table-mode", choices=["auto", "image", "html"], default="auto")
    parser.add_argument(
        "--renderer",
        choices=["template", "llm"],
        default="template",
        help="HTML generation: template=deterministic template (default), llm=LLM full-page generation with QA auto-repair",
    )
    parser.add_argument("--brief", help="Reuse a confirmed project_brief.json")
    parser.add_argument("--paper-url", help="Override paper URL")
    parser.add_argument("--code-url", help="Override code URL")
    parser.add_argument("-i", "--interactive", action="store_true", help="Prompt for generation options")
    parser.add_argument("--lite", action="store_true", help="Use MinerU lightweight API for PDF parsing")
    parser.add_argument("--no-reuse-parsed", action="store_true", help="Do not reuse existing parsed/full.md")
    parser.add_argument("--no-copy-images", action="store_true", help="Do not copy images into the output directory")
    parser.add_argument(
        "--rotate",
        help='Rotate sideways figures clockwise, by figure number: "3:90,5:90" (degrees 90/180/270). Use the numbers from the interactive "figures" list.',
    )
    parser.add_argument(
        "--variant",
        type=int,
        default=None,
        help="LLM renderer only: pick a distinct layout variant (e.g. 1/2/3) for the same paper. Omit for a stable, reproducible layout.",
    )
    args = parser.parse_args(argv)
    args.brief = _load_brief(args.brief)
    if args.brief and args.table_mode == "auto":
        args.table_mode = args.brief.table_mode

    if args.interactive or not args.input:
        args = _interactive_args(args)

    artifacts = build_agent_page(
        input_path=args.input,
        output_dir=args.output,
        images_dir=args.images,
        mode=args.mode,
        table_mode=args.table_mode,
        brief=args.brief,
        use_lite=args.lite,
        reuse_parsed=not args.no_reuse_parsed,
        paper_url=args.paper_url,
        code_url=args.code_url,
        copy_images=not args.no_copy_images,
        renderer=args.renderer,
        rotate_spec=args.rotate,
        variant=args.variant,
    )

    print("[Paper2HTML-Agent] Done")
    for key, value in artifacts.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
