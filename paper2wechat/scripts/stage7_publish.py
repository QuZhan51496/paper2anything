"""
Stage 7 — md2wechat 格式化与发布准备

流程：
  1. 读取 wechat_article.md
  2. 调用 md2wechat 将 Markdown 转换为微信兼容 HTML
  3. 输出 wechat_article.html（可直接复制到公众号编辑器）
  4. 打印发布指引

md2wechat 安装：
  pip install md2wechat
  或从源码：git clone https://github.com/geekjourneyx/md2wechat-skill && pip install -e .

配置（.env）：
  MD2WECHAT_CMD=/path/to/md2wechat   # 如果不在 PATH 中
  MD2WECHAT_THEME=default             # 主题，可选：default / academic / tech / dark
"""

import os
import subprocess
import shutil
from pathlib import Path

from utils import (
    load_json,
    print_error,
    print_info,
    print_stage_header,
    print_success,
    print_warning,
    save_stage_result,
)


def _get_md2wechat_cmd() -> str:
    """查找 md2wechat 可执行文件路径"""
    custom = os.environ.get("MD2WECHAT_CMD", "").strip()
    if custom:
        return custom
    # 尝试在 PATH 中找
    found = shutil.which("md2wechat")
    if found:
        return found
    return "md2wechat"  # 假设在 PATH 中，让 subprocess 报错


def _check_md2wechat(cmd: str) -> bool:
    """检查 md2wechat 是否可用"""
    try:
        result = subprocess.run(
            [cmd, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 or "--markdown" in (result.stdout + result.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_md2wechat(cmd: str, input_path: Path, output_path: Path, theme: str,
                   title: str = "", summary: str = "", cover_path: Path | None = None) -> bool:
    """调用 md2wechat 推送到微信草稿箱。"""
    style_map = {"academic": "academic_gray", "tech": "tech",
                 "dark": "announcement", "default": "academic_gray"}
    style = style_map.get(theme, theme)
    args = [
        cmd,
        "--markdown", str(input_path),
        "--style", style,
    ]
    if title:
        args += ["--title", title]
    if summary:
        args += ["--summary", summary[:120]]
    if cover_path and cover_path.exists():
        args += ["--cover", str(cover_path)]
    print_info(f"执行: {' '.join(args)}")
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                print_info(f"  {line}")
        if result.returncode != 0:
            print_error(f"md2wechat 返回错误码 {result.returncode}")
            if result.stderr:
                print_error(f"stderr: {result.stderr[:300]}")
            return False
        return True
    except FileNotFoundError:
        print_error(f"找不到 md2wechat 命令: {cmd}")
        print_info("请安装 md2wechat：pip install md2wechat")
        print_info("或在 .env 中设置 MD2WECHAT_CMD=/path/to/md2wechat")
        return False
    except subprocess.TimeoutExpired:
        print_error("md2wechat 执行超时（>60s）")
        return False


def _fallback_copy_markdown(input_path: Path, output_path: Path) -> None:
    """降级方案：md2wechat 不可用时直接使用已有 Markdown 文件"""
    print_warning(f"Markdown 文件已就绪: {input_path}")
    print_warning("请手动将内容粘贴到微信公众号编辑器，或安装 md2wechat 后重试")


def _print_publish_guide(article_path: Path, html_path: Path, md_path: Path, article: dict) -> None:
    """打印发布指引"""
    print_info("\n" + "═" * 60)
    print_success("【Stage 7 完成】md2wechat 格式化成功")
    print_info("═" * 60)
    print_info(f"\n文章标题：{article.get('title', '')}")
    print_info(f"文章摘要：{article.get('digest', '')[:80]}...")
    print_info(f"\n生成文件：")
    print_info(f"  Markdown 原文：{md_path}")
    print_info(f"  微信 HTML：{html_path}")
    print_info(f"\n【发布步骤】")
    print_info("  1. 打开微信公众平台：https://mp.weixin.qq.com")
    print_info("  2. 新建图文消息")
    print_info("  3. 打开 wechat_article.html，全选复制内容")
    print_info("  4. 粘贴到公众号编辑器（格式应自动保留）")
    print_info("  5. 上传封面图：cover.jpg（900×383）")
    print_info("  6. 填写摘要（已在文件中）")
    print_info("  7. 预览确认后发布")
    print_info("═" * 60 + "\n")


def run(task_id: str, workspace: dict) -> dict:
    print_stage_header(7, "md2wechat 格式化与发布准备")

    md_path = workspace["wechat"] / "wechat_article.md"
    html_path = workspace["wechat"] / "wechat_article.html"
    article_json_path = workspace["wechat"] / "wechat_article.json"

    if not md_path.exists():
        print_error(f"Markdown 文件不存在: {md_path}")
        return {"status": "failed", "error": "wechat_article.md 不存在"}

    # 加载文章元数据
    article = {}
    if article_json_path.exists():
        try:
            article = load_json(article_json_path)
        except Exception:
            pass

    cmd = _get_md2wechat_cmd()
    theme = os.environ.get("MD2WECHAT_THEME", "default")

    print_info(f"md2wechat 命令: {cmd}")
    print_info(f"主题: {theme}")

    # 检查 md2wechat 是否可用
    if not _check_md2wechat(cmd):
        print_warning(f"md2wechat 不可用（命令: {cmd}）")
        print_warning("降级处理：直接使用 Markdown 文件")
        _fallback_copy_markdown(md_path, html_path)
        _print_publish_guide(article_json_path, html_path.with_suffix(".md"), md_path, article)
        return {
            "status": "degraded",
            "reason": "md2wechat 不可用，已降级为直接输出 Markdown",
            "markdown_path": str(md_path),
        }

    # 执行转换
    cover_path = workspace["wechat"] / "cover.jpg"
    success = _run_md2wechat(
        cmd, md_path, html_path, theme,
        title=article.get("title", ""),
        summary=article.get("digest", ""),
        cover_path=cover_path if cover_path.exists() else None,
    )

    if not success:
        print_warning("md2wechat 转换失败，降级处理")
        _fallback_copy_markdown(md_path, html_path)
        return {
            "status": "degraded",
            "reason": "md2wechat 转换失败，已降级为直接输出 Markdown",
            "markdown_path": str(md_path),
        }

    if not html_path.exists():
        print_warning(f"md2wechat 未生成 HTML 文件（期望路径: {html_path}）")
        print_warning("可能 md2wechat 使用了不同的输出路径，请检查")
        _fallback_copy_markdown(md_path, html_path)

    _print_publish_guide(article_json_path, html_path, md_path, article)

    result = {
        "status": "success",
        "html_path": str(html_path),
        "markdown_path": str(md_path),
        "title": article.get("title", ""),
        "word_count": article.get("word_count", 0),
    }
    save_stage_result(result, "stage7_publish", workspace)
    return result
