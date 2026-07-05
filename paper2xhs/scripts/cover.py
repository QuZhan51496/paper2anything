"""
cover — 封面生成（可选）
使用 GPT Image API (gpt-image-2) 生成小红书封面图
输出：cover.png
"""

import base64
import os
import re
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
        line_h = int(size * 1.32)
        if line_h * len(lines) <= max_h:
            return font, lines, line_h
        size -= 6
    return ImageFont.truetype(_CJK_FONT, min_size), lines, int(min_size * 1.32)


def _hex2rgb(s: str, default: tuple) -> tuple:
    try:
        s = (s or "").lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def _cover_colors(understanding: dict) -> tuple:
    """本地合成封面的底色/强调色：用 understanding.cover_palette 里选定的配色（bg + accent）；
    缺省回退通用浅色调（浅灰底 + 蓝色强调）。"""
    pal = (understanding or {}).get("cover_palette") or {}
    return _hex2rgb(pal.get("bg"), (244, 245, 247)), _hex2rgb(pal.get("accent"), (46, 134, 171))


def _title_color(bg: tuple) -> tuple:
    """标题字色随底色深浅自适应：深底用白字、浅底用近黑字，保证对比度。"""
    return (255, 255, 255) if (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]) < 140 else (26, 26, 40)


def _compose_xhs_cover(fig_path: Path, cover_text: str, out_path: Path,
                       understanding: dict = None, w: int = 1080, h: int = 1440) -> bool:
    """合成小红书竖版封面（3:4）：深色底 + 顶部 cover_text 大字 + 白卡内嵌等比原图。失败返回 False。"""
    try:
        from PIL import Image, ImageDraw
        if not os.path.exists(_CJK_FONT):
            return False
        bg, accent = _cover_colors(understanding)
        txt = _title_color(bg)
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
                draw.text(((w - lw) / 2, ty), ln, font=font, fill=txt)
                ty += line_h
            draw.rectangle([margin, title_h - 30, margin + 100, title_h - 20], fill=accent)
        # 白卡按图等比缩放后的尺寸"贴合"图（加 pad），水平居中、顶对齐贴标题下方——宽图不再浮在
        # 过高白卡里留大片空白，余白统一落在底部、卡外是深色封面底，观感更整（仍等比内嵌、不裁不拉伸）。
        pad = 32
        region = [margin, title_h + 8, w - margin, h - margin]
        avail_w, avail_h = region[2] - region[0] - 2 * pad, region[3] - region[1] - 2 * pad
        fig = Image.open(fig_path).convert("RGB")
        scale = min(avail_w / fig.width, avail_h / fig.height)
        nw, nh = max(1, int(fig.width * scale)), max(1, int(fig.height * scale))
        fig = fig.resize((nw, nh), Image.LANCZOS)
        card_w, card_h = nw + 2 * pad, nh + 2 * pad
        cx = region[0] + (region[2] - region[0] - card_w) // 2
        cy = region[1]  # 顶对齐：图卡紧贴标题下方，余白统一落在底部（标题→图→留白的自然版式）
        draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=28, fill=(255, 255, 255), outline=(226, 228, 232), width=2)
        canvas.paste(fig, (cx + pad, cy + pad))
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
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    return OpenAI(api_key=api_key, base_url=base_url)


def _clip_title(title: str, limit: int = 90) -> str:
    """英文副标题：优先取冒号前的主标题（更精炼且语义完整），过短则用全称；
    超长再按词边界截断加省略号——避免半句硬截把原意截反（如 "Still Do Not Transfer" 截成 "Still Do"）。"""
    t = " ".join((title or "").split())
    head = re.split(r"[:：]", t, 1)[0].strip()
    if len(head) >= 16:
        t = head
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-") + "…"


def _paper_brief(understanding: dict) -> str:
    """把论文理解拼成「核心内容」简介，供模型理解论文、构思贴切主视觉（不必逐条画进图里）。"""
    g = understanding.get
    findings = g("highlights", []) or g("contributions", []) or []
    results = g("experiment_results", []) or []
    rows = [
        ("标题", g("paper_title", "")),
        ("核心方法 / 主题", g("method_name", "")),
        ("一句话概括", g("one_sentence_summary", "")),
        ("解决的问题", g("problem", "")),
        ("方法做法", g("method", "")),
        ("主要发现", "；".join(str(h) for h in findings[:4])),
        ("关键结果", "；".join(str(r) for r in results[:4])),
        ("关键词", "、".join((g("keywords", []) or [])[:6])),
    ]
    return "\n".join(f"- {k}：{v}" for k, v in rows if v)


def _build_image_prompt(understanding: dict, title: str, subtitle: str) -> str:
    """构建封面图生成 Prompt：给足论文核心内容供模型理解，约束简洁、禁止编造数据图表。
    title / subtitle 由你在封面步骤拟定后传入（此时你已读透论文）。"""
    sub_line = f'\n- 画面含副标题小字："{subtitle}"' if subtitle else ""
    return f"""为下面这篇学术论文设计一张小红书风格的竖版封面图。

【论文核心内容（供你理解论文、构思贴切的主视觉；不必把这些文字都画进图里）】
{_paper_brief(understanding)}

【设计要求】
- 尽量简洁：聚焦一个能表达论文主旨的核心视觉或隐喻，不要做成密密麻麻的信息图。
- 画面含主标题大字："{title}"{sub_line}
- 除上述主、副标题外尽量不要再添加其他文字。
- 严禁编造：不要画任何具体数据、图表、折线/柱状图、坐标轴、表格、baseline 对比或伪造界面；标题本身的数字除外，需要图形时只用抽象示意。
- 不要出现任何真实人物照片。"""


def _select_main_figure(understanding: dict) -> tuple:
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


def generate_cover(client, understanding: dict, title: str, subtitle: str, output_path: Path) -> bool:
    """调用 GPT Image API 生成封面图"""
    prompt = _build_image_prompt(understanding, title, subtitle)
    print_info(f"封面 Prompt: {prompt[:200]}...")
    print_info("正在调用生图 API（high 质量单次可达数分钟，经中转更久）——请勿给本命令设过短超时")

    try:
        response = client.images.generate(
            model=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2"),
            prompt=prompt,
            size="1152x1536",  # 竖版 3:4 比例（小红书最常用封面比例）
            quality="high",
            n=1,
        )

        # gpt-image-2 返回 base64
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


def run(workdir: str, cover_title: str = "", cover_subtitle: str = "") -> dict:
    """
    生成小红书封面（可选）：默认用 OPENAI_IMAGE_MODEL 生图；无 OPENAI_API_KEY 或 key 不可用时
    回退本地合成（复用论文原图）；两者都不可用则 status=skipped。
    cover_title / cover_subtitle 由你在封面步骤拟定后经 CLI 传入（留空才回退 JSON 字段）。

    输入：understanding/paper_understanding.json（xhs_post.json 可选，仅作 cover_text 回退）
    输出：cover.png
    """
    print_stage_header("生成封面")

    workspace = resolve_workspace(workdir)
    understanding_path = workspace["understanding"] / "paper_understanding.json"
    post_path = workspace["xhs"] / "xhs_post.json"
    cover_path = workspace["xhs"] / "cover.png"

    if not understanding_path.exists():
        print_error(f"输入文件不存在: {understanding_path}")
        return {"status": "failed", "error": f"{understanding_path.name} 不存在"}

    understanding = load_json(understanding_path)

    # 主/副标题优先用你传入的，留空才回退 JSON 字段
    # （xhs_post.json 是可选的标题来源，缺失/损坏都不应阻断封面，故 try 兜底）
    if not cover_title and post_path.exists():
        try:
            cover_title = load_json(post_path).get("cover_text") or ""
        except Exception:
            pass
    cover_title = cover_title or understanding.get("one_sentence_summary", "")[:15]
    cover_subtitle = cover_subtitle or _clip_title(understanding.get("paper_title", ""))

    cover_source = None
    # ── 默认：API 生图（gpt-image-2）──
    if os.environ.get("OPENAI_API_KEY"):
        try:
            client = _get_openai_client()
            print_info(f"封面主标题: {cover_title}")
            if generate_cover(client, understanding, cover_title, cover_subtitle, cover_path):
                cover_source = "ai_generated"
        except (ImportError, ValueError) as e:
            print_warning(f"API 客户端不可用：{e}")
        if not cover_source:
            print_warning("API 生图未成功（key 未提供则不会到这；多为 key 不可用或报错），回退本地合成")
    else:
        print_info("未配置 OPENAI_API_KEY，使用本地合成（复用论文原图）")

    # ── 回退：本地合成，复用论文原图 ──
    if not cover_source:
        main_figure_path, _ = _select_main_figure(understanding)
        if not main_figure_path:
            return {"status": "skipped", "reason": "API 不可用且无可复用论文原图"}
        print_info(f"本地合成竖版封面，复用论文原图: {main_figure_path.name}")
        if _compose_xhs_cover(main_figure_path, cover_title, cover_path, understanding):
            cover_source = "paper_figure_composed"
        else:
            shutil.copy2(main_figure_path, cover_path)
            cover_source = "paper_figure"

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
        "cover_text": cover_title,
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
        help="工作区目录，约定 <pdf目录>/.paper2anything/xhs/<stem>",
    )
    parser.add_argument("--title", default="", help="封面主标题大字（你在此步拟定；留空回退 xhs_post.cover_text）")
    parser.add_argument("--subtitle", default="", help="封面副标题小字（你拟定；留空回退论文标题精简）")
    args = parser.parse_args()
    res = run(args.workdir, args.title, args.subtitle)
    # skipped（无 key / 无合适图）不算失败
    sys.exit(0 if res.get("status") in ("success", "skipped") else 1)
