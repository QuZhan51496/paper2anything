"""
Stage 7 — 半自动发布（xiaohongshu-skills）

流程：
  1. fill-publish  — 自动填写浏览器发布表单
  2. 用户在浏览器检查内容
  3. click-publish — 用户确认后自动点击发布按钮

依赖：
  - 克隆 https://github.com/autoclaw-cc/xiaohongshu-skills 并 uv sync
  - Chrome 安装 XHS Bridge 扩展（extension/ 目录）
  - 设置环境变量 XHS_SKILLS_DIR 指向克隆目录
"""

import os
import subprocess
import tempfile
from pathlib import Path

import _env  # noqa: F401  # 独立运行时兜底加载包根 .env（XHS_SKILLS_DIR 等）

from utils import (
    load_json,
    print_error,
    print_info,
    print_stage_header,
    print_success,
    print_warning,
    resolve_workspace,
    save_stage_result,
)


def _get_skills_dir() -> Path | None:
    raw = os.environ.get("XHS_SKILLS_DIR", "").strip()
    if not raw:
        print_error("未设置 XHS_SKILLS_DIR 环境变量")
        print_info("请克隆 https://github.com/autoclaw-cc/xiaohongshu-skills")
        print_info("并在 .env 中设置 XHS_SKILLS_DIR=/path/to/xiaohongshu-skills")
        return None
    p = Path(raw).expanduser()
    if not p.exists():
        print_error(f"XHS_SKILLS_DIR 路径不存在: {p}")
        return None
    cli = p / "scripts" / "cli.py"
    if not cli.exists():
        print_error(f"未找到 cli.py: {cli}")
        return None
    return p


def _run_cli(skills_dir: Path, args: list[str]) -> bool:
    cli = skills_dir / "scripts" / "cli.py"
    result = subprocess.run(
        ["uv", "run", "python", str(cli)] + args,
        cwd=skills_dir,
    )
    return result.returncode == 0


def run(workdir: str) -> dict:
    """
    半自动发布到小红书（依赖外部 xiaohongshu-skills CLI + Chrome 扩展）。

    输入：xhs/xhs_post.json（title/body/hashtags）+ xhs/cover.png（可选）
    """
    print_stage_header("半自动发布到小红书")

    skills_dir = _get_skills_dir()
    if not skills_dir:
        return {"status": "failed", "error": "XHS_SKILLS_DIR 未配置或路径无效"}

    workspace = resolve_workspace(workdir)
    post_path = workspace["xhs"] / "xhs_post.json"
    if not post_path.exists():
        print_error(f"帖子文件不存在: {post_path}")
        return {"status": "failed", "error": "xhs_post.json 不存在"}

    post = load_json(post_path)
    title = post.get("title", "")[:20]
    body = post.get("body", "")
    tags = post.get("hashtags") or post.get("tags") or []  # Claude 写的产物用 hashtags

    # 收集图片（目前只有封面，多图扩展在此处添加）
    images: list[str] = []
    cover_path = workspace["xhs"] / "cover.png"
    if cover_path.exists():
        images.append(str(cover_path.resolve()))
    else:
        print_warning("未找到封面图 cover.png，将在无图模式下发布")

    # 显示预览
    print_info("\n【发布内容预览】")
    print_info(f"标题：{title}")
    print_info(f"正文（前100字）：{body[:100]}{'...' if len(body) > 100 else ''}")
    print_info(f"标签：{tags}")
    print_info(f"图片：{images if images else '无'}")
    print_info("")

    # 写临时文件（cli.py 要求文件路径而非直接传字符串）
    tmp_files = []
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(title)
            title_file = f.name
            tmp_files.append(title_file)

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(body)
            content_file = f.name
            tmp_files.append(content_file)

        # ── Step 1: fill-publish ──
        print_info("Step 1/3：填写发布表单...")
        fill_args = [
            "fill-publish",
            "--title-file", title_file,
            "--content-file", content_file,
        ]
        if images:
            fill_args += ["--images"] + images
        if tags:
            fill_args += ["--tags"] + tags

        if not _run_cli(skills_dir, fill_args):
            return {"status": "failed", "error": "fill-publish 失败，请检查 Chrome 扩展是否已安装并启用"}

        # ── Step 2: 用户确认 ──
        print_info("\n" + "═" * 50)
        print_success("表单已填写完成，请在浏览器中检查内容")
        print_info("确认无误后按 Enter 发布，按 Ctrl+C 取消")
        print_info("═" * 50 + "\n")
        try:
            input()
        except KeyboardInterrupt:
            print_warning("用户取消发布")
            return {"status": "cancelled", "message": "用户取消"}

        # ── Step 3: click-publish ──
        print_info("Step 3/3：点击发布...")
        if not _run_cli(skills_dir, ["click-publish"]):
            return {"status": "failed", "error": "click-publish 失败"}

    finally:
        for f in tmp_files:
            try:
                os.unlink(f)
            except Exception:
                pass

    print_success("发布成功！")
    result = {"status": "success", "title": title, "images_count": len(images)}
    save_stage_result(result, "stage7_publish", workspace)
    return result


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="半自动发布到小红书（协调式机械步骤）")
    parser.add_argument(
        "--workdir", required=True,
        help="工作区目录，约定 <pdf目录>/.paper2anything/xhs",
    )
    args = parser.parse_args()
    res = run(args.workdir)
    # cancelled（用户取消）不算失败
    sys.exit(0 if res.get("status") in ("success", "cancelled") else 1)
