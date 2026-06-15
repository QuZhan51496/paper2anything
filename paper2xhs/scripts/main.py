"""
paper2xhs — 主入口
将学术论文 PDF 转换为小红书帖子草稿

用法：
  python main.py paper.pdf                    # 完整流水线
  python main.py paper.pdf --from-stage 3     # 从指定阶段继续
  python main.py paper.pdf --skip-cover       # 跳过封面生成
  python main.py paper.pdf --skip-publish     # 跳过发布
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
    """从已有任务 ID 重建工作区路径"""
    return create_workspace(task_id, base_dir)


def _print_pipeline_status(stages_done: list[int]) -> None:
    """打印流水线状态表格"""
    table = Table(title="流水线状态", show_header=True)
    table.add_column("阶段", style="cyan", width=6)
    table.add_column("名称", width=20)
    table.add_column("状态", width=10)

    stage_names = [
        "PDF 上传",
        "MinerU 解析",
        "论文理解",
        "内容结构化",
        "小红书生成",
        "封面生成",
        "半自动发布",
    ]
    for i, name in enumerate(stage_names, 1):
        if i in stages_done:
            status = "[green]✓ 完成[/green]"
        else:
            status = "[dim]待执行[/dim]"
        table.add_row(str(i), name, status)

    console.print(table)


def _print_final_summary(workspace: dict, task_id: str) -> None:
    """打印最终结果摘要"""
    post_path = workspace["xhs"] / "xhs_post.json"
    cover_path = workspace["xhs"] / "cover.png"

    console.print(
        Panel(
            f"[bold green]任务完成！[/bold green]\n\n"
            f"任务 ID: [cyan]{task_id}[/cyan]\n"
            f"工作区: [dim]{workspace['root']}[/dim]\n\n"
            f"帖子文件: [cyan]{post_path}[/cyan]\n"
            f"封面图: [cyan]{cover_path if cover_path.exists() else '未生成'}[/cyan]",
            title="paper2xhs",
            border_style="green",
        )
    )

    if post_path.exists():
        try:
            post = load_json(post_path)
            console.print("\n[bold]【最终帖子预览】[/bold]")
            console.print(f"[bold cyan]标题：[/bold cyan]{post.get('title', '')}")
            console.print(f"\n{post.get('body', '')}\n")
        except Exception:
            pass


@click.command()
@click.argument("pdf_path", required=False)
@click.option("--from-stage", "-s", type=int, default=1, help="从指定阶段开始（1-7）")
@click.option("--resume", "-r", type=str, default=None, help="恢复已有任务 ID")
@click.option("--skip-cover", is_flag=True, default=False, help="跳过封面生成（Stage 6）")
@click.option("--skip-publish", is_flag=True, default=False, help="跳过发布（Stage 7）")
@click.option("--no-confirm", is_flag=True, default=False, help="不需要人工确认，自动继续")
@click.option("--base-dir", default=None, help="工作区根目录（默认落在论文旁 .paper2anything/xhs/）")
def main(
    pdf_path: str | None,
    from_stage: int,
    resume: str | None,
    skip_cover: bool,
    skip_publish: bool,
    no_confirm: bool,
    base_dir: str | None,
):
    """
    paper2xhs — 将学术论文 PDF 转换为小红书帖子

    PDF_PATH: 本地 PDF 文件路径
    """
    console.print(
        Panel(
            "[bold cyan]paper2xhs[/bold cyan]\n学术论文 → 小红书帖子",
            border_style="cyan",
        )
    )

    # ── 解析工作区根目录：默认落在论文旁 <pdf目录>/.paper2anything/xhs/ ──
    if base_dir is None:
        base_dir = (
            str(Path(pdf_path).expanduser().resolve().parent / ".paper2anything" / "xhs")
            if pdf_path
            else "workspace"
        )

    # ── 确定任务 ID 和工作区 ──
    task_id = None
    workspace = None

    if resume:
        # 恢复已有任务
        task_id = resume
        workspace = _load_workspace(task_id, base_dir)
        if not workspace["root"].exists():
            print_error(f"任务工作区不存在: {workspace['root']}")
            sys.exit(1)
        print_info(f"恢复任务: {task_id}")
        print_info(f"从 Stage {from_stage} 开始")
    elif pdf_path:
        if from_stage > 1:
            # 从中间阶段开始，需要找到已有任务
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

    # ══════════════════════════════════════════
    # Stage 1 — PDF 上传
    # ══════════════════════════════════════════
    if from_stage <= 1:
        result = stage1_upload.run(pdf_path, base_dir)
        if result["status"] != "success":
            print_error(f"Stage 1 失败: {result.get('error', '未知错误')}")
            sys.exit(1)

        task_id = result["task_id"]
        workspace = _load_workspace(task_id, base_dir)
        stages_done.append(1)

        if not no_confirm:
            _print_pipeline_status(stages_done)
            if not confirm_continue("Stage 1 完成，是否继续 Stage 2（MinerU 解析）？"):
                print_info("已暂停。使用以下命令继续：")
                print_info(f"  python main.py --resume {task_id} --from-stage 2 --base-dir {base_dir}")
                sys.exit(0)

    # ══════════════════════════════════════════
    # Stage 2 — MinerU 解析
    # ══════════════════════════════════════════
    if from_stage <= 2:
        result = stage2_parse.run(task_id, workspace, base_dir)
        if result["status"] != "success":
            print_error(f"Stage 2 失败: {result.get('error', '未知错误')}")
            sys.exit(1)

        stages_done.append(2)

        if not no_confirm:
            _print_pipeline_status(stages_done)
            if not confirm_continue("Stage 2 完成，是否继续 Stage 3（论文理解）？"):
                print_info(f"  python main.py --resume {task_id} --from-stage 3 --base-dir {base_dir}")
                sys.exit(0)

    # ══════════════════════════════════════════
    # Stage 3 — 论文理解
    # ══════════════════════════════════════════
    if from_stage <= 3:
        result = stage3_understand.run(task_id, workspace)
        if result["status"] != "success":
            print_error(f"Stage 3 失败: {result.get('error', '未知错误')}")
            sys.exit(1)

        stages_done.append(3)

        if not no_confirm:
            _print_pipeline_status(stages_done)
            if not confirm_continue("Stage 3 完成，是否继续 Stage 4（内容结构化）？"):
                print_info(f"  python main.py --resume {task_id} --from-stage 4 --base-dir {base_dir}")
                sys.exit(0)

    # ══════════════════════════════════════════
    # Stage 4 — 内容结构化
    # ══════════════════════════════════════════
    if from_stage <= 4:
        result = stage4_structure.run(task_id, workspace)
        if result["status"] != "success":
            print_error(f"Stage 4 失败: {result.get('error', '未知错误')}")
            sys.exit(1)

        stages_done.append(4)

        if not no_confirm:
            _print_pipeline_status(stages_done)
            if not confirm_continue("Stage 4 完成，是否继续 Stage 5（小红书内容生成）？"):
                print_info(f"  python main.py --resume {task_id} --from-stage 5 --base-dir {base_dir}")
                sys.exit(0)

    # ══════════════════════════════════════════
    # Stage 5 — 小红书内容生成
    # ══════════════════════════════════════════
    if from_stage <= 5:
        result = stage5_generate.run(task_id, workspace)
        if result["status"] != "success":
            print_error(f"Stage 5 失败: {result.get('error', '未知错误')}")
            sys.exit(1)

        stages_done.append(5)

        if not no_confirm:
            _print_pipeline_status(stages_done)
            if not confirm_continue("Stage 5 完成，是否继续 Stage 6（封面生成）？"):
                print_info(f"  python main.py --resume {task_id} --from-stage 6 --base-dir {base_dir}")
                sys.exit(0)

    # ══════════════════════════════════════════
    # Stage 6 — 封面生成（可选）
    # ══════════════════════════════════════════
    if from_stage <= 6 and not skip_cover:
        result = stage6_cover.run(task_id, workspace)
        if result["status"] == "failed":
            print_warning(f"Stage 6 失败（非致命）: {result.get('error', '')}")
            print_warning("继续后续流程...")
        elif result["status"] == "skipped":
            print_info(f"Stage 6 跳过: {result.get('reason', '')}")
        else:
            stages_done.append(6)

        if not no_confirm and result["status"] == "success":
            _print_pipeline_status(stages_done)
            if not confirm_continue("Stage 6 完成，是否继续 Stage 7（半自动发布）？"):
                print_info(f"  python main.py --resume {task_id} --from-stage 7 --base-dir {base_dir}")
                sys.exit(0)

    # ══════════════════════════════════════════
    # Stage 7 — 半自动发布
    # ══════════════════════════════════════════
    if from_stage <= 7 and not skip_publish:
        result = stage7_publish.run(task_id, workspace)
        if result["status"] == "success":
            stages_done.append(7)
        elif result["status"] == "cancelled":
            print_info("发布已取消")
        else:
            print_warning(f"Stage 7 失败: {result.get('error', '')}")

    # ── 最终摘要 ──
    _print_pipeline_status(stages_done)
    _print_final_summary(workspace, task_id)


if __name__ == "__main__":
    main()
