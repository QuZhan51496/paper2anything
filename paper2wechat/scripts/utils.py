"""
paper2wechat 工具函数模块
"""

import json
import logging
import os
import random
import string
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

console = Console()


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    return logging.getLogger("paper2wechat")


logger = setup_logging()


def generate_task_id() -> str:
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{now}_{suffix}"


def create_workspace(task_id: str, base_dir: str = "workspace") -> dict[str, Path]:
    base = Path(base_dir) / task_id
    dirs = {
        "root": base,
        "raw": base / "raw",
        "parsed": base / "parsed",
        "pages": base / "pages",
        "figures": base / "figures",
        "understanding": base / "understanding",
        "assets": base / "assets",
        "wechat": base / "wechat",
        "logs": base / "logs",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def save_json(data: Any, path: Path, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    logger.debug(f"已保存: {path}")


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_stage_result(result: dict, stage_name: str, workspace: dict[str, Path]) -> None:
    log_path = workspace["logs"] / f"{stage_name}_result.json"
    save_json(result, log_path)


def print_stage_header(stage_num: int, stage_name: str) -> None:
    console.print(
        Panel(
            Text(f"Stage {stage_num}: {stage_name}", style="bold cyan", justify="center"),
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


def confirm_continue(prompt_text: str = "是否继续到下一阶段？") -> bool:
    console.print(f"\n[bold yellow]{prompt_text}[/bold yellow] [y/n]: ", end="")
    try:
        answer = input().strip().lower()
        return answer in ("y", "yes", "是", "")
    except (EOFError, KeyboardInterrupt):
        return False


def find_latest_task(base_dir: str = "workspace") -> str | None:
    base = Path(base_dir)
    if not base.exists():
        return None
    tasks = sorted(
        [d.name for d in base.iterdir() if d.is_dir()],
        reverse=True,
    )
    return tasks[0] if tasks else None
