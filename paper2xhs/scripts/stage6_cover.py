"""
Stage 6 — 封面生成（可选）
使用 GPT Image API (gpt-image-1) 生成小红书封面图
输出：cover.png
"""

import base64
import os
import shutil
from pathlib import Path

from utils import (
    load_json,
    logger,
    print_error,
    print_info,
    print_stage_header,
    print_success,
    print_warning,
    save_json,
    save_stage_result,
)


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
- 图片比例：3:4（竖版，适合小红书）
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


def run(task_id: str, workspace: dict) -> dict:
    """
    执行 Stage 6：封面生成（可选）

    输入：
      - workspace["understanding"]/paper_understanding.json
      - workspace["xhs"]/xhs_post.json
    输出：workspace["xhs"]/cover.png
    """
    print_stage_header(6, "封面生成（可选）")

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
        print_info(f"找到合适的论文原图: {main_figure_path.name}，直接用作封面")
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
            return {"status": "failed", "error": "封面图生成失败"}

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
    save_stage_result(result, "stage6_cover", workspace)
    return result
