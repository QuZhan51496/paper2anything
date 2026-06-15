"""
Stage 3 — 论文理解
使用 Claude Sonnet 深度理解论文内容
采用模块化 prompt 函数，分步骤调用，避免单次超长 prompt
"""

import base64
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

# ─────────────────────────────────────────────
# Claude 客户端初始化
# ─────────────────────────────────────────────

def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("未设置 ANTHROPIC_API_KEY 环境变量")
    return anthropic.Anthropic(api_key=api_key)


def _call_claude(client: anthropic.Anthropic, prompt: str, max_tokens: int = 2048) -> str:
    """调用 Claude，使用流式请求避免代理超时"""
    with client.messages.stream(
        model=os.environ.get("CLAUDE_FAST_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        return stream.get_final_text()


def _call_claude_with_image(
    client: anthropic.Anthropic,
    prompt: str,
    image_path: Path,
    max_tokens: int = 1024,
) -> str:
    """调用 Claude Sonnet，附带图片"""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    suffix = image_path.suffix.lower()
    media_type_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    media_type = media_type_map.get(suffix, "image/png")

    message = client.messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return message.content[0].text


# ─────────────────────────────────────────────
# 辅助：构建论文上下文
# ─────────────────────────────────────────────

def _build_paper_context(meta: dict, sections: list, max_chars: int = 4000) -> str:
    """将论文 PIR 拼接为 LLM 可读的上下文文本，限制总长度"""
    parts = []
    parts.append(f"【论文标题】{meta.get('title', '未知')}")
    if meta.get("authors"):
        parts.append(f"【作者】{', '.join(meta['authors'][:5])}")
    if meta.get("abstract"):
        parts.append(f"【摘要】\n{meta['abstract']}")

    parts.append("\n【正文章节】")
    total = sum(len(p) for p in parts)

    for sec in sections:
        title = sec.get("title", "")
        content = sec.get("content", "")
        # 跳过参考文献章节
        if title.lower() in ("references", "参考文献", "bibliography", "acknowledgments", "acknowledgements"):
            continue
        chunk = f"\n## {title}\n{content[:2000]}"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)

    return "\n".join(parts)


# ─────────────────────────────────────────────
# 模块化 Prompt 函数
# ─────────────────────────────────────────────

def analyze_all(client: anthropic.Anthropic, paper_context: str) -> dict:
    """一次调用完成所有分析，避免多次请求超时"""
    import json as _json
    prompt = f"""你是一位 AI 研究领域的专家，同时熟悉小红书等社交媒体内容风格。
请分析以下论文，用一次 JSON 回答所有问题。

{paper_context}

请用以下 JSON 格式输出（只输出 JSON，不要其他内容）：
{{
  "problem": "核心问题（1-2句）",
  "motivation": "研究动机（2-3句）",
  "research_gap": "现有方法不足（1句）",
  "method_name": "方法/模型名称",
  "method_summary": "方法核心思路（2-3句）",
  "key_components": ["关键组件1", "关键组件2", "关键组件3"],
  "novelty": "创新点（1句）",
  "datasets": ["数据集1", "数据集2"],
  "baselines": ["对比方法1", "对比方法2"],
  "main_results": ["主要结论1（含数字）", "主要结论2"],
  "ablation_insights": "消融实验发现（如有，否则空字符串）",
  "highlights": ["亮点1", "亮点2", "亮点3"],
  "one_sentence_summary": "一句话概括核心贡献",
  "target_audience": ["目标读者1", "目标读者2"],
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
}}"""

    response = _call_claude(client, prompt, max_tokens=2000)
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        return _json.loads(response[start:end])
    except Exception:
        return {}


def analyze_problem(client: anthropic.Anthropic, paper_context: str) -> dict:
    """分析论文解决的问题和动机"""
    prompt = f"""你是一位 AI 研究领域的专家。请分析以下论文，提取核心问题和研究动机。

{paper_context}

请用 JSON 格式回答，包含以下字段：
{{
  "problem": "这篇论文解决的核心问题（1-2句话）",
  "motivation": "研究动机和背景（2-3句话）",
  "research_gap": "现有方法的不足之处（1-2句话）"
}}

只输出 JSON，不要其他内容。"""

    response = _call_claude(client, prompt)
    try:
        import json
        # 提取 JSON 部分
        start = response.find("{")
        end = response.rfind("}") + 1
        return json.loads(response[start:end])
    except Exception:
        return {"problem": response[:500], "motivation": "", "research_gap": ""}


def analyze_method(client: anthropic.Anthropic, paper_context: str) -> dict:
    """分析论文方法"""
    prompt = f"""你是一位 AI 研究领域的专家。请分析以下论文的方法论。

{paper_context}

请用 JSON 格式回答：
{{
  "method_name": "方法/模型名称",
  "method_summary": "方法核心思路（2-3句话）",
  "key_components": ["关键组件1", "关键组件2", "关键组件3"],
  "novelty": "相比现有方法的创新点（1-2句话）"
}}

只输出 JSON，不要其他内容。"""

    response = _call_claude(client, prompt)
    try:
        import json
        start = response.find("{")
        end = response.rfind("}") + 1
        return json.loads(response[start:end])
    except Exception:
        return {"method_name": "", "method_summary": response[:500], "key_components": [], "novelty": ""}


def analyze_experiments(client: anthropic.Anthropic, paper_context: str) -> dict:
    """分析实验结果"""
    prompt = f"""你是一位 AI 研究领域的专家。请分析以下论文的实验结果。

{paper_context}

请用 JSON 格式回答：
{{
  "datasets": ["使用的数据集1", "数据集2"],
  "baselines": ["对比方法1", "对比方法2"],
  "main_results": ["主要实验结论1（包含具体数字）", "主要实验结论2"],
  "ablation_insights": "消融实验的关键发现（如有）"
}}

只输出 JSON，不要其他内容。"""

    response = _call_claude(client, prompt)
    try:
        import json
        start = response.find("{")
        end = response.rfind("}") + 1
        return json.loads(response[start:end])
    except Exception:
        return {"datasets": [], "baselines": [], "main_results": [response[:300]], "ablation_insights": ""}


def extract_highlights(client: anthropic.Anthropic, paper_context: str) -> dict:
    """提取论文亮点"""
    prompt = f"""你是一位 AI 研究领域的专家，同时熟悉小红书等社交媒体的内容风格。
请分析以下论文，提取最值得在社交媒体上分享的亮点。

{paper_context}

请用 JSON 格式回答：
{{
  "highlights": [
    "亮点1：具体、有数据支撑的结论",
    "亮点2：方法上的创新",
    "亮点3：实际应用价值"
  ],
  "one_sentence_summary": "用一句话概括这篇论文的核心贡献",
  "target_audience": ["目标读者群体1", "目标读者群体2"],
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
}}

只输出 JSON，不要其他内容。"""

    response = _call_claude(client, prompt)
    try:
        import json
        start = response.find("{")
        end = response.rfind("}") + 1
        return json.loads(response[start:end])
    except Exception:
        return {
            "highlights": [response[:300]],
            "one_sentence_summary": "",
            "target_audience": ["AI 研究者"],
            "keywords": [],
        }


def analyze_figure(client: anthropic.Anthropic, figure: dict) -> dict:
    """分析单张图片（如果图片文件存在）"""
    img_path = Path(figure.get("image_path", ""))
    caption = figure.get("caption", "")

    if not img_path.exists():
        return {
            "figure_id": figure.get("figure_id", ""),
            "figure_type": "unknown",
            "description": caption,
            "importance_score": 0.5,
        }

    prompt = f"""请分析这张来自学术论文的图片。
图片说明（caption）：{caption}

请用 JSON 格式回答：
{{
  "figure_type": "framework/result/comparison/diagram/other 中的一个",
  "description": "图片内容的简洁描述（1-2句话）",
  "importance_score": 0.0到1.0之间的重要性评分,
  "suitable_for_cover": true或false（是否适合作为小红书封面）
}}

只输出 JSON，不要其他内容。"""

    try:
        response = _call_claude_with_image(client, prompt, img_path)
        import json
        start = response.find("{")
        end = response.rfind("}") + 1
        result = json.loads(response[start:end])
        result["figure_id"] = figure.get("figure_id", "")
        return result
    except Exception as e:
        logger.warning(f"图片分析失败 {img_path}: {e}")
        return {
            "figure_id": figure.get("figure_id", ""),
            "figure_type": "unknown",
            "description": caption,
            "importance_score": 0.5,
            "suitable_for_cover": False,
        }


# ─────────────────────────────────────────────
# 验证
# ─────────────────────────────────────────────

def _validate(understanding: dict) -> dict:
    checks = {
        "problem": bool(understanding.get("problem")),
        "method": bool(understanding.get("method")),
        "highlights": len(understanding.get("highlights", [])) > 0,
        "experiment_results": len(understanding.get("experiment_results", [])) > 0,
    }
    return checks


# ─────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────

def run(task_id: str, workspace: dict) -> dict:
    """
    执行 Stage 3：论文理解

    输入：workspace["parsed"]/ 下的 PIR 文件
    输出：workspace["understanding"]/paper_understanding.json
    """
    print_stage_header(3, "论文理解（Claude Sonnet）")

    parsed_dir = workspace["parsed"]
    understanding_dir = workspace["understanding"]

    # 加载 PIR
    try:
        meta = load_json(parsed_dir / "paper_meta.json")
        sections = load_json(parsed_dir / "sections.json")
        figures_index = load_json(parsed_dir / "figures_index.json")
    except FileNotFoundError as e:
        print_error(f"PIR 文件不存在: {e}")
        return {"status": "failed", "error": str(e)}

    # 初始化 Claude 客户端
    try:
        client = _get_client()
    except ValueError as e:
        print_error(str(e))
        return {"status": "failed", "error": str(e)}

    # 构建论文上下文
    paper_context = _build_paper_context(meta, sections)
    print_info(f"论文上下文长度: {len(paper_context)} 字符")

    # ── 合并分析（单次 Claude 调用）──
    print_info("一次性分析论文（问题/方法/实验/亮点）...")
    analysis = analyze_all(client, paper_context)

    # ── 图片分析：用 Claude 视觉评估各图，判断是否适合封面 ──
    important_figures = []
    print_info(f"分析论文图片（共 {len(figures_index)} 张）...")
    for fig in figures_index:
        result = analyze_figure(client, fig)
        result["image_path"] = fig.get("image_path", "")
        important_figures.append(result)
        label = "✓ 适合封面" if result.get("suitable_for_cover") else "  不适合"
        print_info(f"  {fig.get('figure_id', '')}: {label} (score={result.get('importance_score', 0):.1f})")

    # ── 组装 paper_understanding.json ──
    understanding = {
        "paper_title": meta.get("title", ""),
        "authors": meta.get("authors", []),
        "problem": analysis.get("problem", ""),
        "motivation": analysis.get("motivation", ""),
        "research_gap": analysis.get("research_gap", ""),
        "method": analysis.get("method_summary", ""),
        "method_name": analysis.get("method_name", ""),
        "key_components": analysis.get("key_components", []),
        "novelty": analysis.get("novelty", ""),
        "highlights": analysis.get("highlights", []),
        "one_sentence_summary": analysis.get("one_sentence_summary", ""),
        "experiment_results": analysis.get("main_results", []),
        "datasets": analysis.get("datasets", []),
        "baselines": analysis.get("baselines", []),
        "ablation_insights": analysis.get("ablation_insights", ""),
        "target_audience": analysis.get("target_audience", []),
        "keywords": analysis.get("keywords", []),
        "important_figures": important_figures,
    }

    # ── 验证 ──
    checks = _validate(understanding)
    failed = [k for k, v in checks.items() if not v]
    if failed:
        print_warning(f"验证警告（部分字段为空）: {failed}")
        # 非致命性失败，继续执行

    if not checks["problem"] or not checks["method"]:
        print_error("核心字段（problem/method）为空，验证失败")
        return {"status": "failed", "error": "核心理解字段为空", "validation": checks}

    # ── 保存 ──
    save_json(understanding, understanding_dir / "paper_understanding.json")

    print_success(f"论文理解完成")
    print_success(f"核心问题: {understanding['problem'][:80]}...")
    print_success(f"亮点数量: {len(understanding['highlights'])}")

    result = {
        "status": "success",
        "understanding_path": str(understanding_dir / "paper_understanding.json"),
        "validation": checks,
        "stats": {
            "highlights": len(understanding["highlights"]),
            "experiment_results": len(understanding["experiment_results"]),
            "important_figures": len(important_figures),
        },
    }
    save_stage_result(result, "stage3_understanding", workspace)
    return result
