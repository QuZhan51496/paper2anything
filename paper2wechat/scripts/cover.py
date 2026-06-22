"""
cover — 封面生成（可选）

优先使用论文原图（suitable_for_cover=True 的图），裁剪至微信封面尺寸 900×383。
若无合适原图，调用 OpenAI 生成专业学术风格封面图（1920×816，再 resize）。
输出 cover.jpg（微信推荐 JPG 格式）。
"""

import base64
import os
import re
import shutil
from pathlib import Path

import _env  # noqa: F401  # 独立运行时兜底加载包根 .env（OPENAI_API_KEY 等）

from utils import (
    load_json,
    logger,
    print_error,
    print_info,
    print_stage_header,
    print_success,
    print_warning,
    resolve_workspace,
    save_stage_result,
)

WECHAT_COVER_W = 900
WECHAT_COVER_H = 383

_CJK_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"


def _fit_font(draw, text: str, max_w: int, max_h: int, start: int = 60, min_size: int = 26):
    """断行（拉丁/数字串不拆），递减字号直到 text 能塞进 max_w×max_h，返回 (font, lines, line_h)。"""
    from PIL import ImageFont
    size = start
    lines = [text]
    # 断行单元：连续拉丁字母/数字算一个不可断单元（"NeurIPS 2025" 不被拆成 "202"+"5"），
    # 其余按单字符——纯中文标题与逐字断行一致。
    units = re.findall(r"[A-Za-z0-9]+|.", text)
    # kinsoku 禁则：闭引号/括号/收尾标点不另起一行（否则 '…甜点"' 的闭引号会孤落行首/末行），触发断行时
    # 若该字符是收尾标点就挂在行尾、宁可轻微超宽。直双引号 " 兼作开/闭，按出现奇偶判定（第偶数个为闭）。
    no_start = "”’）)】》」』〉］｝》>，。、；;：:？?！!…·"
    while size >= min_size:
        font = ImageFont.truetype(_CJK_FONT, size)
        lines, cur, dq = [], "", 0
        for unit in units:
            closing = unit in no_start or (unit == '"' and dq % 2 == 1)
            if draw.textbbox((0, 0), cur + unit, font=font)[2] <= max_w or not cur:
                cur += unit
            elif closing and cur:
                cur += unit  # 收尾标点/闭引号挂行尾，不另起一行（kinsoku）
            else:
                lines.append(cur)
                cur = "" if unit.isspace() else unit
            if unit == '"':
                dq += 1
        if cur:
            lines.append(cur)
        line_h = int(size * 1.3)
        if line_h * len(lines) <= max_h:
            return font, lines, line_h
        size -= 4
    return ImageFont.truetype(_CJK_FONT, min_size), lines, int(min_size * 1.3)


def _compose_wechat_cover(fig_path: Path, banner_text: str, out_path: Path,
                          w: int = WECHAT_COVER_W, h: int = WECHAT_COVER_H) -> bool:
    """合成微信横版封面（900×383）：左侧深色文字栏 + 右侧白卡等比内嵌原图（不裁剪）。失败返回 False。"""
    try:
        from PIL import Image, ImageDraw
        if not os.path.exists(_CJK_FONT):
            return False
        bg, accent = (17, 49, 68), (240, 180, 65)
        canvas = Image.new("RGB", (w, h), bg)
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, 9, h], fill=accent)  # 左缘装饰条
        margin = 30
        text = (banner_text or "").strip()
        text_w = int(w * 0.42) if text else margin
        if text:
            font, lines, line_h = _fit_font(draw, text, text_w - margin - 18, h - 2 * margin)
            ty = (h - line_h * len(lines)) / 2
            for ln in lines:
                draw.text((margin, ty), ln, font=font, fill=(255, 255, 255))
                ty += line_h
        card = [text_w + 6, margin, w - margin, h - margin]
        draw.rounded_rectangle(card, radius=18, fill=(255, 255, 255))
        pad = 16
        area_w, area_h = card[2] - card[0] - 2 * pad, card[3] - card[1] - 2 * pad
        fig = Image.open(fig_path).convert("RGB")
        scale = min(area_w / fig.width, area_h / fig.height)
        nw, nh = max(1, int(fig.width * scale)), max(1, int(fig.height * scale))
        fig = fig.resize((nw, nh), Image.LANCZOS)
        canvas.paste(fig, (card[0] + pad + (area_w - nw) // 2, card[1] + pad + (area_h - nh) // 2))
        canvas.convert("RGB").save(out_path, "JPEG", quality=92)
        return True
    except Exception as e:
        print_warning(f"封面合成失败（回退为裁剪原图）：{e}")
        return False


def _get_openai_client():
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("请安装 openai: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("未设置 OPENAI_API_KEY 环境变量")
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    return OpenAI(api_key=api_key, base_url=base_url)


def _resize_to_wechat_cover(src_path: Path, dst_path: Path) -> bool:
    """将图片 resize + crop 到微信封面尺寸 900×383"""
    try:
        from PIL import Image
        with Image.open(src_path) as img:
            # 先等比缩放，使宽度达到 900（或高度达到 383，取较大者）
            w, h = img.size
            scale = max(WECHAT_COVER_W / w, WECHAT_COVER_H / h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            # 中心裁剪
            left = (new_w - WECHAT_COVER_W) // 2
            top = (new_h - WECHAT_COVER_H) // 2
            img = img.crop((left, top, left + WECHAT_COVER_W, top + WECHAT_COVER_H))
            img.convert("RGB").save(dst_path, "JPEG", quality=92)
        return True
    except Exception as e:
        logger.warning(f"PIL resize 失败: {e}，直接复制原图")
        shutil.copy2(src_path, dst_path)
        return True


def _build_image_prompt(paper_title: str, method_name: str, keywords: list) -> str:
    kw_str = "、".join(keywords[:4]) if keywords else "AI 研究"
    return f"""设计一张微信公众号封面图，风格要求：
- 整体风格：专业、学术、简洁，适合科技类公众号
- 图片比例：横版，宽高比约 2.35:1（适合微信公众号封面图）
- 背景：深蓝色渐变或白色简洁背景
- 主要文字："{method_name or paper_title[:20]}"
- 装饰元素：与 AI/机器学习相关的抽象图形（神经网络节点、数据流、几何图形）
- 关键词标签：{kw_str}
- 文字清晰可读，颜色对比度高
- 整体专业感强，适合学术研究者群体
不要包含任何真实人物照片。不要竖版构图。"""


def _select_cover_figure(understanding: dict, figures_dir: Path) -> tuple:
    """优先选 suitable_for_cover=True 且 importance_score 最高的图"""
    important_figures = understanding.get("important_figures", [])
    best, best_score = None, 0.0
    for fig in important_figures:
        if fig.get("suitable_for_cover") and fig.get("importance_score", 0) > best_score:
            img_path = Path(fig.get("image_path", ""))
            if img_path.exists():
                best = fig
                best_score = fig["importance_score"]
    if best:
        return Path(best["image_path"]), best.get("wechat_caption", "")

    # 备用：importance_score 最高的图
    for fig in sorted(important_figures, key=lambda x: x.get("importance_score", 0), reverse=True):
        img_path = Path(fig.get("image_path", ""))
        if img_path.exists():
            return img_path, fig.get("wechat_caption", "")

    return None, ""


def generate_cover_ai(client, paper_title: str, method_name: str, keywords: list, output_path: Path) -> bool:
    prompt = _build_image_prompt(paper_title, method_name, keywords)
    print_info(f"封面 Prompt: {prompt[:200]}...")
    try:
        response = client.images.generate(
            model=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2"),
            prompt=prompt,
            size="1920x816",  # 横版 2.35:1（微信公众号最常用封面比例，≈900×383）
            quality="high",
            n=1,
        )
        image_data = response.data[0].b64_json
        if image_data:
            tmp_path = output_path.with_suffix(".tmp.png")
            tmp_path.write_bytes(base64.b64decode(image_data))
            _resize_to_wechat_cover(tmp_path, output_path)
            tmp_path.unlink(missing_ok=True)
            return True
        image_url = response.data[0].url
        if image_url:
            import urllib.request
            tmp_path = output_path.with_suffix(".tmp.png")
            urllib.request.urlretrieve(image_url, tmp_path)
            _resize_to_wechat_cover(tmp_path, output_path)
            tmp_path.unlink(missing_ok=True)
            return True
        print_error("API 返回数据中无图片内容")
        return False
    except Exception as e:
        print_error(f"AI 封面生成失败: {e}")
        return False


def _validate_image(image_path: Path) -> bool:
    if not image_path.exists() or image_path.stat().st_size < 1024:
        return False
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            w, h = img.size
            return w >= 200 and h >= 80
    except Exception:
        return image_path.stat().st_size > 5120


def run(workdir: str) -> dict:
    """
    生成微信公众号封面（横版 900×383 JPG）：优先复用 understanding.important_figures 里
    suitable_for_cover 最高分的论文原图，否则用 OPENAI_IMAGE_MODEL 生成横版图再裁剪；
    无 OPENAI_API_KEY 则跳过（status=skipped）。

    输入：understanding/paper_understanding.json
    输出：cover.jpg
    """
    print_stage_header("生成封面（微信横版 900×383）")

    workspace = resolve_workspace(workdir)
    understanding_path = workspace["understanding"] / "paper_understanding.json"
    cover_path = workspace["wechat"] / "cover.jpg"
    figures_dir = workspace["figures"]

    if not understanding_path.exists():
        print_error(f"输入文件不存在: {understanding_path}")
        return {"status": "failed", "error": f"{understanding_path.name} 不存在"}

    understanding = load_json(understanding_path)
    paper_title = understanding.get("paper_title", "")
    method_name = understanding.get("method_name", "")
    keywords = understanding.get("keywords", [])

    # banner 标题：优先文章中文标题，否则方法简称，否则截断的论文标题
    # （文章 JSON 是可选的标题来源，损坏/缺失都不应阻断封面，故 try 兜底）
    banner_text = method_name or paper_title[:24]
    article_path = workspace["wechat"] / "wechat_article.json"
    if article_path.exists():
        try:
            banner_text = (load_json(article_path).get("title") or banner_text)
        except Exception:
            pass

    # 优先使用论文原图（important_figures 里 suitable_for_cover 最高分）
    main_figure_path, _ = _select_cover_figure(understanding, figures_dir)

    if main_figure_path:
        print_info(f"使用论文原图合成横版封面: {main_figure_path.name}（{WECHAT_COVER_W}×{WECHAT_COVER_H}）")
        if _compose_wechat_cover(main_figure_path, banner_text, cover_path):
            cover_source = "paper_figure_composed"
        else:
            _resize_to_wechat_cover(main_figure_path, cover_path)
            cover_source = "paper_figure"
    else:
        print_info("未找到合适的论文原图，尝试 AI 生成封面...")
        if not os.environ.get("OPENAI_API_KEY"):
            print_warning("未设置 OPENAI_API_KEY，跳过封面生成")
            return {"status": "skipped", "reason": "无合适论文图且未设置 OPENAI_API_KEY"}
        try:
            client = _get_openai_client()
        except (ImportError, ValueError) as e:
            print_warning(f"封面生成跳过: {e}")
            return {"status": "skipped", "reason": str(e)}
        success = generate_cover_ai(client, paper_title, method_name, keywords, cover_path)
        if not success:
            # 封面是可选步骤，AI 生成失败（如 key 无效 / API 报错）不应阻断流程，降级为 skipped。
            return {"status": "skipped", "reason": "AI 封面生成失败（封面可选，不阻断）"}
        cover_source = "ai_generated"

    if not _validate_image(cover_path):
        print_error("封面图验证失败")
        return {"status": "failed", "error": "封面图无效"}

    file_size_kb = cover_path.stat().st_size / 1024
    print_success(f"封面图就绪: {cover_path.name} ({file_size_kb:.1f} KB) [{cover_source}]")

    result = {
        "status": "success",
        "cover_path": str(cover_path),
        "cover_source": cover_source,
        "file_size_kb": round(file_size_kb, 1),
        "dimensions": f"{WECHAT_COVER_W}×{WECHAT_COVER_H}",
    }
    save_stage_result(result, "cover", workspace)
    return result


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="生成微信公众号封面（协调式机械步骤）")
    parser.add_argument(
        "--workdir", required=True,
        help="工作区目录，约定 <pdf目录>/.paper2anything/wechat",
    )
    args = parser.parse_args()
    res = run(args.workdir)
    sys.exit(0 if res.get("status") in ("success", "skipped") else 1)
