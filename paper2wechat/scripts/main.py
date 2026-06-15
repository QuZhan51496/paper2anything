"""
paper2wechat — 主入口
将学术论文 PDF 转换为微信公众号深度解读推文

用法：
  python main.py paper.pdf                    # 完整流水线
  python main.py paper.pdf --from-stage 3     # 从指定阶段继续
  python main.py paper.pdf --skip-cover       # 跳过封面生成
  python main.py paper.pdf --skip-publish     # 跳过 md2wechat（仅生成 Markdown）
  python main.py paper.pdf --resume <task_id> # 恢复已有任务（传 PDF 以定位论文旁工作区）

"""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 加载 paper2anything 包根的 .env（统一凭据；已 export 的环境变量优先）
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from utils import (
    confirm_continue,
    console,
    create_workspace,
    find_latest_task,
    load_json,
    print_error,
    print_info,
    print_success,
    print_warning,
    save_json,
)

import stage1_upload
import stage2_parse
import stage3_understand
import stage4_structure
import stage5_generate
import stage6_cover
import stage7_publish


def _load_workspace(task_id: str, base_dir: str = "workspace") -> dict:
    return create_workspace(task_id, base_dir)


def _print_pipeline_status(stages_done: list[int]) -> None:
    table = Table(title="paper2wechat 流水线状态", show_header=True)
    table.add_column("阶段", style="cyan", width=6)
    table.add_column("名称", width=28)
    table.add_column("状态", width=10)

    stage_names = [
        "PDF 上传验证",
        "MinerU 解析",
        "论文深度理解",
        "公众号大纲结构化",
        "长文生成",
        "封面生成",
        "md2wechat 格式化",
    ]
    for i, name in enumerate(stage_names, 1):
        status = "[green]✓ 完成[/green]" if i in stages_done else "[dim]待执行[/dim]"
        table.add_row(str(i), name, status)

    console.print(table)


def _print_final_summary(workspace: dict, task_id: str) -> None:
    article_path = workspace["wechat"] / "wechat_article.json"
    html_path = workspace["wechat"] / "wechat_article.html"
    cover_path = workspace["wechat"] / "cover.jpg"

    console.print(
        Panel(
            f"[bold green]任务完成！[/bold green]\n\n"
            f"任务 ID: [cyan]{task_id}[/cyan]\n"
            f"工作区: [dim]{workspace['root']}[/dim]\n\n"
            f"文章 JSON:  [cyan]{article_path}[/cyan]\n"
            f"Markdown:   [cyan]{workspace['wechat'] / 'wechat_article.md'}[/cyan]\n"
            f"微信 HTML:  [cyan]{html_path if html_path.exists() else '未生成（跳过了 Stage 7）'}[/cyan]\n"
            f"封面图:     [cyan]{cover_path if cover_path.exists() else '未生成'}[/cyan]",
            title="paper2wechat",
            border_style="green",
        )
    )

    if article_path.exists():
        try:
            article = load_json(article_path)
            console.print("\n[bold]【最终文章预览】[/bold]")
            console.print(f"[bold cyan]标题：[/bold cyan]{article.get('title', '')}")
            console.print(f"[bold cyan]摘要：[/bold cyan]{article.get('digest', '')}")
            console.print(f"\n{article.get('body_markdown', '')[:500]}...\n")
        except Exception:
            pass


@click.command()
@click.argument("pdf_path", required=False)
@click.option("--from-stage", "-s", type=int, default=1, help="从指定阶段开始（1-7）")
@click.option("--to-stage", "-e", type=int, default=7, help="到指定阶段结束（1-7）")
@click.option("--resume", "-r", type=str, default=None, help="恢复已有任务 ID")
@click.option("--skip-cover", is_flag=True, default=False, help="跳过封面生成（Stage 6）")
@click.option("--skip-publish", is_flag=True, default=False, help="跳过 md2wechat 格式化（Stage 7）")
@click.option("--no-confirm", is_flag=True, default=False, help="不需要人工确认，自动继续")
@click.option("--base-dir", default=None, help="工作区根目录（默认落在论文旁 .paper2anything/wechat/）")
def main(
    pdf_path: str | None,
    from_stage: int,
    to_stage: int,
    resume: str | None,
    skip_cover: bool,
    skip_publish: bool,
    no_confirm: bool,
    base_dir: str | None,
):
    """paper2wechat — 将学术论文 PDF 转换为微信公众号深度解读推文"""
    console.print(
        Panel(
            "[bold cyan]paper2wechat[/bold cyan]\n学术论文 → 微信公众号深度解读推文",
            border_style="cyan",
        )
    )

    # ── 解析工作区根目录：默认落在论文旁 <pdf目录>/.paper2anything/wechat/ ──
    if base_dir is None:
        base_dir = (
            str(Path(pdf_path).expanduser().resolve().parent / ".paper2anything" / "wechat")
            if pdf_path
            else "workspace"
        )

    task_id = None
    workspace = None

    if resume:
        task_id = resume
        workspace = _load_workspace(task_id, base_dir)
        if not workspace["root"].exists():
            print_error(f"任务工作区不存在: {workspace['root']}")
            sys.exit(1)
        print_info(f"恢复任务: {task_id}，从 Stage {from_stage} 开始")
    elif pdf_path:
        if from_stage > 1:
            latest = find_latest_task(base_dir)
            if latest:
                task_id = latest
                workspace = _load_workspace(task_id, base_dir)
                print_info(f"使用最新任务: {task_id}")
            else:
                print_error("未找到已有任务，请从 Stage 1 开始")
                sys.exit(1)
    else:
        print_error("请提供 PDF 文件路径，或使用 --resume <task_id> 恢复任务")
        sys.exit(1)

    stages_done = []

    def _should_run(n: int) -> bool:
        return from_stage <= n <= to_stage

    def _stage_done(n: int, next_desc: str = "") -> None:
        stages_done.append(n)
        print_success(f"✅ Stage {n} 完成" + (f"，可继续执行 Stage {n+1}（{next_desc}）" if next_desc and n < to_stage else ""))

    # ══ Stage 1 — PDF 上传 ══
    if _should_run(1):
        result = stage1_upload.run(pdf_path, base_dir)
        if result["status"] != "success":
            print_error(f"Stage 1 失败: {result.get('error', '未知错误')}")
            sys.exit(1)
        task_id = result["task_id"]
        workspace = _load_workspace(task_id, base_dir)
        _stage_done(1, "MinerU 解析")

    # ══ Stage 2 — MinerU 解析 ══
    if _should_run(2):
        result = stage2_parse.run(task_id, workspace, base_dir)
        if result["status"] != "success":
            print_error(f"Stage 2 失败: {result.get('error', '未知错误')}")
            sys.exit(1)
        _stage_done(2, "论文深度理解")

    # ══ Stage 3 — 论文深度理解 ══
    if _should_run(3):
        result = stage3_understand.run(task_id, workspace)
        if result["status"] != "success":
            print_error(f"Stage 3 失败: {result.get('error', '未知错误')}")
            sys.exit(1)
        _stage_done(3, "大纲结构化")

    # ══ Stage 4 — 公众号大纲结构化 ══
    if _should_run(4):
        result = stage4_structure.run(task_id, workspace)
        if result["status"] != "success":
            print_error(f"Stage 4 失败: {result.get('error', '未知错误')}")
            sys.exit(1)
        _stage_done(4, "长文生成")

    # ══ Stage 5 — 公众号长文生成 ══
    if _should_run(5):
        result = stage5_generate.run(task_id, workspace)
        if result["status"] != "success":
            print_error(f"Stage 5 失败: {result.get('error', '未知错误')}")
            sys.exit(1)
        _stage_done(5, "封面生成")

    # ══ Stage 6 — 封面生成（可选，横版）══
    if _should_run(6) and not skip_cover:
        result = stage6_cover.run(task_id, workspace)
        if result["status"] == "failed":
            print_warning(f"Stage 6 失败（非致命）: {result.get('error', '')}")
        elif result["status"] == "skipped":
            print_info(f"Stage 6 跳过: {result.get('reason', '')}")
        else:
            _stage_done(6, "md2wechat 格式化与发布")

    # ══ Stage 7 — md2wechat 格式化══
    if _should_run(7) and not skip_publish:
        result = stage7_publish.run(task_id, workspace)
        if result["status"] in ("success", "degraded"):
            _stage_done(7)
        else:
            print_warning(f"Stage 7 失败: {result.get('error', '')}")

    _print_pipeline_status(stages_done)
    _print_final_summary(workspace, task_id)


if __name__ == "__main__":
    main()
