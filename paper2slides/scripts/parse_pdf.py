"""
parse_pdf.py — Stage 1: PDF parse (MinerU cloud API)

Input: paper.pdf
Outputs (written to workdir):
  - paper_meta.json     title/authors/sections/figures/tables/equations (produced by mineru_parser)
  - figures_index.json  three lists: captions / hi-res crop index / page_renders
  - pages/page-NN.png   full-page PNG (pdftoppm render, default 300 dpi, for hi-res crops and equation crop source)
  - hi-res figure/table crops

Parsing uniformly goes through MinerU cloud; requires MINERU_API_TOKEN. Errors out on failure.

CLI:
    python scripts/parse_pdf.py <paper.pdf> [--output <out.pptx>] [--dpi 300]
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
    """Full-page render. Default 300 dpi (the clarity threshold for academic tables' small
    text), with -hide-annotations to remove the hyperlink green boxes that paper PDFs ship
    with ([N] citations / cross-references)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), "-hide-annotations",
         str(pdf), str(prefix)],
        check=True, capture_output=True,
    )
    return sorted(out_dir.glob("page-*.png"))


def _page_renders(workdir: Path, pages_png: list[Path]) -> list[dict]:
    """Extract the page number from the already-rendered page-NN.png filenames, returning [{page, path}] in ascending page order."""
    out: list[dict] = []
    for png in pages_png:
        m = re.search(r"page-(\d+)\.png$", png.name)
        if m:
            out.append({"page": int(m.group(1)),
                        "path": str(png.relative_to(workdir))})
    return sorted(out, key=lambda x: x["page"])


def _run_mineru(ws, args, token: str) -> dict:
    """Stage 1: MinerU cloud API parse. Produces paper_meta.json + figures_index.json + hi-res crops in one shot."""
    # local import: mineru-specific parsing dependencies (requests/zipfile chain) loaded on demand
    sys.path.insert(0, str(Path(__file__).parent))
    from lib import mineru_client, mineru_parser  # noqa: E402

    _need("pdftoppm")  # still need full-page PNGs (hi-res crops and future equation crop source)

    paper_path = ws.paper_path
    size_mb = paper_path.stat().st_size / (1024 * 1024)
    print(f"[mineru] uploading {paper_path.name} ({size_mb:.1f} MB) "
          f"to mineru.net cloud API", file=sys.stderr)

    # 1) submit the task (local PDF goes through file-urls/batch)
    task_id = mineru_client.submit_local_pdf(paper_path, token)
    print(f"[mineru] task_id = {task_id}", file=sys.stderr)

    # 2) poll
    result = mineru_client.poll_task(task_id, token, timeout_s=300)
    state = result.get("state", "")
    if state != "done":
        raise RuntimeError(
            f"task {task_id} ended with state={state!r}: "
            f"{result.get('err_msg', '(no err_msg)')}")
    zip_url = result.get("full_zip_url")
    if not zip_url:
        raise RuntimeError(f"task {task_id} done but no full_zip_url: {result}")

    # 3) download + unzip
    zip_bytes = mineru_client.download_zip(zip_url)
    unzipped = ws.workdir / "_mineru"
    mineru_client.extract_zip(zip_bytes, unzipped)

    # 4) render full-page PNGs (mineru doesn't give hi-res full pages; we need this to crop hi-res ourselves)
    pages_png = render_pages(ws.paper_path, ws.pages_dir, dpi=args.dpi)

    # 5) call the parser to write outputs
    page_renders = _page_renders(ws.workdir, pages_png)
    pm_path, fi_path = mineru_parser.write_outputs(
        unzipped_dir=unzipped,
        workdir=ws.workdir,
        source_pdf=str(ws.paper_path),
        page_renders=page_renders,
        mineru_task_id=task_id,
    )

    # return simple statistics
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
                   help="(the final .pptx path passed through to workdir; this stage does not directly produce a .pptx)")
    p.add_argument(
        "--dpi", type=int, default=300,
        help=("full-page PNG render resolution (default 300, clamped 100-600). "
              "The clarity threshold for academic papers' table small text is in the 250-300 range; "
              "for very long papers you can drop to 200 to reduce load, and for very fine equations raise to 400"),
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
