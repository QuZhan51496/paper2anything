"""
Stage 5 — 小红书内容生成
使用固定 Prompt 模板生成小红书帖子
输出：xhs_post.json
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


def _call_claude(client: anthropic.Anthropic, prompt: str, max_tokens: int = 3000) -> str:
    with client.messages.stream(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        return stream.get_final_text()


def _fix_json_newlines(s: str) -> str:
    """Escape literal newlines inside JSON string values."""
    result = []
    in_string = False
    escape_next = False
    for char in s:
        if escape_next:
            result.append(char)
            escape_next = False
        elif char == "\\":
            result.append(char)
            escape_next = True
        elif char == '"':
            in_string = not in_string
            result.append(char)
        elif char == "\n" and in_string:
            result.append("\\n")
        else:
            result.append(char)
    return "".join(result)


def _extract_json(response: str) -> dict:
    from json_repair import repair_json
    start = response.find("{")
    end = response.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    json_str = response[start:end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return json.loads(repair_json(json_str))


# ─────────────────────────────────────────────
# 固定 Prompt 模板（V1）
# 预留 extension_hooks 供未来个性化扩展
# ─────────────────────────────────────────────

def generate_xhs_post(
    client: anthropic.Anthropic,
    understanding: dict,
    assets: dict,
    # extension_hooks（未来扩展用，V1 不使用）
    # writing_style: str = "default",
    # user_persona: str = None,
) -> dict:
    """
    使用固定模板生成小红书帖子
    V1 固定风格：简洁、社交媒体友好、面向 AI 研究者、小红书风格
    """

    title_hooks = assets.get("title_hooks", [""])
    core_points = assets.get("core_points", [])
    experiment_results = understanding.get("experiment_results", [])
    highlights = understanding.get("highlights", [])
    audience_tags = assets.get("audience_tags", [])
    cover_text_candidates = assets.get("cover_text_candidates", [""])
    opening_hooks = assets.get("opening_hooks", [""])
    practical_values = assets.get("practical_values", [])

    prompt = f"""你是一位专注于 AI 领域的小红书博主，擅长将复杂的学术论文转化为易读、有价值的科普内容。

请根据以下内容素材，生成一篇完整的小红书帖子。

【论文基本信息】
标题：{understanding.get('paper_title', '')}
一句话总结：{understanding.get('one_sentence_summary', '')}
方法名称：{understanding.get('method_name', '')}

【内容素材】
推荐标题（从中选一个或改写）：
{json.dumps(title_hooks[:3], ensure_ascii=False, indent=2)}

开头钩子：
{json.dumps(opening_hooks, ensure_ascii=False, indent=2)}

核心要点：
{json.dumps(core_points, ensure_ascii=False, indent=2)}

实验结果：
{json.dumps(experiment_results, ensure_ascii=False, indent=2)}

论文亮点：
{json.dumps(highlights, ensure_ascii=False, indent=2)}

实际价值：
{json.dumps(practical_values, ensure_ascii=False, indent=2)}

推荐标签：
{json.dumps(audience_tags, ensure_ascii=False, indent=2)}

推荐封面文字：
{json.dumps(cover_text_candidates[:3], ensure_ascii=False, indent=2)}

【写作要求】
1. 标题：吸引眼球，包含核心价值，≤30字
2. 正文结构：
   - 开头：1-2句话抓住读者（用开头钩子改写）
   - 论文介绍：简要介绍这篇论文是什么、解决什么问题（2-3句）
   - 核心亮点：3-5个要点，每点用 emoji 开头，简洁有力
   - 实验结果：1-3个关键数据，要具体
   - 实际价值：这对读者有什么用（1-2句）
   - 结尾：引导互动（如"你觉得这个方法有什么应用场景？"）
3. 风格：口语化、易读、不过度学术化，但保持准确性
4. 长度：正文 300-600 字
5. 标签：8-12个，放在正文末尾
6. 封面文字：从候选中选一个最合适的

请用 JSON 格式输出：
{{
  "title": "帖子标题",
  "body": "帖子正文（包含 emoji 和换行，标签放在最后）",
  "hashtags": ["#标签1", "#标签2"],
  "cover_text": "封面文字",
  "paper_title_zh": "论文标题（如果是英文，提供中文翻译）"
}}

注意：
- body 字段中标签直接写在正文末尾，不要单独放在 hashtags 里重复
- hashtags 字段保留供程序使用，可以和 body 末尾的标签相同
- 只输出 JSON，不要其他内容"""

    response = _call_claude(client, prompt, max_tokens=3000)
    try:
        return _extract_json(response)
    except Exception as e:
        logger.error(f"小红书帖子生成解析失败: {e}\n原始响应: {response[:500]}")
        return {}


def _save_markdown(post: dict, output_path: Path) -> None:
    title = post.get("title", "")
    body = post.get("body", "")
    lines = [
        f"# {title}",
        "",
        "![封面](cover.png)",
        "",
        body,
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _validate(post: dict) -> dict:
    body = post.get("body", "")
    checks = {
        "title_exists": bool(post.get("title")),
        "body_exists": bool(body),
        "body_length_ok": 100 <= len(body) <= 2000,
        "has_hashtags": len(post.get("hashtags", [])) > 0,
        "cover_text_exists": bool(post.get("cover_text")),
    }
    return checks


def run(task_id: str, workspace: dict) -> dict:
    """
    执行 Stage 5：小红书内容生成

    输入：
      - workspace["understanding"]/paper_understanding.json
      - workspace["assets"]/content_assets.json
    输出：workspace["xhs"]/xhs_post.json
    """
    print_stage_header(5, "小红书内容生成")

    understanding_path = workspace["understanding"] / "paper_understanding.json"
    assets_path = workspace["assets"] / "content_assets.json"
    xhs_dir = workspace["xhs"]

    for p in [understanding_path, assets_path]:
        if not p.exists():
            print_error(f"输入文件不存在: {p}")
            return {"status": "failed", "error": f"{p.name} 不存在"}

    try:
        understanding = load_json(understanding_path)
        assets = load_json(assets_path)
    except Exception as e:
        print_error(f"加载输入文件失败: {e}")
        return {"status": "failed", "error": str(e)}

    try:
        client = _get_client()
    except ValueError as e:
        print_error(str(e))
        return {"status": "failed", "error": str(e)}

    print_info("生成小红书帖子...")
    post = generate_xhs_post(client, understanding, assets)

    if not post:
        print_error("帖子生成失败（空响应）")
        return {"status": "failed", "error": "帖子生成失败"}

    # 验证
    checks = _validate(post)
    failed = [k for k, v in checks.items() if not v]
    if failed:
        print_warning(f"验证警告: {failed}")

    if not checks["title_exists"] or not checks["body_exists"]:
        print_error("帖子核心内容（标题/正文）为空")
        return {"status": "failed", "error": "帖子核心内容为空", "validation": checks}

    # 保存
    save_json(post, xhs_dir / "xhs_post.json")
    _save_markdown(post, xhs_dir / "xhs_post.md")

    print_success(f"标题: {post.get('title', '')}")
    print_success(f"正文长度: {len(post.get('body', ''))} 字")
    print_success(f"标签数量: {len(post.get('hashtags', []))}")
    print_info(f"\n{'─'*50}")
    print_info("【帖子预览】")
    print_info(f"标题：{post.get('title', '')}")
    print_info(f"\n{post.get('body', '')[:300]}...")
    print_info(f"{'─'*50}\n")

    result = {
        "status": "success",
        "post_path": str(xhs_dir / "xhs_post.json"),
        "validation": checks,
        "preview": {
            "title": post.get("title", ""),
            "body_preview": post.get("body", "")[:200],
            "cover_text": post.get("cover_text", ""),
        },
    }
    save_stage_result(result, "stage5_xhs", workspace)
    return result
