"""
Stage 3 — 论文原文段落提取

直接从特定论文章节中摘录对应推文各节所需的原文段落。
Stage 5 将对这些原文段落进行翻译和格式化，最大程度保留论文原意。
"""

import base64
import json as _json
import os
import re
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


def _call_claude(client: OpenAI, prompt: str, max_tokens: int = 4096) -> str:
    response = client.chat.completions.create(
        model=_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def _fix_json_strings(s: str) -> str:
    result = []
    in_string = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and in_string:
            result.append(c)
            i += 1
            if i < len(s):
                result.append(s[i])
            i += 1
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
        elif in_string and c == "\n":
            result.append("\\n")
        elif in_string and c == "\r":
            result.append("\\r")
        elif in_string and c == "\t":
            result.append("\\t")
        else:
            result.append(c)
        i += 1
    return "".join(result)


def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text.strip(), flags=re.MULTILINE)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("响应中未找到 JSON 对象")
    json_str = text[start:end]
    try:
        return _json.loads(json_str)
    except _json.JSONDecodeError:
        json_str = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", json_str)
        try:
            return _json.loads(json_str)
        except _json.JSONDecodeError:
            return _json.loads(_fix_json_strings(json_str))


_INTRO_KW = {"introduction", "background", "motivation", "observation",
             "related", "preliminary", "problem", "challenge", "overview"}
_METHOD_KW = {"method", "model", "architecture", "approach", "framework",
              "network", "attention", "encoder", "decoder", "proposed",
              "design", "system", "algorithm", "module", "mechanism",
              "embedding", "encoding", "feedforward", "feed-forward",
              "position", "layer", "transformer", "head", "block"}
_EXP_KW = {"experiment", "evaluation", "result", "performance", "training",
            "ablation", "benchmark", "comparison", "setting", "dataset",
            "baseline", "variation", "influence", "translation", "parsing",
            "analysis", "schedule", "regularization", "optimizer", "hardware"}
_CONCLUSION_KW = {"conclusion", "summary", "discussion", "future", "limitation"}
_APPENDIX_KW = {"appendix", "supplement", "proof", "intuitive", "pseudocode",
                "derivation", "explanation"}


def _select_key_sections(sections: list, method_name: str = "") -> dict:
    """通用章节分组，适配不同论文结构（NLP/CV/ML 论文均可）"""
    result = {}
    mn = method_name.lower().strip()

    for s in sections:
        title = s.get("title", "").strip()
        # 去掉章节编号前缀："3.2.1 Scaled Dot-Product Attention" → "scaled dot-product attention"
        tl = re.sub(r"^[\d\.\s]+", "", title).lower().strip()
        content = s.get("content", "").strip()
        if not content:
            continue

        def has(kw_set: set) -> bool:
            return any(k in tl for k in kw_set)

        # 方法名精确匹配（最高优先级，处理 "AccKV"、"BERT" 等命名章节）
        if mn and (tl == mn or tl.startswith(mn + " ") or tl.startswith(mn + ":")):
            result["method"] = result.get("method", "") + "\n\n" + content
        elif has(_CONCLUSION_KW):
            result["conclusion"] = result.get("conclusion", "") + "\n\n" + content
        elif has(_APPENDIX_KW):
            result["appendix"] = result.get("appendix", "") + "\n\n" + content
        elif has(_EXP_KW):
            result["experiment"] = result.get("experiment", "") + "\n\n" + content
        elif has(_METHOD_KW):
            result["method"] = result.get("method", "") + "\n\n" + content
        elif has(_INTRO_KW):
            result["observation"] = result.get("observation", "") + "\n\n" + content

    return {k: v.strip() for k, v in result.items()}


def extract_metadata(client: OpenAI, meta: dict) -> dict:
    """提取论文元数据：方法名、需加粗的术语列表"""
    authors_raw = meta.get("authors", [])
    title = meta.get("title", "")
    abstract = meta.get("abstract", "")[:500]

    prompt = (
        "请根据以下论文信息，列出需要在中文推文里保留英文并加粗的核心技术术语。\n\n"
        f"论文标题：{title}\n"
        f"摘要片段：{abstract}\n\n"
        "只输出 JSON：\n"
        '{\n'
        '  "paper_title_en": "论文英文完整标题",\n'
        '  "method_name": "论文核心方法/模型名称（如 AccKV）",\n'
        '  "bold_terms": ["需保留英文并加粗的术语1", "术语2", "…"]\n'
        "}"
    )
    response = _call_claude(client, prompt, max_tokens=400)
    try:
        result = _extract_json(response)
        result["authors_cn"] = ", ".join(authors_raw)
        return result
    except Exception as e:
        logger.warning(f"元数据提取失败: {e}")
        return {
            "paper_title_en": title,
            "method_name": "",
            "authors_cn": ", ".join(authors_raw),
            "bold_terms": [],
        }


def extract_segments(client: OpenAI, sections_content: dict,
                     exp_tables_html: str = "") -> dict:
    """
    从论文原文章节中直接摘录各推文节所需的英文段落。
    使用分隔符格式避免 JSON 转义问题。
    exp_tables_html: 实验结果表格的 HTML 数据，用于让 LLM 获取真实数字。
    """
    obs = sections_content.get("observation", "")[:3500]
    method = sections_content.get("method", "")[:5000]
    appendix = sections_content.get("appendix", "")[:2000]
    experiment = sections_content.get("experiment", "")[:3000]
    conclusion = sections_content.get("conclusion", "")[:2000]

    prompt_parts = [
        "你的任务是从以下论文各章节原文中，找出并逐字摘录特定段落。",
        "不要改写、总结或补充任何内容——只摘录原文。",
        "删除数学公式行和文献引用（如 (Zhang et al. 2023)）即可。",
        "",
        "=== [OBSERVATION] ===",
        obs,
        "",
        "=== [METHOD/AccKV] ===",
        method,
        "",
        "=== [APPENDIX/Intuitive Explanation] ===",
        appendix,
        "",
        "=== [EXPERIMENT TEXT] ===",
        experiment,
        "",
    ]
    if exp_tables_html:
        prompt_parts += [
            "=== [EXPERIMENT TABLES — 真实数据，可在 EXPERIMENT_RESULTS 中引用] ===",
            exp_tables_html[:3000],
            "",
        ]
    prompt_parts += [
        "=== [CONCLUSION] ===",
        conclusion,
        "",
        "请按以下格式输出，不要输出其他内容：",
        "",
        "<<<SEGMENTS_START>>>",
        "INTRO_OBSERVATIONS:",
        "[从 OBSERVATION 章节摘录每个关键现象的描述段落，现象之间用「---」分隔]",
        "",
        "INTRO_METHOD_OVERVIEW:",
        "[从 METHOD 章节摘录介绍整体框架的第一段（从 'In this section' 或 'we propose' 开始的段落）]",
        "",
        "METHOD_MODULES:",
        "[模块英文名1]",
        "###",
        "[从 METHOD 和 APPENDIX 中摘录该模块的完整描述段落]",
        "---",
        "[模块英文名2]",
        "###",
        "[该模块的完整描述段落]",
        "---",
        "[如有更多模块继续]",
        "",
        "EXPERIMENT_SETUP:",
        "[从 EXPERIMENT 章节摘录说明在哪些模型/数据集上验证的1-2句话]",
        "",
        "EXPERIMENT_RESULTS:",
        "[从 EXPERIMENT 章节摘录最重要的结论段落；若提供了 EXPERIMENT TABLES，可引用表格中的具体数值（如准确率对比），但只引用表格里真实存在的数字]",
        "",
        "CONCLUSION:",
        "[从 CONCLUSION 章节摘录核心总结段落]",
        "<<<SEGMENTS_END>>>",
    ]
    prompt = "\n".join(prompt_parts)

    response = _call_claude(client, prompt, max_tokens=4096)
    return _parse_segments(response)


def _parse_segments(response: str) -> dict:
    """解析分隔符格式的摘录输出"""
    start = response.find("<<<SEGMENTS_START>>>")
    end = response.find("<<<SEGMENTS_END>>>")
    if start == -1 or end == -1:
        logger.error(f"未找到段落分隔符，原始响应前300字: {response[:300]}")
        return {}
    content = response[start + len("<<<SEGMENTS_START>>>"):end].strip()

    headers = ["INTRO_OBSERVATIONS", "INTRO_METHOD_OVERVIEW", "METHOD_MODULES",
               "EXPERIMENT_SETUP", "EXPERIMENT_RESULTS", "CONCLUSION"]

    def get_section(header: str) -> str:
        tag = f"{header}:"
        idx = content.find(tag)
        if idx == -1:
            return ""
        start_idx = idx + len(tag)
        end_idx = len(content)
        for h in headers:
            if h == header:
                continue
            hi = content.find(f"\n{h}:", start_idx)
            if hi != -1 and hi < end_idx:
                end_idx = hi
        return content[start_idx:end_idx].strip()

    result = {}

    # 引言现象（以 --- 分隔）
    obs_text = get_section("INTRO_OBSERVATIONS")
    result["intro_observations"] = [p.strip() for p in obs_text.split("---") if p.strip()]

    result["intro_method_overview"] = get_section("INTRO_METHOD_OVERVIEW")

    # 方法模块（模块名 + ### + 描述，以 --- 分隔）
    modules_text = get_section("METHOD_MODULES")
    modules = []
    for block in modules_text.split("---"):
        block = block.strip()
        if "###" in block:
            parts = block.split("###", 1)
            name = parts[0].strip()
            text = parts[1].strip()
            if name and text:
                modules.append({"name": name, "text": text})
    result["method_modules"] = modules

    result["experiment_setup"] = get_section("EXPERIMENT_SETUP")
    result["experiment_results"] = get_section("EXPERIMENT_RESULTS")
    result["conclusion"] = get_section("CONCLUSION")

    return result


def analyze_figure(client: OpenAI, figure: dict) -> dict:
    """分析单张论文图片，判断在推文中的用途"""
    img_path = Path(figure.get("image_path", ""))
    caption = figure.get("caption", "")

    if not img_path.exists():
        return {
            "figure_id": figure.get("figure_id", ""),
            "figure_type": "unknown",
            "description": caption,
            "importance_score": 0.5,
            "suitable_for_cover": False,
            "suitable_for_article": True,
            "wechat_caption": caption[:80] if caption else "",
            "article_position_hint": "method",
            "image_path": figure.get("image_path", ""),
        }

    with open(img_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")
    suffix = img_path.suffix.lower()
    media_type_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    media_type = media_type_map.get(suffix, "image/png")

    prompt = (
        f"请分析这张来自学术论文的图片。图片说明：{caption}\n\n"
        "用 JSON 格式回答：\n"
        "{\n"
        '  "figure_type": "framework/result_table/comparison_chart/ablation/diagram/other",\n'
        '  "description": "图片内容简洁描述（1-2句）",\n'
        '  "importance_score": 0.0到1.0,\n'
        '  "suitable_for_cover": true或false（横版构图、视觉清晰才适合封面）,\n'
        '  "suitable_for_article": true或false,\n'
        '  "wechat_caption": "适合公众号的简短图注（≤50字，中文）",\n'
        '  "article_position_hint": "method/experiment/introduction/conclusion"\n'
        "}\n只输出 JSON。"
    )

    try:
        response = client.chat.completions.create(
            model=_MODEL,
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_data}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = response.choices[0].message.content
        result = _extract_json(raw)
        result["figure_id"] = figure.get("figure_id", "")
        result["image_path"] = figure.get("image_path", "")
        return result
    except Exception as e:
        logger.warning(f"图片分析失败 {img_path}: {e}")
        return {
            "figure_id": figure.get("figure_id", ""),
            "figure_type": "unknown",
            "description": caption,
            "importance_score": 0.5,
            "suitable_for_cover": False,
            "suitable_for_article": True,
            "wechat_caption": caption[:80] if caption else "",
            "article_position_hint": "method",
            "image_path": figure.get("image_path", ""),
        }


def _validate(understanding: dict) -> dict:
    return {
        "method_name": bool(understanding.get("method_name")),
        "intro_observations": len(understanding.get("intro_observations", [])) > 0,
        "method_modules": len(understanding.get("method_modules", [])) > 0,
        "experiment_results": bool(understanding.get("experiment_results")),
    }


def _classify_table(caption: str, html: str) -> str:
    """根据 caption/html 判断表格属于哪个文章节"""
    cl = caption.lower()
    # 主结果对比表：明确标注了模型名或基准集，且是 eviction strategy 对比
    if any(k in cl for k in ("eviction strategy", "videollama", "avicuna", "mvbench", "avsd")):
        return "experiment"
    if "ablation" in cl:
        return "experiment"
    # 观察/动机实验：验证论文提出的三个现象，属于引言节
    if any(k in cl for k in ("evict", "heterogeneous", "merging", "evicting all")):
        return "introduction"
    # 空 caption 的表（如 tab_4）：看 HTML 内容判断
    if not caption and ("20% cache budget" in html.lower() or "h2o" in html.lower()):
        return "experiment"
    return "experiment"


def run(task_id: str, workspace: dict) -> dict:
    print_stage_header(3, "论文原文段落提取")

    parsed_dir = workspace["parsed"]
    understanding_dir = workspace["understanding"]

    try:
        meta = load_json(parsed_dir / "paper_meta.json")
        sections = load_json(parsed_dir / "sections.json")
        figures_index = load_json(parsed_dir / "figures_index.json")
    except FileNotFoundError as e:
        print_error(f"解析文件不存在: {e}")
        return {"status": "failed", "error": str(e)}

    # 加载表格索引
    tables_index = []
    tables_path = parsed_dir / "tables_index.json"
    if tables_path.exists():
        tables_index = load_json(tables_path)
        print_info(f"加载表格索引: {len(tables_index)} 张")
    else:
        print_warning("tables_index.json 不存在，跳过表格（可重新跑 Stage 2 生成）")

    try:
        client = _get_client()
    except ValueError as e:
        print_error(str(e))
        return {"status": "failed", "error": str(e)}

    # 元数据提取（方法名、中文作者、加粗术语）
    print_info("提取论文元数据（方法名、作者、术语）...")
    metadata = extract_metadata(client, meta)
    print_info(f"  方法名: {metadata.get('method_name')}")
    print_info(f"  作者: {metadata.get('authors_cn', '')[:60]}...")

    # 选取关键章节（传入方法名做精确匹配）
    sections_content = _select_key_sections(sections, method_name=metadata.get("method_name", ""))
    print_info(f"关键章节: {list(sections_content.keys())}")
    for k, v in sections_content.items():
        print_info(f"  {k}: {len(v)} chars")

    # 构建表格 HTML 补充（注入实验上下文，让 LLM 看到真实数字）
    exp_tables_html = ""
    if tables_index:
        exp_tables = [t for t in tables_index
                      if _classify_table(t.get("caption", ""), t.get("html", "")) == "experiment"
                      and t.get("html")]
        if exp_tables:
            parts = []
            for t in exp_tables:
                cap = t.get("caption", t.get("table_id", ""))
                parts.append(f"[{cap}]\n{t['html']}")
            exp_tables_html = "\n\n".join(parts)
            print_info(f"注入实验表格数据: {len(exp_tables)} 张")

    # 原文段落摘录
    print_info("从论文章节摘录原文段落...")
    segments = extract_segments(client, sections_content, exp_tables_html=exp_tables_html)

    if not segments:
        print_error("段落摘录失败（空响应）")
        return {"status": "failed", "error": "段落摘录失败"}

    print_success(f"引言现象: {len(segments.get('intro_observations', []))} 条")
    print_success(f"方法模块: {len(segments.get('method_modules', []))} 个")
    for m in segments.get("method_modules", []):
        print_info(f"  {m.get('name', '')}")

    # 图片分析（论文插图）
    important_figures = []
    print_info(f"分析图片（共 {len(figures_index)} 张）...")
    for fig in figures_index:
        result = analyze_figure(client, fig)
        important_figures.append(result)
        cover_ok = "✓ 封面候选" if result.get("suitable_for_cover") else "  不适合封面"
        print_info(f"  {fig.get('figure_id')}: {cover_ok} (score={result.get('importance_score', 0):.1f})")

    # 表格图片：不需要 LLM 分析，直接按 caption 分类加入 important_figures
    if tables_index:
        print_info(f"纳入表格图片（共 {len(tables_index)} 张）...")
        for tab in tables_index:
            caption = tab.get("caption", "")
            html = tab.get("html", "")
            pos = _classify_table(caption, html)
            cl = caption.lower()
            # 主结果对比表（含模型名/基准名）得分最高；消融表次之；其他较低
            if any(k in cl for k in ("eviction strategy", "videollama", "avicuna", "mvbench")):
                score = 0.95
            elif "ablation" in cl:
                score = 0.75
            elif pos == "experiment":
                score = 0.80
            else:
                score = 0.60
            entry = {
                "figure_id": tab["table_id"],
                "figure_type": "result_table",
                "description": caption[:120] if caption else tab["table_id"],
                "importance_score": score,
                "suitable_for_cover": False,
                "suitable_for_article": True,
                "wechat_caption": (caption[:60] if caption else ""),
                "article_position_hint": pos,
                "image_path": tab.get("image_path", ""),
                "is_table": True,
            }
            important_figures.append(entry)
            print_info(f"  {tab['table_id']} ({score:.2f}) → {pos}: {caption[:60]}")

    # 合并所有信息
    understanding = {
        "paper_title": meta.get("title", ""),
        "paper_title_en": metadata.get("paper_title_en", meta.get("title", "")),
        "authors": meta.get("authors", []),
        "authors_cn": metadata.get("authors_cn", ""),
        "method_name": metadata.get("method_name", ""),
        "bold_terms": metadata.get("bold_terms", []),
        # 原文段落
        "intro_observations": segments.get("intro_observations", []),
        "intro_method_overview": segments.get("intro_method_overview", ""),
        "method_modules": segments.get("method_modules", []),
        "experiment_setup": segments.get("experiment_setup", ""),
        "experiment_results": segments.get("experiment_results", ""),
        "conclusion": segments.get("conclusion", ""),
        # 图片（含表格）
        "important_figures": important_figures,
    }

    checks = _validate(understanding)
    failed = [k for k, v in checks.items() if not v]
    if failed:
        print_warning(f"验证警告: {failed}")

    if not checks["method_name"] or not checks["intro_observations"]:
        print_error("核心字段为空（method_name / intro_observations）")
        return {"status": "failed", "error": "核心字段为空", "validation": checks}

    save_json(understanding, understanding_dir / "paper_understanding.json")

    result = {
        "status": "success",
        "understanding_path": str(understanding_dir / "paper_understanding.json"),
        "validation": checks,
        "stats": {
            "intro_observations": len(understanding["intro_observations"]),
            "method_modules": len(understanding["method_modules"]),
            "important_figures": len(important_figures),
        },
    }
    save_stage_result(result, "stage3_understanding", workspace)
    return result
