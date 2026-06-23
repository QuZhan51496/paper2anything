"""
paper2html 工具函数模块

协调式（你主导）下的基础设施：日志、工作区解析、JSON 读写、Rich 输出。
工作区落在论文旁 `<pdf目录>/.paper2anything/html/<stem>/`（同目录多篇论文按 `<stem>` 分篇）。

布局（root = .paper2anything/html/<stem>/）：
  root/clean.md       normalize 后的 markdown（parse_pdf 写，你读）
  root/manifest.json  确定性抽取的事实（parse_pdf 写，闸门1）
  root/index.html     你亲手写的单页网站
  root/validation.json + root/qa_report.md  QA 结果（validate 写，闸门2）
  root/parsed/        MinerU 原始解析（含 parsed/images/ 所有裁图）
  root/images/        页面引用的图（parse_pdf 从 parsed 复制；你以 images/<name> 引用）
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
    """配置日志系统"""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    return logging.getLogger("paper2html")


logger = setup_logging()


def resolve_workspace(workdir: str | Path) -> dict[str, Path]:
    """解析协调式工作区（root = 论文旁 .paper2anything/html/<stem>/），按需创建子目录。

    供机械脚本（parse/extract/validate）共用：每个脚本拿到同一个 --workdir 即对齐到
    同一组产物目录。index.html / clean.md / manifest.json 直接落在 root。
    """
    base = Path(workdir).expanduser().resolve()
    dirs = {
        "root": base,
        "parsed": base / "parsed",      # MinerU 原始解析（含 parsed/images/ 所有裁图）
        "images": base / "images",      # 页面引用的图（parse_pdf 从 parsed 复制）
        "logs": base / "logs",          # 各步骤 *_result.json + QA 产物
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def save_json(data: Any, path: Path, indent: int = 2) -> None:
    """将数据保存为 JSON 文件"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    logger.debug(f"已保存: {path}")


def load_json(path: Path) -> Any:
    """从 JSON 文件加载数据"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_stage_result(result: dict, stage_name: str, workspace: dict[str, Path]) -> None:
    """保存步骤执行结果到日志目录"""
    log_path = workspace["logs"] / f"{stage_name}_result.json"
    save_json(result, log_path)


def print_stage_header(title: str) -> None:
    """打印步骤标题"""
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
