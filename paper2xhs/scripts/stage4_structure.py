"""
Stage 4 — 内容结构化
将学术理解转化为社交媒体内容素材
输出：content_assets.json
"""

import json
import os
from pathlib import Path

import anthropic

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


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("未设置 ANTHROPIC_API_KEY 环境变量")
    return anthropic.Anthropic(api_key=api_key)


def _call_claude(client: anthropic.Anthropic, prompt: str, max_tokens: int = 2048) -> str:
    with client.messages.stream(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        return stream.get_final_text()


def _extract_json(response: str) -> dict:
    """从 Claude 响应中提取 JSON"""
    start = response.find("{")
    end = response.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    return json.loads(response[start:end])


def generate_content_assets(client: anthropic.Anthropic, understanding: dict) -> dict:
    """
    将论文理解转化为小红书内容素材
    提取：情感钩子、社会价值、实用影响、受众相关性
    """
    prompt = f"""你是一位擅长将学术论文转化为小红书爆款内容的创作者。
请根据以下论文理解，生成小红书内容素材。

【论文信息】
标题：{understanding.get('paper_title', '')}
核心问题：{understanding.get('problem', '')}
研究动机：{understanding.get('motivation', '')}
方法名称：{understanding.get('method_name', '')}
方法概述：{understanding.get('method', '')}
创新点：{understanding.get('novelty', '')}
论文亮点：{json.dumps(understanding.get('highlights', []), ensure_ascii=False)}
实验结果：{json.dumps(understanding.get('experiment_results', []), ensure_ascii=False)}
一句话总结：{understanding.get('one_sentence_summary', '')}
目标受众：{json.dumps(understanding.get('target_audience', []), ensure_ascii=False)}
关键词：{json.dumps(understanding.get('keywords', []), ensure_ascii=False)}

请生成以下内容素材，用 JSON 格式输出：
{{
  "title_hooks": [
    "标题候选1（吸引眼球，包含核心价值）",
    "标题候选2（问题式，引发好奇）",
    "标题候选3（结果导向，突出数字）",
    "标题候选4（对比式，突出优势）",
    "标题候选5（实用价值导向）"
  ],
  "core_points": [
    "核心要点1（简洁，可直接用于正文）",
    "核心要点2",
    "核心要点3",
    "核心要点4",
    "核心要点5"
  ],
  "technical_advantages": [
    "技术优势1（相比现有方法）",
    "技术优势2",
    "技术优势3"
  ],
  "practical_values": [
    "实际应用价值1（对读者有什么用）",
    "实际应用价值2",
    "实际应用价值3"
  ],
  "audience_tags": [
    "#标签1",
    "#标签2",
    "#标签3",
    "#标签4",
    "#标签5",
    "#标签6",
    "#标签7",
    "#标签8"
  ],
  "emotion_points": [
    "情感共鸣点1（读者痛点或期待）",
    "情感共鸣点2"
  ],
  "cover_text_candidates": [
    "封面文字候选1（简短有力，≤15字）",
    "封面文字候选2",
    "封面文字候选3"
  ],
  "opening_hooks": [
    "开头钩子1（第一句话，抓住读者注意力）",
    "开头钩子2"
  ]
}}

注意：
- 标题要符合小红书风格，吸引 AI 研究者和技术爱好者
- 内容要准确反映论文贡献，不夸大
- 语言要口语化、易读，避免过于学术化
- 标签要包含领域标签和热门标签

只输出 JSON，不要其他内容。"""

    response = _call_claude(client, prompt, max_tokens=3000)
    try:
        return _extract_json(response)
    except Exception as e:
        logger.error(f"内容素材生成解析失败: {e}\n原始响应: {response[:500]}")
        return {}


def _validate(assets: dict) -> dict:
    checks = {
        "title_hooks": len(assets.get("title_hooks", [])) >= 1,
        "core_points": len(assets.get("core_points", [])) >= 3,
        "practical_values": len(assets.get("practical_values", [])) >= 1,
        "audience_tags": len(assets.get("audience_tags", [])) >= 1,
        "cover_text_candidates": len(assets.get("cover_text_candidates", [])) >= 1,
    }
    return checks


def run(task_id: str, workspace: dict) -> dict:
    """
    执行 Stage 4：内容结构化

    输入：workspace["understanding"]/paper_understanding.json
    输出：workspace["assets"]/content_assets.json
    """
    print_stage_header(4, "内容结构化")

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

    print_info("生成内容素材...")
    assets = generate_content_assets(client, understanding)

    if not assets:
        print_error("内容素材生成失败（空响应）")
        return {"status": "failed", "error": "内容素材生成失败"}

    # 验证
    checks = _validate(assets)
    failed = [k for k, v in checks.items() if not v]
    if failed:
        print_warning(f"部分内容素材不足: {failed}")

    if not checks["title_hooks"] or not checks["core_points"]:
        print_error("核心内容素材（标题/要点）生成失败")
        return {"status": "failed", "error": "核心内容素材不足", "validation": checks}

    # 保存
    save_json(assets, assets_dir / "content_assets.json")

    print_success(f"标题候选: {len(assets.get('title_hooks', []))} 个")
    print_success(f"核心要点: {len(assets.get('core_points', []))} 个")
    print_success(f"受众标签: {len(assets.get('audience_tags', []))} 个")

    result = {
        "status": "success",
        "assets_path": str(assets_dir / "content_assets.json"),
        "validation": checks,
        "stats": {
            "title_hooks": len(assets.get("title_hooks", [])),
            "core_points": len(assets.get("core_points", [])),
            "audience_tags": len(assets.get("audience_tags", [])),
        },
    }
    save_stage_result(result, "stage4_assets", workspace)
    return result
