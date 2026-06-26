"""
workdir.py — paper2slides work directory and default-argument resolution

Centralized implementation of:
  - default output path resolution (defaults to <stem>_slides/<stem>.pptx next to the paper; on name collision the directory appends _v2/_v3)
  - work directory resolution (.paper2anything/slides/<stem>/ in the paper's directory; falls back to ~/.cache when the paper's directory is read-only)
  - stage-completion determination and --from-stage skip logic

Called uniformly by SKILL.md and all helper scripts, to avoid the rules being scattered all over.

CLI:
    python -m scripts.workdir resolve <paper.pdf> [--output <out.pptx>] [--ensure]
    python -m scripts.workdir status  <paper.pdf>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

STAGES = ("configure", "extract", "outline", "spec", "render", "qa")

# Criterion for each stage being "complete": the existence of the output path (relative to workdir) counts as complete.
STAGE_MARKERS = {
    "configure":  "config.json",   # Stage 0.5: persisting the three AskUserQuestion confirmations
    "extract":    "figures_index.json",
    "outline":    "slide_outline.json",
    "spec":       "slide_spec.json",
    "render":     "output.pptx",   # the render output first lands in workdir, then is copied to output_path at the end
    "qa":         "qa_log.json",
}


@dataclass
class Workspace:
    paper_path: Path
    output_path: Path
    workdir: Path

    @property
    def paper_meta_path(self) -> Path:    return self.workdir / "paper_meta.json"
    @property
    def slide_outline_path(self) -> Path: return self.workdir / "slide_outline.json"
    @property
    def slide_spec_path(self) -> Path:    return self.workdir / "slide_spec.json"
    @property
    def config_path(self) -> Path:        return self.workdir / "config.json"
    @property
    def figures_dir(self) -> Path:        return self.workdir / "figures"
    @property
    def pages_dir(self) -> Path:          return self.workdir / "pages"
    @property
    def figures_index_path(self) -> Path: return self.workdir / "figures_index.json"
    @property
    def render_dir(self) -> Path:         return self.workdir / "render"
    @property
    def qa_dir(self) -> Path:             return self.workdir / "qa"
    @property
    def render_output_path(self) -> Path: return self.workdir / "output.pptx"
    @property
    def qa_log_path(self) -> Path:        return self.workdir / "qa_log.json"
    @property
    def run_log_path(self) -> Path:       return self.workdir / "run.log"

    def ensure(self) -> None:
        for d in (self.workdir, self.figures_dir, self.pages_dir,
                  self.render_dir, self.qa_dir):
            d.mkdir(parents=True, exist_ok=True)

    def stage_complete(self, stage: str) -> bool:
        return (self.workdir / STAGE_MARKERS[stage]).exists()

    def should_run(self, stage: str, from_stage: str | None = None,
                   force: bool = False) -> bool:
        """Decide whether a given stage should run.

        - force=True: run unconditionally
        - from_stage specified: run all stages from that stage onward
        - neither specified: skip if the stage's output already exists
        """
        if force:
            return True
        if from_stage is not None:
            return STAGES.index(stage) >= STAGES.index(from_stage)
        return not self.stage_complete(stage)

    def to_dict(self) -> dict:
        d = {
            "paper_path":  str(self.paper_path),
            "output_path": str(self.output_path),
            "workdir":     str(self.workdir),
        }
        for k in ("config_path", "paper_meta_path",
                  "slide_outline_path",
                  "slide_spec_path", "figures_dir", "pages_dir",
                  "figures_index_path", "render_dir", "qa_dir",
                  "render_output_path", "qa_log_path", "run_log_path"):
            d[k] = str(getattr(self, k))
        d["stage_status"] = {s: self.stage_complete(s) for s in STAGES}
        return d


def _is_dir_writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        return False
    return os.access(p, os.W_OK)


def _hashed_workdir_fallback(paper_path: Path) -> Path:
    h = hashlib.sha1(str(paper_path).encode("utf-8")).hexdigest()[:12]
    return Path.home() / ".cache" / "paper2anything" / "slides" / f"{paper_path.stem}-{h}"


def resolve_workdir(paper_path: Path) -> Path:
    paper_path = paper_path.resolve()
    preferred_parent = paper_path.parent / ".paper2anything" / "slides"
    if _is_dir_writable(preferred_parent):
        wd = preferred_parent / paper_path.stem
        wd.mkdir(parents=True, exist_ok=True)
        return wd
    return _hashed_workdir_fallback(paper_path)


def resolve_output_path(paper_path: Path, requested: Path | None) -> Path:
    if requested is not None:
        return requested.expanduser().resolve()
    paper_path = paper_path.resolve()
    # the finished product lands in the <stem>_slides/ subdirectory next to the paper;
    # on name collision the directory appends _v2, _v3, without overwriting the old product. The pptx filename stays <stem>.pptx.
    parent, stem = paper_path.parent, paper_path.stem
    out_dir = parent / f"{stem}_slides"
    i = 2
    while out_dir.exists():
        out_dir = parent / f"{stem}_slides_v{i}"
        i += 1
    return out_dir / f"{stem}.pptx"


def resolve_workspace(paper_path: Path,
                      output_path: Path | None = None) -> Workspace:
    paper_path = paper_path.expanduser().resolve()
    if not paper_path.exists():
        raise FileNotFoundError(f"paper not found: {paper_path}")
    if paper_path.suffix.lower() != ".pdf":
        raise ValueError(f"paper must be .pdf, got: {paper_path.suffix}")
    return Workspace(
        paper_path=paper_path,
        output_path=resolve_output_path(paper_path, output_path),
        workdir=resolve_workdir(paper_path),
    )


def main() -> None:
    p = argparse.ArgumentParser(description="paper2slides workdir resolver")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("resolve", help="resolve the workspace and print JSON")
    pr.add_argument("paper", type=Path)
    pr.add_argument("--output", type=Path, default=None)
    pr.add_argument("--ensure", action="store_true",
                    help="also create the workdir and subdirectories")

    ps = sub.add_parser("status", help="print whether each stage is complete")
    ps.add_argument("paper", type=Path)

    args = p.parse_args()
    ws = resolve_workspace(args.paper, getattr(args, "output", None))

    if args.cmd == "resolve":
        if args.ensure:
            ws.ensure()
        print(json.dumps(ws.to_dict(), indent=2, ensure_ascii=False))
    elif args.cmd == "status":
        print(json.dumps(
            {"stage_status": {s: ws.stage_complete(s) for s in STAGES}},
            indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
