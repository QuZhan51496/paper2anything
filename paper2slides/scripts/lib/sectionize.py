"""
lib/sectionize.py — 章节关键词表（共享库）

论文章节标题的识别关键词表与 kind 映射，供 `mineru_parser._classify_kind` 复用——
用 `NUMBERING` / `NUMBERED_KEYWORDS` / `TOP_LEVEL_KEYWORDS` 把 MinerU 解析出的章节
标题分类成统一的 kind。纯数据模块，无可执行入口。

识别分两类：
1) TOP_LEVEL_KEYWORDS — 不需 numbering 也能识别（这些标题不易在正文里独占一行）
2) NUMBERED_KEYWORDS  — 必须配 numbering 前缀才匹配（"3 Method" / "3.1 Encoder ..."）
"""
from __future__ import annotations

TOP_LEVEL_KEYWORDS: list[tuple[str, str]] = [
    (r"abstract",                                          "abstract"),
    (r"references?|bibliography",                          "references"),
    (r"acknowledg(?:e?ments?)",                            "other"),
    (r"appendix(?:\s+\w+)?|supplement(?:ary)?(?:\s+material)?", "other"),
]

# 关键词内的空白用 \s* 而不是 \s+：解析出的标题里词间空格可能丢失或多余
# （如 "Model Architecture" → "ModelArchitecture"），\s* 两种都兼容。
NUMBERED_KEYWORDS: list[tuple[str, str]] = [
    (r"introduction",                                      "introduction"),
    (r"background(?:\s*and\s*motivation)?",                "background"),
    (r"preliminaries|notation",                            "background"),
    (r"related\s*work|prior\s*work",                       "related"),
    (r"method(?:s|ology)?|approach|"
     r"(?:model\s*)?architecture|proposed(?:\s*method)?|framework",
                                                           "method"),
    (r"why\s*self-?attention",                             "method"),
    (r"experiment(?:s|al\s*setup)?|evaluation|"
     r"implementation(?:\s*details?)?|training",           "experiment"),
    (r"results?|main\s*results?|findings",                 "result"),
    (r"analysis|ablation(?:\s*studies?|s)?",               "result"),
    (r"discussion|limitations?",                           "discussion"),
    (r"conclusion(?:s)?|summary|concluding\s*remarks",     "conclusion"),
]

# numbering 前缀：1 / 1. / 1.2 / 1.2. / I. / A.（论文常见三种）
NUMBERING = r"(?:\d+(?:\.\d+)*\.?|[IVXLCDM]+\.|[A-Z]\.)"
