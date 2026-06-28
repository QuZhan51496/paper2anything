#!/usr/bin/env python
"""parse_pdf — parse + deterministic extraction (mechanical, gate 1).

PDF → MinerU parse → normalize → extract_manifest (title/authors/abstract/links/claims/
figures/tables/method/bibtex; appendix filtered; what can't be extracted is left empty for you to fill) → copy page figures.

Outputs (under --workdir, i.e. <pdf-dir>/.paper2anything/html/<stem>/):
  clean.md       normalized markdown (for you to read through)
  manifest.json  deterministically extracted facts (you may only author from the real material here)
  parsed/        MinerU raw parse (includes full.md for reuse on re-run, and images/ with all crops)
  images/        the figures the page references (referenced by you as images/<name>, sibling to index.html)
  logs/parse_pdf_result.json

Usage:
  python parse_pdf.py <paper.pdf> --workdir <pdf-dir>/.paper2anything/html/<stem> [--paper-url URL] [--code-url URL] [--lite]
"""
import argparse
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: F401  uniformly load the package-root .env
from utils import (
    resolve_workspace, save_json, save_stage_result, print_stage_header,
    print_info, print_success, print_warning, print_error,
)
from lib import core


def run(input_path: str, workdir: str, *, paper_url=None, code_url=None,
        use_lite: bool = False, copy_images: bool = True) -> dict:
    print_stage_header("MinerU parse + deterministic extraction (gate 1)")
    ws = resolve_workspace(workdir)
    root = ws["root"]

    source = Path(input_path).expanduser().resolve()
    if not source.exists():
        print_error(f"Input does not exist: {source}")
        return {"status": "failed", "error": f"Input does not exist: {source}"}

    # Parse (PDF goes through MinerU; MD is read directly). reuse_parsed=True: if parsed/full.md exists, skip the cloud parse.
    print_info(f"Parsing input: {source.name}")
    raw_markdown, parsed_images, parsed_dir = core._load_or_parse_source(
        source, root, use_lite=use_lite, reuse_parsed=True
    )
    # Write full.md for reuse on re-run (not dependent on an external pipeline's output)
    if parsed_dir is not None:
        Path(parsed_dir).mkdir(parents=True, exist_ok=True)
        (Path(parsed_dir) / "full.md").write_text(raw_markdown, encoding="utf-8")

    # HD re-crop: MinerU's extracted figures are downsampled (a bit blurry). Before copying figures to images/, use the
    # bbox from layout.json to re-crop from the pdftoppm 300dpi full page, overwriting the referenced source figures
    # under parsed/ in place (without changing filenames/manifest). Run only for PDF input with a parsed_dir; skip for MD input (no PDF).
    if parsed_dir is not None and source.suffix.lower() == ".pdf":
        core._recrop_inplace(source, Path(parsed_dir))

    markdown = core.normalize_markdown(raw_markdown)
    (root / "clean.md").write_text(markdown, encoding="utf-8")
    print_success(f"clean.md written ({len(markdown)} chars)")

    # Deterministic extraction (gate 1)
    image_roots = core._candidate_image_roots(source, root, None)
    manifest = core.extract_manifest(
        markdown, source=source, image_roots=image_roots,
        paper_url=paper_url, code_url=code_url, parsed_dir=parsed_dir,
    )

    # Copy the figures the page references into root/images/, so your images/<name> resolves and QA doesn't report missing figures
    copied = set()
    if copy_images:
        copied = core.copy_manifest_images(manifest, root, image_roots, parsed_images)
        for fig in manifest.figures:
            fig.exists = fig.file in copied or (root / fig.file).exists()

    save_json(asdict(manifest), root / "manifest.json")

    # ── Summary (fields that couldn't be extracted are left empty for you to fill during authoring; not an error) ──
    print_success(f"Paper title: {manifest.title}")
    if not manifest.abstract:
        print_warning("No abstract extracted (the paper may have no Abstract heading); left empty for you to fill")
    if not manifest.authors:
        print_warning("No authors extracted (a limit of deterministic extraction); left empty for you to fill")
    if not manifest.links.paper:
        print_info("Paper link not determined automatically (no arxiv assumption); re-run with --paper-url if needed")
    print_info(f"authors {len(manifest.authors)} | abstract {len(manifest.abstract)} chars | "
               f"figures {len(manifest.figures)} | tables {len(manifest.tables)} | claims {len(manifest.claims)}")
    print_info(f"Copied {len(copied)} page figures → {root / 'images'}")
    print_info(f"Outputs saved to: {root}")

    result = {
        "status": "success",
        "workdir": str(root),
        "clean_md": str(root / "clean.md"),
        "manifest": str(root / "manifest.json"),
        "title": manifest.title,
        "counts": {
            "authors": len(manifest.authors),
            "abstract_chars": len(manifest.abstract),
            "figures": len(manifest.figures),
            "tables": len(manifest.tables),
            "claims": len(manifest.claims),
            "images_copied": len(copied),
        },
        "links": asdict(manifest.links),
    }
    save_stage_result(result, "parse_pdf", ws)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="paper2html parse_pdf: parse + deterministic extraction")
    ap.add_argument("input", help="paper PDF (or already-parsed Markdown)")
    ap.add_argument("--workdir", required=True, help="working directory (<pdf-dir>/.paper2anything/html/<stem>)")
    ap.add_argument("--paper-url", default=None, help="paper canonical link (left empty if omitted; no arxiv assumption)")
    ap.add_argument("--code-url", default=None, help="code repository link override")
    ap.add_argument("--lite", action="store_true", help="use the MinerU lite parsing API")
    ap.add_argument("--no-copy-images", action="store_true", help="don't copy figures into images/")
    args = ap.parse_args()

    result = run(
        args.input, args.workdir,
        paper_url=args.paper_url, code_url=args.code_url,
        use_lite=args.lite, copy_images=not args.no_copy_images,
    )
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
