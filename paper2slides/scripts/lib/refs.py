"""
lib/refs.py — 工具：剥离论文 References / Bibliography 内容

主要用法：sectionize.py 已把 references 标为一个 section。下游想"忽略 references"
时直接 strip_references(sections) 即可。

同时提供 strip_text_after_refs(text)，用于尚未切分但需要快速去掉参考文献块的场景
（如调试或 Stage 2 之前的临时文本预览）。
"""
from __future__ import annotations
import re

REFERENCES_HEAD_RE = re.compile(
    r"^[ \t]*(?:\d+\.?\s+)?(?:references?|bibliography)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_references(sections: list[dict]) -> list[dict]:
    return [s for s in sections if s.get("kind") != "references"]


def strip_text_after_refs(text: str) -> str:
    m = REFERENCES_HEAD_RE.search(text)
    return text[:m.start()] if m else text
