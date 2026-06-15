"""
paper_quiz.py — PaperQuiz evaluator for rendered posters.

Inspired by PosterAgent (arXiv:2505.21497), this module measures how well a
poster *communicates* the paper, not just how it looks.

Pipeline:
  1. Read `digest.json` (asset library) and pick a few load-bearing facts:
     problem, key contribution, method idea, headline result, takeaway.
  2. Use the text LLM (qwen-plus) to write 5-10 multiple-choice questions
     covering those facts, each with one correct answer and 3 plausible
     distractors derived from neighbouring sections.
  3. Use the VLM (qwen3-vl-plus) to answer those questions from the rendered
     poster image alone.
  4. Score correctness, surface which sections were mis-answered, and emit
     structured `suggested_repair_actions` (e.g. emphasize the result section
     when the result question is wrong).

Output JSON:
  {
    "quiz_score": 80,
    "n_questions": 5,
    "questions": [...],
    "answers": [...],
    "correctness": [...],
    "by_role": {"problem": 1.0, "method": 0.5, "result": 1.0, "takeaway": 0.0},
    "suggested_repair_actions": [
      {"type": "emphasize_section", "target": "takeaway"}
    ]
  }
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys

from translate_outline import _make_client
from translate_outline import MODEL as TEXT_MODEL


VLM_MODEL = os.environ.get("VLM_MODEL", "qwen3-vl-plus")

# Hard cap so a long paper does not blow the LLM context.
DIGEST_SECTION_CHAR_LIMIT = 1200
DIGEST_MAX_SECTIONS = 12

QUESTION_AUTHOR_PROMPT = """You write reading-comprehension multiple-choice
questions to test whether a research poster faithfully transmits its paper.

Constraints:
- Exactly 5 to 8 questions, each with 4 options labeled A/B/C/D and one
  correct answer.
- Cover these poster roles, in order: problem, method, result, takeaway,
  and at most one extra (contribution or limitation).
- Each question MUST be answerable from a well-designed poster — don't ask
  about minor numerical details that even the paper buries in an appendix.
- Distractors must be plausible: pull them from sibling sections of the same
  paper, not random nonsense. Wrong options should *sound* like they could
  belong to the paper.
- Keep stems under 25 words. Keep options under 12 words.
- Output language matches the poster language hint provided.

Return ONLY JSON:
{
  "questions": [
    {
      "id": "q1",
      "role": "problem",
      "source_section": "Introduction",
      "stem": "...",
      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
      "answer": "B",
      "rationale": "one short sentence citing the section"
    }
  ]
}"""


VLM_ANSWER_PROMPT = """You are taking a multiple-choice quiz about a research
poster. You can ONLY use what is visible in the poster image — do not rely on
prior knowledge, do not guess from the paper title alone.

For each question, return the single best option letter A/B/C/D, and a short
note (under 20 words) describing where on the poster you found the evidence
(e.g. "top-right metrics card" or "method figure caption"). If the poster does
not contain the answer, return "?" and say so plainly.

Return ONLY JSON:
{
  "answers": [
    {"id": "q1", "choice": "B", "evidence": "headline metric card"},
    {"id": "q2", "choice": "?", "evidence": "not shown on the poster"}
  ]
}"""


def _short(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit]


def _digest_payload_for_quiz(digest):
    """Trim a digest into a question-author payload."""
    metadata = digest.get("metadata", {}) or {}
    sections = []
    for sec in (digest.get("sections") or [])[:DIGEST_MAX_SECTIONS]:
        heading = sec.get("heading") or ""
        if not heading or heading.startswith("_"):
            continue
        sections.append({
            "heading": heading,
            "text": _short(sec.get("text"), DIGEST_SECTION_CHAR_LIMIT),
            "lists": [_short(b, 200) for b in (sec.get("lists") or [])[:6]],
        })
    figures = []
    for fig in (digest.get("figures") or [])[:8]:
        figures.append({
            "id": fig.get("id"),
            "caption": _short(fig.get("caption"), 240),
            "section": fig.get("section"),
        })
    tables = []
    for tab in (digest.get("tables") or [])[:6]:
        tables.append({
            "id": tab.get("id"),
            "caption": _short(tab.get("caption"), 240),
            "section": tab.get("section"),
        })
    assets = []
    for asset in (digest.get("assets") or [])[:24]:
        assets.append({
            "id": asset.get("id"),
            "type": asset.get("type"),
            "role": asset.get("role"),
            "priority": asset.get("priority"),
            "text": _short(asset.get("text"), 240),
            "source_section": asset.get("source_section"),
        })
    return {
        "title": metadata.get("title", ""),
        "abstract": _short(metadata.get("abstract"), 1500),
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "assets": assets,
    }


def _image_data_url(image_path):
    mime = mimetypes.guess_type(image_path)[0] or "image/png"
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _safe_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def author_questions(digest, language="en", api_key=None, n_target=6):
    """Use the text LLM to write a multiple-choice quiz from the digest."""
    payload = _digest_payload_for_quiz(digest)
    payload["target_question_count"] = n_target
    payload["output_language"] = (
        "Simplified Chinese (中文)" if language == "zh" else "English"
    )
    client = _make_client(api_key=api_key)
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        max_tokens=2400,
        messages=[
            {"role": "system", "content": QUESTION_AUTHOR_PROMPT},
            {
                "role": "user",
                "content": (
                    "Write the quiz from this paper digest. Return only JSON.\n\n"
                    f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    text = (resp.choices[0].message.content or "{}").strip()
    data = _safe_json(text)
    questions = []
    for q in (data.get("questions") or [])[:10]:
        opts = q.get("options") or {}
        if not all(k in opts for k in ("A", "B", "C", "D")):
            continue
        ans = str(q.get("answer", "")).strip().upper()[:1]
        if ans not in ("A", "B", "C", "D"):
            continue
        questions.append({
            "id": str(q.get("id") or f"q{len(questions) + 1}"),
            "role": str(q.get("role") or "").lower().strip() or "general",
            "source_section": q.get("source_section"),
            "stem": str(q.get("stem") or "").strip(),
            "options": {k: str(opts.get(k, "")).strip() for k in ("A", "B", "C", "D")},
            "answer": ans,
            "rationale": str(q.get("rationale") or "").strip(),
        })
    return questions


def answer_questions_from_poster(png_path, questions, api_key=None):
    """Show the poster image to the VLM and ask it to answer each question."""
    if not questions:
        return []
    if not png_path or not os.path.isfile(png_path):
        return [
            {"id": q["id"], "choice": "?", "evidence": "no poster image available"}
            for q in questions
        ]
    visible = [
        {
            "id": q["id"],
            "stem": q["stem"],
            "options": q["options"],
        }
        for q in questions
    ]
    client = _make_client(api_key=api_key)
    resp = client.chat.completions.create(
        model=VLM_MODEL,
        max_tokens=900,
        messages=[
            {"role": "system", "content": VLM_ANSWER_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": _image_data_url(png_path)}},
                    {
                        "type": "text",
                        "text": (
                            "Answer each question using only the poster image. "
                            "Return one entry per question id.\n\n"
                            f"```json\n{json.dumps(visible, ensure_ascii=False, indent=2)}\n```"
                        ),
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
    )
    text = (resp.choices[0].message.content or "{}").strip()
    data = _safe_json(text)
    by_id = {}
    for a in (data.get("answers") or []):
        qid = str(a.get("id") or "").strip()
        if not qid:
            continue
        choice = str(a.get("choice", "?")).strip().upper()[:1]
        if choice not in ("A", "B", "C", "D"):
            choice = "?"
        by_id[qid] = {
            "id": qid,
            "choice": choice,
            "evidence": _short(a.get("evidence"), 220),
        }
    return [
        by_id.get(q["id"], {"id": q["id"], "choice": "?", "evidence": "no answer"})
        for q in questions
    ]


_REPAIR_BY_ROLE = {
    "problem":      [{"type": "emphasize_section", "target": "problem"},
                     {"type": "fix_reading_order", "target": "all"}],
    "motivation":   [{"type": "emphasize_section", "target": "problem"}],
    "method":       [{"type": "increase_figure_area", "target": "method", "factor": 1.2},
                     {"type": "emphasize_section", "target": "method"}],
    "approach":     [{"type": "increase_figure_area", "target": "method", "factor": 1.2}],
    "result":       [{"type": "increase_hero_visual", "target": "results", "factor": 1.25},
                     {"type": "convert_results_table_to_metrics", "target": "results"}],
    "results":      [{"type": "increase_hero_visual", "target": "results", "factor": 1.25},
                     {"type": "convert_results_table_to_metrics", "target": "results"}],
    "takeaway":     [{"type": "emphasize_section", "target": "takeaway"},
                     {"type": "compact_sidebars", "target": "support"}],
    "conclusion":   [{"type": "emphasize_section", "target": "takeaway"}],
    "contribution": [{"type": "emphasize_section", "target": "contribution"}],
    "limitation":   [{"type": "tighten_side_text", "target": "support", "max": 2}],
}


def _suggest_repair_actions(by_role):
    """Translate role-level miss rates into structured repair actions."""
    suggestions = []
    seen = set()
    # Role with lowest correctness drives the strongest action first.
    ranked = sorted(by_role.items(), key=lambda kv: (kv[1]["correct"] / max(kv[1]["asked"], 1)))
    for role, stat in ranked:
        if stat["asked"] == 0:
            continue
        miss_rate = 1 - stat["correct"] / stat["asked"]
        if miss_rate < 0.5:
            continue
        for action in _REPAIR_BY_ROLE.get(role, []):
            key = (action.get("type"), action.get("target"))
            if key in seen:
                continue
            seen.add(key)
            entry = dict(action)
            entry["confidence"] = round(min(0.95, 0.5 + miss_rate / 2), 2)
            entry["source"] = "paper_quiz"
            entry["miss_role"] = role
            suggestions.append(entry)
    return suggestions


def evaluate(digest, png_path, language="en", api_key=None, n_target=6):
    """Run author -> answer -> score and return the full evaluation dict."""
    questions = author_questions(digest, language=language, api_key=api_key,
                                 n_target=n_target)
    answers = answer_questions_from_poster(png_path, questions, api_key=api_key)
    correctness = []
    by_role = {}
    for q, a in zip(questions, answers):
        role = q.get("role") or "general"
        slot = by_role.setdefault(role, {"asked": 0, "correct": 0})
        slot["asked"] += 1
        is_correct = a.get("choice") == q.get("answer")
        if is_correct:
            slot["correct"] += 1
        correctness.append({
            "id": q["id"],
            "role": role,
            "expected": q.get("answer"),
            "got": a.get("choice"),
            "correct": bool(is_correct),
            "evidence": a.get("evidence"),
        })
    n = len(questions)
    n_correct = sum(1 for c in correctness if c["correct"])
    quiz_score = int(round(100 * n_correct / n)) if n else 0
    by_role_ratio = {
        role: round(stat["correct"] / max(stat["asked"], 1), 2)
        for role, stat in by_role.items()
    }
    return {
        "quiz_score": quiz_score,
        "n_questions": n,
        "n_correct": n_correct,
        "questions": questions,
        "answers": answers,
        "correctness": correctness,
        "by_role": by_role_ratio,
        "by_role_raw": by_role,
        "suggested_repair_actions": _suggest_repair_actions(by_role),
        "vlm_model": VLM_MODEL,
        "text_model": TEXT_MODEL,
    }


def main():
    ap = argparse.ArgumentParser(description="PaperQuiz evaluator for a rendered poster")
    ap.add_argument("--digest", required=True, help="Path to digest.json")
    ap.add_argument("--poster-png", required=True, help="Path to rendered poster PNG")
    ap.add_argument("--output", required=True, help="Where to write the quiz JSON")
    ap.add_argument("--language", default="en", choices=["en", "zh"],
                    help="Poster language (controls question wording)")
    ap.add_argument("--n", type=int, default=6, help="Target number of questions (5-10)")
    ap.add_argument("--api-key", default=None, help="DashScope key override")
    args = ap.parse_args()

    with open(args.digest, "r", encoding="utf-8") as f:
        digest = json.load(f)

    result = evaluate(
        digest, args.poster_png, language=args.language,
        api_key=args.api_key, n_target=max(5, min(10, args.n)),
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"PaperQuiz result -> {args.output}")
    print(f"  questions: {result['n_questions']}")
    print(f"  correct  : {result['n_correct']}")
    print(f"  score    : {result['quiz_score']}/100")
    if result["by_role"]:
        print("  by role  :")
        for role, ratio in result["by_role"].items():
            print(f"    {role:>14s}: {ratio:.2f}")
    if result["suggested_repair_actions"]:
        print("  suggested repair actions:")
        for action in result["suggested_repair_actions"]:
            print(f"    - {action.get('type')} -> {action.get('target')} "
                  f"(role={action.get('miss_role')})")


if __name__ == "__main__":
    sys.exit(main() or 0)
