"""
translate_outline.py — Translate a poster outline to a target language via
the DashScope (Aliyun Qwen) OpenAI-compatible API.

Used by the Gradio app so the "Poster language" dropdown actually changes
the rendered content. Translates:
  - title
  - sections[].title
  - sections[].content[]   (preserves leading **Bold lead**: markup)
  - headline.label, headline.context  (stat is left untouched — it's a number)

The source paper text is loaded into a single chat call which returns a
JSON object mapping each input string to its translation. We do not
translate file paths, color hex codes, column names, etc.

Auth (in priority order):
  - api_key argument
  - DASHSCOPE_API_KEY env var
  - API_KEY env var (matches the user's existing shell export)

Base URL override: API_BASE_URL env var (defaults to DashScope's
compatible-mode endpoint).
"""
from __future__ import annotations

import _env  # noqa: F401  # 统一加载包根 .env（凭据）

import argparse
import json
import os
import re
import sys


MODEL = os.environ.get("POSTER_TEXT_MODEL", "qwen-plus")  # Cheap + capable for mechanical translation
MAX_TOKENS = 4096

LANG_NAMES = {
    "en": "English",
    "zh": "Simplified Chinese (中文)",
}


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _make_client(api_key: str | None = None):
    """Build an OpenAI-compatible client pointed at DashScope."""
    from openai import OpenAI
    key = (
        api_key
        or os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("API_KEY")
    )
    if not key:
        raise RuntimeError(
            "DashScope API key not set. Get a key from "
            "https://dashscope.console.aliyun.com/apiKey and either:\n"
            "  - export DASHSCOPE_API_KEY=sk-...\n"
            "  - export API_KEY=sk-...\n"
            "  - or paste it into the app's API key field."
        )
    base_url = os.environ.get("API_BASE_URL") or DEFAULT_BASE_URL
    return OpenAI(api_key=key, base_url=base_url)


def _collect_strings(outline: dict) -> list[str]:
    """Walk the outline and collect every translatable user-visible string."""
    out = []
    if outline.get("title"):
        out.append(outline["title"])
    for sec in outline.get("sections", []):
        if sec.get("title"):
            out.append(sec["title"])
        for bullet in sec.get("content", []):
            out.append(bullet)
    hl = outline.get("headline") or {}
    if hl.get("label"):
        out.append(hl["label"])
    if hl.get("context"):
        out.append(hl["context"])
    return out


def _apply_translations(outline: dict, mapping: dict) -> dict:
    """Return a new outline with each translatable string replaced."""
    def t(s):
        return mapping.get(s, s) if isinstance(s, str) else s

    new = dict(outline)
    new["title"] = t(outline.get("title", ""))
    new_sections = []
    for sec in outline.get("sections", []):
        new_sec = dict(sec)
        new_sec["title"] = t(sec.get("title", ""))
        new_sec["content"] = [t(b) for b in sec.get("content", [])]
        new_sections.append(new_sec)
    new["sections"] = new_sections

    hl = outline.get("headline")
    if hl:
        new_hl = dict(hl)
        if "label" in hl:
            new_hl["label"] = t(hl["label"])
        if "context" in hl:
            new_hl["context"] = t(hl["context"])
        new["headline"] = new_hl

    return new


SYSTEM_PROMPT = """You translate academic poster content for an audience of researchers.

Rules:
1. Translate each input string into the target language naturally and concisely. Posters are read at a glance — keep it tight.
2. Preserve any markdown bold markup like **lead phrase**: at the start of a bullet — translate the bolded phrase but keep the asterisks and the trailing colon.
3. Do NOT translate proper nouns (paper names, model names, benchmark names, citation keys).
4. Keep numbers, percentages, and units intact.
5. Output ONLY a JSON object mapping each input string verbatim to its translation. No markdown fences, no commentary."""


def translate_outline(outline: dict, target_lang: str = "zh",
                       api_key: str | None = None) -> dict:
    """Translate outline content to target_lang. Returns new outline dict."""
    if target_lang not in LANG_NAMES:
        raise ValueError(f"Unsupported language: {target_lang}")
    if target_lang == "en":
        return outline  # Already english (assumed)

    strings = _collect_strings(outline)
    # De-duplicate so the model only translates each unique string once
    unique = list(dict.fromkeys(strings))
    if not unique:
        return outline

    client = _make_client(api_key=api_key)

    user_payload = {
        "target_language": LANG_NAMES[target_lang],
        "strings": unique,
    }
    user_msg = (
        "Translate every string in `strings` to "
        f"{LANG_NAMES[target_lang]}. Return a JSON object mapping each "
        "original string (verbatim, including markup) to its translation.\n\n"
        f"```json\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}\n```"
    )

    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )

    text = (resp.choices[0].message.content or "").strip()

    # Defensive: strip ```json fences if the model ignored response_format
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    try:
        mapping = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Translator returned invalid JSON: {e}\n--- response ---\n{text[:500]}"
        )

    return _apply_translations(outline, mapping)


def main():
    ap = argparse.ArgumentParser(description="Translate a poster outline.json")
    ap.add_argument("--input", required=True, help="Source outline.json")
    ap.add_argument("--output", required=True, help="Translated outline path")
    ap.add_argument("--lang", default="zh", choices=list(LANG_NAMES.keys()))
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        outline = json.load(f)

    translated = translate_outline(outline, args.lang)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(translated, f, indent=2, ensure_ascii=False)

    n = len(_collect_strings(outline))
    print(f"Translated {n} strings → {args.output}")


if __name__ == "__main__":
    main()
