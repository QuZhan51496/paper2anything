"""
Stage 5 — 论文速读推文生成

策略：不生成新内容，将 Stage 3 提取的论文原文段落翻译成中文推文。
风格：固定 4 节（引言/方法/实验/总结），技术术语加粗，第一人称「我们」。
"""

import os
from pathlib import Path

from openai import OpenAI

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

_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def _get_client() -> OpenAI:
    import httpx
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("未设置 ANTHROPIC_API_KEY 环境变量")
    base_url = os.environ.get("ANTHROPIC_BASE_URL") or None
    return OpenAI(api_key=api_key, base_url=base_url,
                  http_client=httpx.Client(trust_env=False))


def _call_claude(client: OpenAI, prompt: str, max_tokens: int = 3000) -> str:
    response = client.chat.completions.create(
        model=_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def _parse_body_response(response: str) -> str:
    start_tag = "<<<ARTICLE_START>>>"
    end_tag = "<<<ARTICLE_END>>>"
    s = response.find(start_tag)
    e = response.find(end_tag)
    if s != -1 and e != -1:
        return response[s + len(start_tag):e].strip()
    import re
    text = re.sub(r"^```\w*\s*", "", response.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def _build_figure_map(outline: dict, workspace: dict) -> dict:
    """构建 figure_id/table_id → 相对路径（相对于 wechat/ 目录）的映射"""
    id_to_path = {}

    def _add_entries(index_list: list, id_field: str) -> None:
        for item in index_list:
            fid = item.get(id_field, "")
            img_path = item.get("image_path", "")
            if fid and img_path:
                p = Path(img_path)
                if p.exists():
                    id_to_path[fid] = f"../figures/{p.name}"

    try:
        _add_entries(load_json(workspace["parsed"] / "figures_index.json"), "figure_id")
    except Exception:
        pass
    try:
        _add_entries(load_json(workspace["parsed"] / "tables_index.json"), "table_id")
    except Exception:
        pass

    return id_to_path


def _fig_md(fid: str | None, figure_map: dict, caption: str = "") -> str:
    if not fid or fid == "null":
        return ""
    path = figure_map.get(fid)
    if not path:
        return ""
    return f"\n![{caption}]({path})\n"


def translate_article(client: OpenAI, outline: dict, figure_map: dict) -> str:
    """
    将论文原文英文段落翻译成中文推文。
    不生成新内容，只翻译和格式化 Stage 3 摘录的原文段落。
    """
    method_name = outline.get("method_name", "")
    paper_title_en = outline.get("paper_title_en", "")
    authors_cn = outline.get("authors_cn", "")
    bold_terms = outline.get("bold_terms", [method_name]) or [method_name]

    intro_observations = outline.get("intro_observations", [])
    intro_method_overview = outline.get("intro_method_overview", "")
    method_modules = outline.get("method_modules", [])   # [{name, text}]
    experiment_setup = outline.get("experiment_setup", "")
    experiment_results = outline.get("experiment_results", "")
    conclusion_text = outline.get("conclusion", "")

    intro_fig = _fig_md(outline.get("intro_figure_id"), figure_map, "框架图")
    exp_fig = _fig_md(outline.get("experiment_figure_id"), figure_map, "实验结果")

    module_figures_map = outline.get("module_figures", {})

    # 编号引言现象
    obs_numbered = "\n\n".join(
        [f"[Phenomenon {i+1}]\n{obs}" for i, obs in enumerate(intro_observations)]
    )

    # 方法模块（附带各自的图片插入提示）
    modules_parts = []
    for m in method_modules:
        name = m.get("name", "")
        text = m.get("text", "")
        fid = module_figures_map.get(name)
        fig = _fig_md(fid, figure_map, name)
        fig_instruction = f"\n（翻译完本模块后请插入：{fig.strip()}）" if fig else ""
        modules_parts.append(f"[Module: {name}]{fig_instruction}\n{text}")

    modules_text = "\n\n---\n\n".join(modules_parts)
    bold_list = ", ".join(bold_terms)

    parts = [
        "你的任务是将以下论文英文原文段落翻译成中文微信公众号推文。",
        "",
        "【翻译规则（严格遵守）】",
        "1. 直译为主，忠实原文，不增加分析、评论或论文以外的内容",
        "2. 删除所有文献引用标注，例如 (Zhang et al. 2023)、(Li 2024c)、[12] 等",
        "3. 删除独立的数学公式行；若公式嵌在句子里，用简洁的文字描述替换",
        f"4. 以下术语保留英文并用 ** 加粗：{bold_list}",
        "5. 其余术语翻译成中文",
        "6. 第一人称「我们」（以论文作者口吻）",
        "7. 使用中文标点符号，书面语风格",
        "8. 各节总字数合计约 800-1000 字",
        "",
        "【需翻译的原文段落】",
        "",
        "--- 引言：关键现象 ---",
        obs_numbered,
        "",
        "--- 引言：方法总述 ---",
        intro_method_overview,
        "",
        "--- 方法各模块 ---",
        modules_text,
        "",
        "--- 实验设置 ---",
        experiment_setup,
        "",
        "--- 实验结论 ---",
        experiment_results,
        "",
        "--- 总结 ---",
        conclusion_text,
        "",
        "【输出格式】",
        "严格按以下结构输出，不输出其他内容：",
        "",
        "<<<ARTICLE_START>>>",
        f"**论文题目：** {paper_title_en}",
        f"**本文作者：** {authors_cn}",
        "",
        "## 引 言",
        "",
        "[翻译引言：先翻译各现象（编号用**（1）**格式加粗），最后1-2句翻译方法总述]",
        intro_fig,
        "## 方 法",
        "",
        "[按顺序翻译各模块：模块名**加粗**，按模块文本翻译；若有图片提示则在该模块段落后插入]",
        "",
        "## 实 验",
        "",
        "[翻译实验部分：1句实验设置，然后翻译实验结论段落（加粗关键发现名称）]",
        exp_fig,
        "## 总 结",
        "",
        "[翻译总结段落]",
        "<<<ARTICLE_END>>>",
    ]

    prompt = "\n".join(parts)
    response = _call_claude(client, prompt, max_tokens=3000)
    return _parse_body_response(response)


def _save_markdown(title: str, body: str, output_path: Path) -> None:
    output_path.write_text(f"# {title}\n\n{body}", encoding="utf-8")


def run(task_id: str, workspace: dict) -> dict:
    print_stage_header(5, "论文速读推文生成")

    outline_path = workspace["assets"] / "article_outline.json"
    wechat_dir = workspace["wechat"]

    if not outline_path.exists():
        print_error(f"大纲文件不存在: {outline_path}")
        return {"status": "failed", "error": "article_outline.json 不存在"}

    try:
        outline = load_json(outline_path)
    except Exception as e:
        print_error(f"加载大纲失败: {e}")
        return {"status": "failed", "error": str(e)}

    # 检查新格式字段是否存在
    if not outline.get("intro_observations") and not outline.get("intro_method_overview"):
        print_warning("outline 中未找到 intro_observations / intro_method_overview")
        print_warning("请重新运行 Stage 3 后再执行 Stage 5")

    try:
        client = _get_client()
    except ValueError as e:
        print_error(str(e))
        return {"status": "failed", "error": str(e)}

    figure_map = _build_figure_map(outline, workspace)
    print_info(f"可用图片映射: {len(figure_map)} 张 → {list(figure_map.keys())}")

    print_info("翻译论文原文段落为中文推文...")
    body = translate_article(client, outline, figure_map)

    if not body:
        print_error("翻译失败（空响应）")
        return {"status": "failed", "error": "翻译失败"}

    title = outline.get("article_title", outline.get("method_name", ""))
    word_count = len(body.replace(" ", "").replace("\n", ""))

    if word_count < 400:
        print_warning(f"正文字数 {word_count} 过少，可能翻译不完整")

    article = {
        "title": title,
        "digest": outline.get("conclusion", "")[:120],
        "body_markdown": body,
        "word_count": word_count,
    }
    save_json(article, wechat_dir / "wechat_article.json")
    _save_markdown(title, body, wechat_dir / "wechat_article.md")

    print_success(f"标题: {title}")
    print_success(f"正文字数: {word_count} 字")
    print_info(f"\n{'─'*50}")
    print_info("【文章预览（前600字）】")
    print_info(body[:600] + ("..." if len(body) > 600 else ""))
    print_info(f"{'─'*50}\n")

    result = {
        "status": "success",
        "article_path": str(wechat_dir / "wechat_article.json"),
        "markdown_path": str(wechat_dir / "wechat_article.md"),
        "preview": {
            "title": title,
            "word_count": word_count,
        },
    }
    save_stage_result(result, "stage5_article", workspace)
    return result
