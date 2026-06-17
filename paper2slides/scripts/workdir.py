"""
workdir.py — paper2slides 工作目录与默认参数解析

集中实现：
  - 默认输出路径解析（缺省 .pptx 落在论文同目录，重名追加 -v2/-v3）
  - 工作目录解析（论文同目录 .paper2anything/slides/，论文目录只读时回退到 ~/.cache）
  - 阶段完成判定与 --from-stage 跳过逻辑

被 SKILL.md 与所有 helper 脚本统一调用，避免规则散落各处。

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

# 每个阶段"已完成"的判据：相对 workdir 的产物路径存在即视为完成。
STAGE_MARKERS = {
    "configure":  "config.json",   # Stage 0.5：AskUserQuestion 三项确认的落盘
    "extract":    "figures_index.json",
    "outline":    "slide_outline.json",
    "spec":       "slide_spec.json",
    "render":     "output.pptx",   # 渲染产物先落在 workdir，最后复制到 output_path
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
        """决定某阶段是否要执行。

        - force=True: 无条件执行
        - from_stage 指定: 从该阶段起所有阶段都执行
        - 都未指定: 阶段产物已存在则跳过
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
    base = paper_path.parent / f"{paper_path.stem}.pptx"
    if not base.exists():
        return base
    i = 2
    while True:
        candidate = paper_path.parent / f"{paper_path.stem}-v{i}.pptx"
        if not candidate.exists():
            return candidate
        i += 1


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

    pr = sub.add_parser("resolve", help="解析 workspace 并打印 JSON")
    pr.add_argument("paper", type=Path)
    pr.add_argument("--output", type=Path, default=None)
    pr.add_argument("--ensure", action="store_true",
                    help="一并创建 workdir 与子目录")

    ps = sub.add_parser("status", help="打印各阶段是否已完成")
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
