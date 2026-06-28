"""
paper2html utility module

Infrastructure for the you-led, coordinated flow: logging, workspace resolution, JSON read/write, Rich output.
The workspace lands next to the paper at `<pdf-dir>/.paper2anything/html/<stem>/` (multiple papers in one directory are split by `<stem>`).

Layout (root = .paper2anything/html/<stem>/):
  root/clean.md       normalized markdown (parse_pdf writes, you read)
  root/manifest.json  deterministically extracted facts (parse_pdf writes, gate 1)
  root/index.html     the single-page website you hand-author
  root/validation.json + root/qa_report.md  QA results (validate writes, gate 2)
  root/parsed/        MinerU raw parse (includes parsed/images/ with all crops)
  root/images/        the figures the page references (parse_pdf copies from parsed; referenced by you as images/<name>)
  root/logs/          *_result.json
"""

import json
import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

console = Console()


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure the logging system"""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    return logging.getLogger("paper2html")


logger = setup_logging()


def resolve_workspace(workdir: str | Path) -> dict[str, Path]:
    """Resolve the coordinated workspace (root = .paper2anything/html/<stem>/ next to the paper), creating subdirectories as needed.

    Shared by the mechanical scripts (parse/extract/validate): each script given the same --workdir aligns to
    the same set of output directories. index.html / clean.md / manifest.json land directly in root.
    """
    base = Path(workdir).expanduser().resolve()
    dirs = {
        "root": base,
        "parsed": base / "parsed",      # MinerU raw parse (includes parsed/images/ with all crops)
        "images": base / "images",      # the figures the page references (parse_pdf copies from parsed)
        "logs": base / "logs",          # per-step *_result.json (validation.json + qa_report.md land in root)
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def save_json(data: Any, path: Path, indent: int = 2) -> None:
    """Save data to a JSON file"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    logger.debug(f"Saved: {path}")


def load_json(path: Path) -> Any:
    """Load data from a JSON file"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_stage_result(result: dict, stage_name: str, workspace: dict[str, Path]) -> None:
    """Save a step's execution result to the logs directory"""
    log_path = workspace["logs"] / f"{stage_name}_result.json"
    save_json(result, log_path)


def print_stage_header(title: str) -> None:
    """Print a step header"""
    console.print(
        Panel(
            Text(title, style="bold cyan", justify="center"),
            border_style="cyan",
        )
    )


def print_success(message: str) -> None:
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str) -> None:
    console.print(f"[bold red]✗[/bold red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def print_info(message: str) -> None:
    console.print(f"[bold blue]ℹ[/bold blue] {message}")
