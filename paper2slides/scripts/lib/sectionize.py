"""
lib/sectionize.py — section keyword table (shared library)

Keyword table and kind mapping for recognizing paper section titles, reused by
`mineru_parser._classify_kind` — uses `NUMBERING` / `NUMBERED_KEYWORDS` /
`TOP_LEVEL_KEYWORDS` to classify the section titles parsed out by MinerU into a unified
kind. A pure data module, with no executable entry point.

Recognition falls into two categories:
1) TOP_LEVEL_KEYWORDS — recognized without numbering (these titles are unlikely to occupy a line on their own in the body text)
2) NUMBERED_KEYWORDS  — only match when paired with a numbering prefix ("3 Method" / "3.1 Encoder ...")
"""
from __future__ import annotations

TOP_LEVEL_KEYWORDS: list[tuple[str, str]] = [
    (r"abstract",                                          "abstract"),
    (r"references?|bibliography",                          "references"),
    (r"acknowledg(?:e?ments?)",                            "other"),
    (r"appendix(?:\s+\w+)?|supplement(?:ary)?(?:\s+material)?", "other"),
]

# Whitespace within keywords uses \s* rather than \s+: word spacing in parsed titles may be lost or extra
# (e.g. "Model Architecture" → "ModelArchitecture"), and \s* tolerates both.
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

# numbering prefix: 1 / 1. / 1.2 / 1.2. / I. / A. (the three forms common in papers)
NUMBERING = r"(?:\d+(?:\.\d+)*\.?|[IVXLCDM]+\.|[A-Z]\.)"
