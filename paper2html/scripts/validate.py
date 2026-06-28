#!/usr/bin/env python
"""validate — QA validation (mechanical, gate 2).

Run after you've hand-authored index.html: validate the finished page (structural issues as errors, content fidelity
as warnings) and produce a report for you to revise from. Doesn't edit the HTML, doesn't render — only looks at the index.html + manifest.json you wrote.

Checks:
  error  — missing <!DOCTYPE html>/</html>, a referenced images/<x> file missing, empty href="#"
  warning — title/figure/table not present on the page, claims<3, repeated image references, empty alt, etc.

Outputs (under --workdir):
  validation.json   machine-readable result (ok/errors/warnings/checks)
  qa_report.md      human-readable report
  logs/validate_result.json

Usage:
  python validate.py --workdir <pdf-dir>/.paper2anything/html/<stem>
"""
import argparse
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: F401  uniformly load the package-root .env
from utils import (
    resolve_workspace, save_json, load_json, save_stage_result, print_stage_header,
    print_info, print_success, print_warning, print_error,
)
from lib import core


def run(workdir: str) -> dict:
    print_stage_header("QA validation of index.html (gate 2)")
    ws = resolve_workspace(workdir)
    root = ws["root"]

    index_html = root / "index.html"
    manifest_path = root / "manifest.json"
    if not index_html.exists():
        print_error(f"{index_html} not found; write index.html before running QA")
        return {"status": "failed", "error": "index.html does not exist"}
    if not manifest_path.exists():
        print_error(f"{manifest_path} not found; run parse_pdf first")
        return {"status": "failed", "error": "manifest.json does not exist"}

    manifest = core.manifest_from_dict(load_json(manifest_path))
    html = index_html.read_text(encoding="utf-8")

    qa = core.validate_site(html, root, manifest)

    save_json(asdict(qa), root / "validation.json")
    (root / "qa_report.md").write_text(core.render_qa_report(qa, manifest), encoding="utf-8")

    if qa.ok:
        print_success("QA PASS (no structural errors)")
    else:
        print_error(f"QA FAIL: {len(qa.errors)} error(s)")
        for e in qa.errors:
            print_error(f"  ✗ {e}")
    for w in qa.warnings:
        print_warning(f"  ⚠ {w}")
    print_info(f"Report: {root / 'qa_report.md'}")

    result = {
        "status": "success" if qa.ok else "qa_failed",
        "ok": qa.ok,
        "errors": qa.errors,
        "warnings": qa.warnings,
        "checks": qa.checks,
        "validation": str(root / "validation.json"),
        "qa_report": str(root / "qa_report.md"),
    }
    save_stage_result(result, "validate", ws)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="paper2html validate: QA validation of index.html")
    ap.add_argument("--workdir", required=True, help="working directory (<pdf-dir>/.paper2anything/html/<stem>)")
    args = ap.parse_args()
    result = run(args.workdir)
    # A QA FAIL is not a script error (you fix per the report and re-run); only a real exception returns non-zero
    return 0 if result.get("status") in {"success", "qa_failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
