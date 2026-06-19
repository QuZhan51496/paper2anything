"""
cover — 封面生成（可选）
使用 GPT Image API (gpt-image-1) 生成小红书封面图
输出：cover.png
"""

import base64
import os
import shutil
from pathlib import Path

import _env  # noqa: F401  # 独立运行时兜底加载包根 .env（OPENAI_API_KEY 等）

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

_CJK_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"


def _fit_font(draw, text: str, max_w: int, max_h: int, start: int = 110, min_size: int = 48):
    """逐字断行，递减字号直到 text 能塞进 max_w×max_h，返回 (font, lines, line_h)。"""
    from PIL import ImageFont
    size = start
    lines = [text]
    while size >= min_size:
        font = ImageFont.truetype(_CJK_FONT, size)
        lines, cur = [], ""
        for ch in text:
            if draw.textbbox((0, 0), cur + ch, font=font)[2] <= max_w or not cur:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        line_h = int(size * 1.32)
        if line_h * len(lines) <= max_h:
            return font, lines, line_h
        size -= 6
    return ImageFont.truetype(_CJK_FONT, min_size), lines, int(min_size * 1.32)


def _compose_xhs_cover(fig_path: Path, cover_text: str, out_path: Path, w: int = 1080, h: int = 1620) -> bool:
    """合成小红书竖版封面（2:3）：深色底 + 顶部 cover_text 大字 + 白卡内嵌等比原图。失败返回 False。"""
    try:
        from PIL import Image, ImageDraw
        if not os.path.exists(_CJK_FONT):
            return False
        bg, accent = (17, 49, 68), (240, 180, 65)
        canvas = Image.new("RGB", (w, h), bg)
        draw = ImageDraw.Draw(canvas)
        margin = 70
        text = (cover_text or "").strip()
        title_h = int(h * 0.26) if text else margin
        if text:
            font, lines, line_h = _fit_font(draw, text, w - 2 * margin, title_h - 70)
            ty = (title_h - line_h * len(lines)) / 2 + 8
            for ln in lines:
                lw = draw.textbbox((0, 0), ln, font=font)[2]
                draw.text(((w - lw) / 2, ty), ln, font=font, fill=(255, 255, 255))
                ty += line_h
            draw.rectangle([margin, title_h - 30, margin + 100, title_h - 20], fill=accent)
        card = [margin, title_h + 8, w - margin, h - margin]
        draw.rounded_rectangle(card, radius=28, fill=(255, 255, 255))
        pad = 32
        area_w, area_h = card[2] - card[0] - 2 * pad, card[3] - card[1] - 2 * pad
        fig = Image.open(fig_path).convert("RGB")
        scale = min(area_w / fig.width, area_h / fig.height)
        nw, nh = max(1, int(fig.width * scale)), max(1, int(fig.height * scale))
        fig = fig.resize((nw, nh), Image.LANCZOS)
        canvas.paste(fig, (card[0] + pad + (area_w - nw) // 2, card[1] + pad + (area_h - nh) // 2))
        canvas.save(out_path, "PNG")
        return True
    except Exception as e:
        print_warning(f"封面合成失败（回退为直接复制原图）：{e}")
        return False


def _get_openai_client():
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("请安装 openai: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("未设置 OPENAI_API_KEY 环境变量")
    return OpenAI(api_key=api_key)


def _build_image_prompt(
    paper_title: str,
    cover_text: str,
    method_name: str,
    keywords: list,
    main_figure_desc: str = "",
) -> str:
    """构建封面图生成 Prompt"""
    kw_str = "、".join(keywords[:4]) if keywords else "AI 研究"
    fig_hint = f"参考图片风格：{main_figure_desc}。" if main_figure_desc else ""

    return f"""设计一张小红书封面图，风格要求：
- 整体风格：科技感、简洁、现代、学术
- 背景：深色渐变（深蓝或深紫色调）或白色简洁背景
- 主要文字（大字）："{cover_text}"
- 副标题文字（小字）："{paper_title[:40]}"
- 装饰元素：与 AI/机器学习相关的抽象图形（神经网络节点、数据流、几何图形）
- 关键词标签：{kw_str}
- 图片比例：2:3（竖版，适合小红书）
- 文字要清晰可读，颜色对比度高
- 整体要有视觉冲击力，吸引 AI 研究者点击
{fig_hint}
不要包含任何真实人物照片。"""


def _select_main_figure(understanding: dict, figures_dir: Path) -> tuple:
    """选择最适合封面的图片"""
    important_figures = understanding.get("important_figures", [])

    # 找到 suitable_for_cover=True 且 importance_score 最高的图
    best = None
    best_score = 0.0
    for fig in important_figures:
        if fig.get("suitable_for_cover") and fig.get("importance_score", 0) > best_score:
            img_path = Path(fig.get("image_path", ""))
            if img_path.exists():
                best = fig
                best_score = fig["importance_score"]

    if best:
        return Path(best["image_path"]), best.get("description", "")

    # 备用：找 importance_score 最高的
    for fig in sorted(important_figures, key=lambda x: x.get("importance_score", 0), reverse=True):
        img_path = Path(fig.get("image_path", ""))
        if img_path.exists():
            return img_path, fig.get("description", "")

    return None, ""


def generate_cover(
    client,
    paper_title: str,
    cover_text: str,
    method_name: str,
    keywords: list,
    main_figure_desc: str,
    output_path: Path,
) -> bool:
    """调用 GPT Image API 生成封面图"""
    prompt = _build_image_prompt(paper_title, cover_text, method_name, keywords, main_figure_desc)
    print_info(f"封面 Prompt: {prompt[:200]}...")

    try:
        response = client.images.generate(
            model=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            prompt=prompt,
            size="1024x1536",  # 竖版 2:3 比例
            quality="standard",
            n=1,
        )

        # gpt-image-1 返回 base64
        image_data = response.data[0].b64_json
        if image_data:
            img_bytes = base64.b64decode(image_data)
            output_path.write_bytes(img_bytes)
            return True

        # 备用：url 方式
        image_url = response.data[0].url
        if image_url:
            import urllib.request
            urllib.request.urlretrieve(image_url, output_path)
            return True

        print_error("API 返回数据中无图片内容")
        return False

    except Exception as e:
        print_error(f"图片生成失败: {e}")
        return False


def _validate_image(image_path: Path) -> bool:
    """验证生成的图片"""
    if not image_path.exists():
        return False
    if image_path.stat().st_size < 1024:  # 小于 1KB 认为无效
        return False
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            w, h = img.size
            return w >= 256 and h >= 256
    except Exception:
        # PIL 不可用时只检查文件大小
        return image_path.stat().st_size > 10240


def run(workdir: str) -> dict:
    """
    生成小红书封面（可选）：优先复用论文原图（understanding.important_figures 里
    suitable_for_cover 最高分且 image_path 存在的），否则用 OPENAI_IMAGE_MODEL 生成；
    无 OPENAI_API_KEY 则跳过（status=skipped）。

    输入：understanding/paper_understanding.json、xhs_post.json
    输出：cover.png
    """
    print_stage_header("生成封面")

    workspace = resolve_workspace(workdir)
    understanding_path = workspace["understanding"] / "paper_understanding.json"
    post_path = workspace["xhs"] / "xhs_post.json"
    cover_path = workspace["xhs"] / "cover.png"
    figures_dir = workspace["figures"]

    # 检查输入文件
    for p in [understanding_path, post_path]:
        if not p.exists():
            print_error(f"输入文件不存在: {p}")
            return {"status": "failed", "error": f"{p.name} 不存在"}

    # 加载数据
    understanding = load_json(understanding_path)
    post = load_json(post_path)

    paper_title = understanding.get("paper_title", "")
    cover_text = post.get("cover_text", understanding.get("one_sentence_summary", "")[:15])
    method_name = understanding.get("method_name", "")
    keywords = understanding.get("keywords", [])

    # ── 优先使用论文原图 ──
    main_figure_path, main_figure_desc = _select_main_figure(understanding, figures_dir)

    if main_figure_path:
        print_info(f"找到合适的论文原图: {main_figure_path.name}，合成竖版封面")
        if _compose_xhs_cover(main_figure_path, cover_text, cover_path):
            cover_source = "paper_figure_composed"
        else:
            shutil.copy2(main_figure_path, cover_path)
            cover_source = "paper_figure"
    else:
        # ── 无合适原图，AI 生成 ──
        print_info("未找到合适的论文原图，尝试 AI 生成封面...")

        if not os.environ.get("OPENAI_API_KEY"):
            print_warning("未设置 OPENAI_API_KEY，跳过封面生成")
            return {"status": "skipped", "reason": "无合适论文图片且未设置 OPENAI_API_KEY"}

        try:
            client = _get_openai_client()
        except (ImportError, ValueError) as e:
            print_warning(f"封面生成跳过: {e}")
            return {"status": "skipped", "reason": str(e)}

        print_info(f"封面文字: {cover_text}")
        success = generate_cover(
            client,
            paper_title=paper_title,
            cover_text=cover_text,
            method_name=method_name,
            keywords=keywords,
            main_figure_desc=main_figure_desc,
            output_path=cover_path,
        )

        if not success:
            # 封面是可选步骤，AI 生成失败（如 key 无效 / API 报错）不应阻断流程，降级为 skipped。
            return {"status": "skipped", "reason": "AI 封面生成失败（封面可选，不阻断）"}

        cover_source = "generated"

    # 验证
    if not _validate_image(cover_path):
        print_error("封面图无效")
        return {"status": "failed", "error": "封面图验证失败"}

    file_size_kb = cover_path.stat().st_size / 1024
    print_success(f"封面图就绪: {cover_path.name} ({file_size_kb:.1f} KB) [{cover_source}]")

    result = {
        "status": "success",
        "cover_path": str(cover_path),
        "cover_source": cover_source,
        "cover_text": cover_text,
        "file_size_kb": round(file_size_kb, 1),
    }
    save_stage_result(result, "cover", workspace)
    return result


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="生成小红书封面（协调式机械步骤）")
    parser.add_argument(
        "--workdir", required=True,
        help="工作区目录，约定 <pdf目录>/.paper2anything/xhs",
    )
    args = parser.parse_args()
    res = run(args.workdir)
    # skipped（无 key / 无合适图）不算失败
    sys.exit(0 if res.get("status") in ("success", "skipped") else 1)
