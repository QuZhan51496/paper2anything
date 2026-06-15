"""
Stage 4 — 公众号大纲结构化

输出固定 4 节结构：引言 / 方法 / 实验 / 总结
并为每个章节/模块分配最合适的论文图片。
"""

import json
import os

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


def _call_claude(client: OpenAI, prompt: str, max_tokens: int = 2000) -> str:
    response = client.chat.completions.create(
        model=_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def _extract_json(response: str) -> dict:
    import re
    response = re.sub(r"^```(?:json)?\s*", "", response.strip(), flags=re.MULTILINE)
    response = re.sub(r"\s*```\s*$", "", response.strip(), flags=re.MULTILINE)
    start = response.find("{")
    end = response.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    json_str = response[start:end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        json_str = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", json_str)
        return json.loads(json_str)


def assign_figures(client: OpenAI, understanding: dict) -> dict:
    """
    让 LLM 根据图片信息和文章结构，为每个位置分配最合适的图片。

    返回结构：
    {
      "article_title": "方法名：简洁描述",
      "cover_figure_id": "fig_X",
      "intro_figure_id": "fig_X 或 null",
      "module_figures": {
        "模块名1": "fig_X 或 null",
        "模块名2": "fig_X 或 null",
        ...
      },
      "experiment_figure_id": "fig_X 或 null"
    }
    """
    method_name = understanding.get("method_name", "")
    figures = understanding.get("important_figures", [])
    method_modules = understanding.get("method_modules", [])
    module_names = [m.get("name", "") for m in method_modules]

    figures_desc = []
    for fig in figures:
        figures_desc.append({
            "figure_id": fig.get("figure_id", ""),
            "figure_type": fig.get("figure_type", ""),
            "description": fig.get("description", ""),
            "importance_score": fig.get("importance_score", 0),
            "suitable_for_cover": fig.get("suitable_for_cover", False),
        })

    prompt = f"""你是一位微信公众号编辑，需要为一篇"论文速读"文章分配图片。

论文方法名：{method_name}
方法模块列表：{json.dumps(module_names, ensure_ascii=False)}

可用图片（来自论文）：
{json.dumps(figures_desc, ensure_ascii=False, indent=2)}

文章结构为固定 4 节：
1. 引 言：介绍背景和关键观察，需要一张总览性框架图（如果有）
2. 方 法：逐模块介绍，每个模块可配一张对应图
3. 实 验：实验结果，需要一张实验结果图（表格或对比图）
4. 总 结：无需图片

请为文章各位置分配最合适的图片。每张图只能使用一次。如果没有合适的图就填 null。

只输出 JSON，不要其他内容：
{{
  "article_title": "{method_name}：[20字以内的中文描述，说明方法解决什么问题]",
  "cover_figure_id": "最适合作封面的图片 ID（优先选框架总览图）",
  "intro_figure_id": "引言部分配图（总览框架图），或 null",
  "module_figures": {{
    "{module_names[0] if module_names else '模块1'}": "fig_X 或 null",
    {chr(10).join(f'    "{n}": "fig_X 或 null",' for n in module_names[1:])}
  }},
  "experiment_figure_id": "实验结果图 ID 或 null"
}}"""

    response = _call_claude(client, prompt, max_tokens=1000)
    try:
        return _extract_json(response)
    except Exception as e:
        logger.error(f"图片分配解析失败: {e}\n原始响应: {response[:300]}")
        return {}


def run(task_id: str, workspace: dict) -> dict:
    print_stage_header(4, "公众号大纲结构化（固定4节）")

    understanding_path = workspace["understanding"] / "paper_understanding.json"
    assets_dir = workspace["assets"]

    if not understanding_path.exists():
        print_error(f"论文理解文件不存在: {understanding_path}")
        return {"status": "failed", "error": "paper_understanding.json 不存在"}

    try:
        understanding = load_json(understanding_path)
    except Exception as e:
        print_error(f"加载论文理解失败: {e}")
        return {"status": "failed", "error": str(e)}

    try:
        client = _get_client()
    except ValueError as e:
        print_error(str(e))
        return {"status": "failed", "error": str(e)}

    print_info("分配图片到各章节/模块...")
    layout = assign_figures(client, understanding)

    if not layout:
        print_warning("图片分配失败，使用空布局继续")
        layout = {
            "article_title": understanding.get("method_name", ""),
            "cover_figure_id": None,
            "intro_figure_id": None,
            "module_figures": {},
            "experiment_figure_id": None,
        }

    # 将 understanding 中的关键信息合并进 layout，供 Stage 5 直接使用
    outline = {
        **layout,
        "paper_title_en": understanding.get("paper_title_en", understanding.get("paper_title", "")),
        "authors_cn": understanding.get("authors_cn", ""),
        "method_name": understanding.get("method_name", ""),
        "bold_terms": understanding.get("bold_terms", []),
        # 原文段落
        "intro_observations": understanding.get("intro_observations", []),
        "intro_method_overview": understanding.get("intro_method_overview", ""),
        "method_modules": understanding.get("method_modules", []),  # [{name, text}]
        "experiment_setup": understanding.get("experiment_setup", ""),
        "experiment_results": understanding.get("experiment_results", ""),
        "conclusion": understanding.get("conclusion", ""),
    }

    save_json(outline, assets_dir / "article_outline.json")

    print_success(f"标题: {layout.get('article_title', '')}")
    print_success(f"封面图: {layout.get('cover_figure_id', 'null')}")
    print_success(f"引言配图: {layout.get('intro_figure_id', 'null')}")
    print_info("模块配图:")
    for mod, fig in layout.get("module_figures", {}).items():
        print_info(f"  {mod[:30]} → {fig}")
    print_success(f"实验配图: {layout.get('experiment_figure_id', 'null')}")

    result = {
        "status": "success",
        "outline_path": str(assets_dir / "article_outline.json"),
        "stats": {
            "modules": len(layout.get("module_figures", {})),
            "figures_assigned": sum(1 for v in [
                layout.get("cover_figure_id"),
                layout.get("intro_figure_id"),
                layout.get("experiment_figure_id"),
            ] + list(layout.get("module_figures", {}).values()) if v and v != "null"),
        },
    }
    save_stage_result(result, "stage4_outline", workspace)
    return result
