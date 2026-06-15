"""VLM scoring for rendered poster PNGs.

Standalone replacement for ``app.py:_score_poster_visual``. Uses DashScope's
Qwen3-VL-Plus directly (no Packy / GPT fallback) so it works from the CLI
without the Gradio stack. The output JSON shape is unchanged: callers can drop
this in wherever ``_score_poster_visual`` used to be imported.

Public API:
    score_one(png_path, outline, candidate_name, *, layout=None, api_key=None) -> dict
    score_many(candidates, *, api_key=None) -> list[dict]

CLI:
    python scripts/score_poster_visual.py \
        --png   path/to/poster.png \
        --outline path/to/outline.json \
        --candidate three_zone_empirical_ml \
        [--layout path/to/layout.json] \
        --output path/to/visual_score.json
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from translate_outline import _make_client


VLM_MODEL = os.environ.get("VLM_MODEL", "qwen3-vl-plus")


QUALITY_JUDGE_PROMPT = """You are a strict academic poster design judge.

Score the rendered poster image from 0 to 100. A good poster has a clear first
impression, readable text, readable figures, balanced whitespace, strong visual
hierarchy, a human-friendly reading order, and an obvious research takeaway.
Penalize tiny figures, sparse empty panels, wall-of-text sections,
clipping/overlap, weak headline hierarchy, generic template-like composition,
and chaotic visual flow.
Do not over-reward tidy dashboard or slide-deck compositions: a grid of metric
cards and text blocks is not enough if it lacks a conference-poster visual
anchor. Reward layouts that look like a real research poster with one or two
dominant figures, a clear claim, and supporting evidence around them.
Also penalize posters that are too sparse. Top-conference posters are often
dense but anchored: they should have enough figures, captions, evidence, and
supporting claims for close reading after the first glance.

Treat poster-viewing-distance legibility as a first-class judgment criterion.
A real conference poster is read from roughly 1-2 meters away: section
headers, body bullets, figure labels, and table cells must all be large
enough to be comfortably readable at that distance. If body text or figure
labels look cramped, web-page-sized, or shrunken to fit into a panel, that
is a serious design failure - not a minor polish issue. Use your own
judgment on how much to penalize, but do not let strong content compensate
for text the viewer cannot read. Call out specifically which elements are
too small (e.g. "method diagram axis labels", "results table cell text",
"bullet body text in analysis panel") in `top_issues` so the repair pass
can target them.

Your critique must be operational, not just aesthetic. When you mention
whitespace or weak density, identify where it is inside the affected module:
top, bottom, left, right, around_image, or between_blocks. Check whether a
paper figure is being crudely cropped or stretched; if so, ask to keep the full
figure visible or to create an explicitly labeled detail crop. If a section has
tiny explanatory text next to a major figure, suggest a module-local font-size
change instead of global scaling. If descriptions are spread across three small
parallel cards and leave holes, suggest converting them into a single vertical
bullet stack with larger type. If a figure leaves letterbox whitespace, suggest
filling the space with paper-grounded explanation bullets above/below/beside
the figure.

Treat reading order as a first-class criterion. A poster should guide the eye
roughly as: title -> intro/problem/what-the-paper-is-about -> dominant central
visual -> evidence/results -> takeaway. Penalize layouts that start the visual
path with a raw number, force zig-zag reading, make similarly sized panels
compete, place conclusions before evidence, or bury the main result after
support text.

Apply this template-derived rubric explicitly:
- Title separation: the top band must be the paper title, not a metric or claim.
- Hero claim quality: the hero claim must be a complete sentence; raw numbers
  belong in evidence panels or metric cards, not as the first visual anchor.
- Visual reservation: the main figure/evidence region must be large enough to
  read, not a corner thumbnail.
- Section indexing: section headers should be short and consistent.
- Hierarchy: one primary evidence region should dominate over support panels.

First, identify SEVERE issues. A severe issue is any one of:
  - text or figure labels not comfortably readable at 1-2 m (tiny table cells,
    cramped diagram node labels, body text shrunk to fit);
  - an empty / near-empty / under-filled panel (a figure with sparse text that
    leaves large blank space);
  - a hero/main figure too small to read (thumbnail-sized, well under ~25% of
    the poster area);
  - overlapping, clipped, or cut-off elements;
  - a raw number or fragment used as the top visual anchor instead of a claim.

List EVERY severe issue you see in `top_issues`, and report how many in
`n_severe_issues`.

Then assign the score using these MANDATORY bands. Find your FIRST-impression
band, then adjust by at most +/-5 within it.

  85-100  Conference-ready. Dominant readable hero (>=25% area), complete-
          sentence headline claim, <=2 support panels per zone, no empty panel,
          all text readable at 1-2 m.
  70-84   Solid: clear hierarchy and reading order, and NO severe issues — at
          most minor polish (slightly loose spacing, a marginally small caption).
  50-69   Structural problems: no dominant visual, OR zig-zag reading order, OR
          panels competing at equal size, OR a wall-of-text panel.
  30-49   Broken: overlapping/clipped elements, a raw number as the top anchor,
          or several empty/sparse regions.
  0-29    Not a poster: no visual anchor, pervasive empty space, unreadable text.

HARD CAP: if there is ONE OR MORE severe issues, the score MUST be at most 69
(it cannot land in the 70-84 or 85-100 bands) no matter how good the rest is. A
poster a viewer cannot fully read, or that has dead space, is not "solid".
Strong content never compensates for a severe issue.

Score the IMAGE ONLY. You are given no section list — do not assume any content
is present that you cannot see in the pixels.

For `repair_actions`, emit ONLY these supported operation types (any other type
is ignored downstream):
  fix_reading_order, fix_title_claim_separation, rewrite_hero_as_sentence,
  increase_hero_visual, increase_figure_area, convert_results_table_to_metrics,
  emphasize_section, tighten_side_text, move_section, hide_section,
  compact_headline, set_headline_height.
Map what you see onto these: small/cramped hero -> increase_hero_visual or
increase_figure_area; tiny table text -> convert_results_table_to_metrics;
under-filled/empty panel -> tighten_side_text or hide_section; missing claim ->
rewrite_hero_as_sentence; descriptive title where the claim belongs ->
fix_title_claim_separation.

Return ONLY JSON:
{
  "score": 0,
  "n_severe_issues": 0,
  "verdict": "...",
  "top_issues": ["..."],
  "reading_order": {
    "score": 0,
    "verdict": "...",
    "breakpoints": ["where the eye gets lost"]
  },
  "best_for": "...",
  "repair_actions": [
    {"type": "increase_hero_visual", "target": "results", "factor": 1.3},
    {"type": "convert_results_table_to_metrics", "target": "results"},
    {"type": "rewrite_hero_as_sentence", "target": "headline"},
    {"type": "tighten_side_text", "target": "support", "max": 2}
  ]
}"""


def _image_data_url(image_path: str | Path) -> str:
    """Encode a local image as a data URL for OpenAI-compatible vision input."""
    path = str(image_path)
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _build_payload(outline: dict, candidate_name: str,
                   layout: dict | None = None) -> dict:
    """Minimal context for the judge.

    Deliberately withholds the section/figure structure of the poster: telling
    the VLM what *should* be present biases it toward confirming that content
    exists in the image (score inflation). The judge sees the pixels and only
    the candidate label + paper title for caption sanity.
    """
    return {
        "candidate": candidate_name,
        "title": outline.get("title", ""),
        "judge_focus": [
            "judge the rendered IMAGE ONLY; you are given no section list",
            "score against the mandatory bands in the system prompt",
            "penalize duplicate figures, unreadable thumbnails, and empty panels",
        ],
    }


def score_one(png_path: str | Path,
              outline: dict,
              candidate_name: str,
              *,
              layout: dict | None = None,
              api_key: str | None = None) -> dict:
    """Score a single rendered poster PNG with Qwen3-VL."""
    if not png_path or not Path(png_path).is_file():
        return {
            "candidate": candidate_name,
            "score": 0,
            "verdict": "No rendered PNG was available for visual scoring.",
            "top_issues": ["Preview export failed or was skipped."],
            "png_path": str(png_path) if png_path else None,
            "scoring_provider": None,
        }

    payload = _build_payload(outline, candidate_name, layout)
    try:
        client = _make_client(api_key=api_key)
        resp = client.chat.completions.create(
            model=VLM_MODEL,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": QUALITY_JUDGE_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": _image_data_url(png_path)}},
                        {
                            "type": "text",
                            "text": (
                                "Score this rendered poster against the mandatory "
                                "bands. Judge the image only.\n\n"
                                f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
                            ),
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
        text = (resp.choices[0].message.content or "{}").strip()
    except Exception as exc:
        return {
            "candidate": candidate_name,
            "score": 0,
            "verdict": f"VLM scoring failed: {exc}",
            "top_issues": [f"VLM exception: {exc}"],
            "png_path": str(png_path),
            "scoring_provider": f"dashscope:{VLM_MODEL}",
            "scoring_error": str(exc),
        }

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        import re
        score_match = re.search(r'"score"\s*:\s*(\d+)', text)
        verdict_match = re.search(r'"verdict"\s*:\s*"([^"]+)"', text)
        result = {
            "score": int(score_match.group(1)) if score_match else 0,
            "verdict": verdict_match.group(1) if verdict_match else text[:300],
            "top_issues": [],
            "parse_warning": "VLM response was not valid JSON; "
                             "score salvaged via regex.",
        }
    try:
        result["score"] = int(float(result.get("score", 0)))
    except Exception:
        result["score"] = 0

    # Deterministic severe-issue cap: the prompt asks the VLM to keep any poster
    # with a severe issue out of the 70+ bands, but enforce it in code so a
    # non-compliant judge can't let an unreadable / dead-space poster pass.
    # Severity comes from the VLM's own n_severe_issues, with a keyword fallback
    # over top_issues if that field is missing.
    SEVERE_CAP = 69
    try:
        n_severe = int(result.get("n_severe_issues") or 0)
    except Exception:
        n_severe = 0
    if not n_severe:
        _severe_kw = (
            "not readable", "unreadable", "illegible", "too small",
            "cramped", "tiny", "empty", "near-empty", "under-filled",
            "underfilled", "blank space", "dead space", "overlap",
            "clipped", "cut off", "cut-off", "thumbnail",
        )
        for _iss in (result.get("top_issues") or []):
            if any(k in str(_iss).lower() for k in _severe_kw):
                n_severe += 1
    result["n_severe_issues"] = n_severe
    if n_severe >= 1 and result["score"] > SEVERE_CAP:
        result["score_before_cap"] = result["score"]
        result["score"] = SEVERE_CAP
        result["severe_cap_applied"] = True

    result["candidate"] = candidate_name
    result["png_path"] = str(png_path)
    result["scoring_provider"] = f"dashscope:{VLM_MODEL}"
    return result


def score_many(candidates: list[dict],
               *,
               api_key: str | None = None) -> list[dict]:
    """Score a list of candidate posters.

    Each item in ``candidates`` must have ``png``, ``outline`` and ``name``
    keys; ``layout`` is optional. Returns a list of score dicts aligned with
    the input order.
    """
    results = []
    for cand in candidates:
        results.append(score_one(
            cand.get("png"),
            cand.get("outline") or {},
            cand.get("name") or cand.get("candidate") or "candidate",
            layout=cand.get("layout"),
            api_key=api_key,
        ))
    return results


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one poster PNG with Qwen3-VL.")
    parser.add_argument("--png", type=Path, required=True,
                        help="Path to the rendered poster PNG.")
    parser.add_argument("--outline", type=Path, required=True,
                        help="Outline JSON (used as metadata context).")
    parser.add_argument("--layout", type=Path, default=None,
                        help="Optional layout JSON for additional context.")
    parser.add_argument("--candidate", type=str, default="candidate",
                        help="Candidate name / archetype label.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Write the score JSON here; otherwise stdout.")
    args = parser.parse_args()

    outline = _load_json(args.outline)
    layout = _load_json(args.layout) if args.layout else None

    result = score_one(args.png, outline, args.candidate, layout=layout)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
