"""Select a small narrative set of original paper figures for poster use.

The goal is deliberately narrow: do not flood the poster with every extracted
image. Pick the figures that explain the poster in human reading order:
problem/context, method/main pipeline, and result/evidence. The selector uses
captions, section names, page position, and image geometry as transparent
heuristics so its choice can be inspected and improved.
"""
from __future__ import annotations

import _env  # noqa: F401  # 统一加载包根 .env（凭据）

import argparse
import json
import math
import os
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


METHOD_KEYWORDS = {
    "overview": 10,
    "framework": 10,
    "pipeline": 10,
    "architecture": 9,
    "workflow": 9,
    "infrastructure": 10,
    "system": 7,
    "model": 6,
    "method": 6,
    "training": 6,
    "multi-turn": 5,
    "reinforcement": 5,
    "rl": 5,
    "flywheel": 5,
    "annotation": 4,
    "sandbox": 4,
    "environment": 4,
    "rollout": 4,
}

PROBLEM_KEYWORDS = {
    "introduction": 8,
    "motivation": 8,
    "challenge": 8,
    "limitation": 7,
    "limitations": 7,
    "problem": 7,
    "task": 6,
    "tasks": 6,
    "conventional": 10,
    "existing": 8,
    "versus": 8,
    "vs": 6,
    "linear": 7,
    "ours": 6,
    "proposed": 5,
    "graph-structured": 8,
    "decision-making": 8,
    "branching": 7,
    "illustration": 4,
}

RESULT_KEYWORDS = {
    "result": 10,
    "results": 10,
    "benchmark": 9,
    "evaluation": 9,
    "performance": 8,
    "comparison": 8,
    "score": 7,
    "accuracy": 7,
    "ablation": 7,
    "scaling": 6,
    "dynamics": 5,
    "reward": 5,
    "variance": 4,
    "table": 4,
}

NOISE_KEYWORDS = {
    "appendix",
    "supplement",
    "reference",
    "acknowledg",
}


@dataclass
class Candidate:
    figure_id: str
    file: str
    path: str
    caption: str
    section: str
    page: int | None
    width: int
    height: int
    area: int
    aspect: float
    problem_score: float
    method_score: float
    result_score: float
    notes: list[str]
    reasons: dict[str, list[str]]


def norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def keyword_score(text: str, weights: dict[str, int]) -> float:
    score = 0.0
    for key, weight in weights.items():
        if key in text:
            score += weight
    return score


def keyword_hits(text: str, weights: dict[str, int], limit: int = 5) -> list[str]:
    hits = [(key, weight) for key, weight in weights.items() if key in text]
    hits.sort(key=lambda item: item[1], reverse=True)
    return [key for key, _ in hits[:limit]]


def geometry_score(width: int, height: int) -> tuple[float, list[str]]:
    area = width * height
    aspect = width / max(height, 1)
    notes: list[str] = []
    score = 0.0

    if area >= 700_000:
        score += 8
        notes.append("large image")
    elif area >= 250_000:
        score += 5
        notes.append("medium image")
    elif area >= 80_000:
        score += 2
        notes.append("small but usable")
    else:
        score -= 8
        notes.append("too small")

    if 1.0 <= aspect <= 3.6:
        score += 3
        notes.append("poster-friendly aspect")
    elif 3.6 < aspect <= 5.0:
        score += 1
        notes.append("very wide")
    else:
        score -= 3
        notes.append("awkward aspect")
    return score, notes


def resolve_figure_path(figures_dir: Path, image_path: str) -> Path | None:
    direct = figures_dir / image_path
    if direct.is_file():
        return direct
    name = Path(image_path).name
    direct = figures_dir / name
    if direct.is_file():
        return direct
    matches = list(figures_dir.glob(name))
    return matches[0] if matches else None


def build_candidates(digest: dict[str, Any], figures_dir: Path) -> list[Candidate]:
    out: list[Candidate] = []
    items: list[tuple[dict[str, Any], str]] = []
    for fig in digest.get("figures") or []:
        items.append((fig, "figure"))
    for tbl in digest.get("tables") or []:
        items.append((tbl, "table"))
    for fig, origin in items:
        path = resolve_figure_path(figures_dir, str(fig.get("image_path", "")))
        if not path:
            continue
        try:
            with Image.open(path) as image:
                width, height = image.size
        except Exception:
            continue
        text = norm(f"{fig.get('caption', '')} {fig.get('section', '')}")
        geo, notes = geometry_score(width, height)
        page = fig.get("page")
        section = norm(fig.get("section", ""))
        caption = norm(fig.get("caption", ""))
        if origin == "table":
            notes.append("table-origin")

        problem = geo + keyword_score(text, PROBLEM_KEYWORDS)
        method = geo + keyword_score(text, METHOD_KEYWORDS)
        result = geo + keyword_score(text, RESULT_KEYWORDS)

        reasons = {
            "problem_context": keyword_hits(text, PROBLEM_KEYWORDS),
            "method_main": keyword_hits(text, METHOD_KEYWORDS),
            "result_evidence": keyword_hits(text, RESULT_KEYWORDS),
        }

        if isinstance(page, int) and page <= 1:
            problem += 5
            reasons["problem_context"].append("early-page")
        if "introduction" in section:
            problem += 6
            reasons["problem_context"].append("introduction-section")
        if "figure 1" in caption:
            problem += 5
            reasons["problem_context"].append("figure-1")

        if re.search(r"\b2\.\d|\bmethod|\bconstruction|\bpipeline", section):
            method += 4
            reasons["method_main"].append("method-section")
        if "figure 2" in caption:
            method += 3
            reasons["method_main"].append("early-method-figure")

        if re.search(r"\b3\.\d|\bexperiment|\bresult|\bablation|evaluation|q\d", section):
            result += 5
            reasons["result_evidence"].append("experiment-section")
        if re.search(r"\bfigure [3-9]\b", caption):
            result += 2
            reasons["result_evidence"].append("later-result-figure")

        if any(k in text for k in NOISE_KEYWORDS):
            problem -= 10
            method -= 10
            result -= 10
            notes.append("noise section")
        if not norm(fig.get("caption", "")):
            problem -= 2
            method -= 2
            result -= 2
            notes.append("missing caption")
        out.append(
            Candidate(
                figure_id=str(fig.get("id", "")),
                file=path.name,
                path=str(path),
                caption=str(fig.get("caption", "")),
                section=str(fig.get("section", "")),
                page=fig.get("page"),
                width=width,
                height=height,
                area=width * height,
                aspect=width / max(height, 1),
                problem_score=round(problem, 2),
                method_score=round(method, 2),
                result_score=round(result, 2),
                notes=notes,
                reasons=reasons,
            )
        )
    return out


def select_figures(candidates: list[Candidate]) -> dict[str, Candidate | list[Candidate]]:
    usable = [c for c in candidates if c.area >= 70_000]
    problem_sorted = sorted(usable, key=lambda c: c.problem_score, reverse=True)
    problem = problem_sorted[0] if problem_sorted else None

    used = {problem.file} if problem else set()
    method_pool = [c for c in usable if c.file not in used]
    method_sorted = sorted(usable, key=lambda c: c.method_score, reverse=True)
    method_sorted = sorted(method_pool, key=lambda c: c.method_score, reverse=True)
    method = method_sorted[0] if method_sorted else None

    used = {c.file for c in (problem, method) if c}
    result_pool = [c for c in usable if c.file not in used]
    result_sorted = sorted(result_pool, key=lambda c: c.result_score, reverse=True)
    result = result_sorted[0] if result_sorted else None

    return {
        "problem_context": problem,
        "method_main": method,
        "result_evidence": result,
        "top_problem_candidates": problem_sorted[:5],
        "top_method_candidates": method_sorted[:5],
        "top_result_candidates": result_sorted[:5],
    }


# ---------------------------------------------------------------------------
# VLM-based figure selection (Qwen3-VL-Plus)
# ---------------------------------------------------------------------------

VLM_FIGURE_SELECT_PROMPT = """You are choosing the three anchor figures for an
academic conference poster. The poster needs exactly three role-aligned
figures:

  - problem_context: a figure that frames the task, the limitation of prior
    work, the input space, or a vivid task example. The reader should grasp
    "what is this paper about" from this figure alone.
  - method_main: the dominant pipeline / mechanism / architecture / algorithm
    figure. The figure that, if you saw only one image, you would say "this
    is how the method works".
  - result_evidence: the figure that most strongly demonstrates the paper's
    headline claim — comparison plots, qualitative grids, ablation curves,
    or a result table with numbers.

You will see one labeled candidate panel per figure. Each panel shows the
figure id, its caption, and the figure thumbnail. Choose ONE figure id per
role. Do NOT reuse the same figure across roles.

Rules:
- Prefer figures whose caption / section clearly matches the role.
- Prefer figures that are visually self-explanatory at thumbnail size.
- If two candidates tie, prefer the one whose caption is more concrete.
- If no usable candidate exists for a role, return null for that role and
  explain why in `reasoning`.

Return ONLY JSON of the form:
{
  "problem_context": "<figure_id or null>",
  "method_main":     "<figure_id or null>",
  "result_evidence": "<figure_id or null>",
  "reasoning": {
    "problem_context": "one short sentence",
    "method_main":     "one short sentence",
    "result_evidence": "one short sentence"
  }
}"""


def _build_vlm_pool(selection: dict[str, Any]) -> list[Candidate]:
    """Union the heuristic top-N per role into a unique candidate list."""
    seen: dict[str, Candidate] = {}
    order = []
    for role_key in ("top_problem_candidates", "top_method_candidates",
                     "top_result_candidates"):
        for cand in selection.get(role_key) or []:
            if cand.figure_id and cand.figure_id not in seen:
                seen[cand.figure_id] = cand
                order.append(cand.figure_id)
    return [seen[fid] for fid in order]


def _vlm_image_data_url(path: str | Path) -> str:
    import base64
    import mimetypes
    p = str(path)
    mime = mimetypes.guess_type(p)[0] or "image/png"
    with open(p, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{data}"


def vlm_pick_figures(
    pool: list[Candidate],
    *,
    api_key: str | None = None,
    paper_title: str = "",
) -> dict[str, Any]:
    """Ask Qwen3-VL to pick one anchor figure per role from a candidate pool.

    Returns ``{"picks": {role: figure_id_or_None}, "reasoning": {...},
    "model": "...", "error": optional}``.
    """
    from translate_outline import _make_client

    model = os.environ.get("VLM_MODEL", "qwen3-vl-plus")
    if not pool:
        return {"picks": {}, "reasoning": {}, "model": model,
                "error": "no usable candidates in heuristic pool"}

    user_parts: list[dict[str, Any]] = []
    user_parts.append({
        "type": "text",
        "text": (
            f"Paper title: {paper_title or '(unknown)'}\n\n"
            "Candidate figures (each block: id, then thumbnail):\n"
        ),
    })
    for cand in pool[:12]:
        caption = (cand.caption or "")[:280].replace("\n", " ")
        section = (cand.section or "").replace("\n", " ")[:80]
        user_parts.append({
            "type": "text",
            "text": (
                f"\n— figure_id: {cand.figure_id}\n"
                f"  section: {section or '(unknown)'}\n"
                f"  caption: {caption or '(no caption)'}\n"
                f"  size: {cand.width}x{cand.height}, page={cand.page}\n"
            ),
        })
        try:
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": _vlm_image_data_url(cand.path)},
            })
        except Exception as exc:
            user_parts.append({
                "type": "text",
                "text": f"  [could not load image: {exc}]\n",
            })

    user_parts.append({
        "type": "text",
        "text": (
            "\nPick exactly one figure_id per role from the candidates above. "
            "Return JSON only."
        ),
    })

    try:
        client = _make_client(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=600,
            messages=[
                {"role": "system", "content": VLM_FIGURE_SELECT_PROMPT},
                {"role": "user", "content": user_parts},
            ],
            response_format={"type": "json_object"},
        )
        text = (resp.choices[0].message.content or "{}").strip()
    except Exception as exc:
        return {"picks": {}, "reasoning": {}, "model": model, "error": str(exc)}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"picks": {}, "reasoning": {}, "model": model,
                "error": f"VLM did not return JSON: {exc}; raw={text[:200]}"}

    valid_ids = {c.figure_id for c in pool}
    picks: dict[str, str | None] = {}
    for role in ("problem_context", "method_main", "result_evidence"):
        choice = parsed.get(role)
        if isinstance(choice, str) and choice in valid_ids:
            picks[role] = choice
        else:
            picks[role] = None

    reasoning = parsed.get("reasoning")
    if not isinstance(reasoning, dict):
        reasoning = {}

    return {"picks": picks, "reasoning": reasoning, "model": model,
            "raw": parsed}


def apply_vlm_selection(
    selection: dict[str, Any],
    candidates: list[Candidate],
    vlm_result: dict[str, Any],
) -> dict[str, Any]:
    """Override heuristic anchors with VLM picks where available.

    Resolution order is method_main → result_evidence → problem_context, so the
    figure most coupled to a role (method) wins on conflict. If the VLM picks
    the same figure_id for two roles, only the higher-priority role keeps it;
    the loser falls back to the next-best heuristic pick *not already used*.
    If no fresh heuristic candidate exists for ``problem_context``, the role is
    set to ``None`` so the poster can render text-only for it instead of
    duplicating a figure.
    """
    by_id = {c.figure_id: c for c in candidates}
    picks = vlm_result.get("picks") or {}
    reasoning = vlm_result.get("reasoning") or {}
    used: set[str] = set()
    overrides: dict[str, dict[str, Any]] = {}

    role_priority = ("method_main", "result_evidence", "problem_context")
    rankings = {
        "problem_context": "top_problem_candidates",
        "method_main": "top_method_candidates",
        "result_evidence": "top_result_candidates",
    }

    for role in role_priority:
        previous = selection.get(role)
        chosen_id = picks.get(role)
        cand: Candidate | None = None
        reason: str = ""

        if chosen_id and chosen_id in by_id and by_id[chosen_id].file not in used:
            cand = by_id[chosen_id]
            reason = reasoning.get(role, "")
        else:
            if chosen_id and chosen_id in by_id and by_id[chosen_id].file in used:
                vlm_conflict_note = (
                    f"VLM picked '{chosen_id}' but it was already taken by a "
                    f"higher-priority role; falling back to next-best heuristic."
                )
            elif chosen_id:
                vlm_conflict_note = (
                    f"VLM picked '{chosen_id}' but it was unusable; falling "
                    f"back to heuristic."
                )
            else:
                vlm_conflict_note = (
                    "VLM did not return a valid pick; falling back to heuristic."
                )
            ranked: list[Candidate] = selection.get(rankings[role]) or []
            for c in ranked:
                if c.file not in used:
                    cand = c
                    break
            reason = vlm_conflict_note

        if cand is None and role == "problem_context":
            selection[role] = None
            overrides[role] = {
                "figure_id": None,
                "previous_heuristic": previous.figure_id if previous else None,
                "reason": (
                    f"{reason} No fresh candidate left after dedup; rendering "
                    f"problem_context text-only."
                ),
                "fallback": "text_only_problem",
            }
            continue

        if cand is None:
            selection[role] = previous
            if previous:
                used.add(previous.file)
            overrides[role] = {
                "figure_id": previous.figure_id if previous else None,
                "previous_heuristic": previous.figure_id if previous else None,
                "reason": reason or "no usable candidate.",
            }
            continue

        selection[role] = cand
        used.add(cand.file)
        overrides[role] = {
            "figure_id": cand.figure_id,
            "previous_heuristic": previous.figure_id if previous else None,
            "reason": reason,
        }
    return overrides



def draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, width: int, fill=(0, 0, 0)) -> None:
    x, y = xy
    for line in textwrap.wrap(text, width=width):
        draw.text((x, y), line, fill=fill)
        y += 15


def paste_fit(canvas: Image.Image, image_path: Path, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    with Image.open(image_path) as raw:
        image = raw.convert("RGB")
    image.thumbnail((w, h), Image.LANCZOS)
    px = x + (w - image.width) // 2
    py = y + (h - image.height) // 2
    canvas.paste(image, (px, py))


def make_selected_preview(selection: dict[str, Any], output: Path) -> None:
    problem: Candidate | None = selection.get("problem_context")
    method: Candidate | None = selection.get("method_main")
    result: Candidate | None = selection.get("result_evidence")
    canvas = Image.new("RGB", (1800, 900), "#eef6ec")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1800, 70), fill="#2f663f")
    draw.text((28, 22), "Selected original paper figures for poster", fill="white")

    panels = [
        ("1. Problem / context", problem, (35, 105, 540, 650), "problem_context"),
        ("2. Method / main figure", method, (630, 105, 540, 650), "method_main"),
        ("3. Result / evidence", result, (1225, 105, 540, 650), "result_evidence"),
    ]
    for title, cand, (x, y, w, h), role in panels:
        draw.rectangle((x, y, x + w, y + h), fill="white", outline="#6f9369", width=3)
        draw.rectangle((x, y, x + w, y + 42), fill="#33673f")
        draw.text((x + 14, y + 13), title, fill="white")
        if cand:
            paste_fit(canvas, Path(cand.path), (x + 18, y + 58, w - 36, 330))
            meta_y = y + 450
            draw.text((x + 18, meta_y), f"{cand.figure_id} | {cand.width}x{cand.height}", fill="#111")
            draw.text(
                (x + 18, meta_y + 22),
                f"problem={cand.problem_score} method={cand.method_score} result={cand.result_score}",
                fill="#111",
            )
            reason = ", ".join(cand.reasons.get(role, [])[:4])
            draw_wrapped(draw, (x + 18, meta_y + 48), f"why: {reason or 'geometry + role fit'}", 62, fill="#24432b")
            caption = cand.caption or f"Section: {cand.section}"
            draw_wrapped(draw, (x + 18, meta_y + 86), caption, 62, fill="#111")
        else:
            draw.text((x + 18, y + 80), "No candidate found", fill="#111")

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92)


def make_rank_sheet(selection: dict[str, Any], output: Path) -> None:
    top_problem: list[Candidate] = selection.get("top_problem_candidates") or []
    top_method: list[Candidate] = selection.get("top_method_candidates") or []
    top_result: list[Candidate] = selection.get("top_result_candidates") or []
    rows = [
        ("Top problem/context candidates", top_problem, "problem_context"),
        ("Top method candidates", top_method, "method_main"),
        ("Top result candidates", top_result, "result_evidence"),
    ]
    cell_w, cell_h = 300, 230
    canvas = Image.new("RGB", (cell_w * 5, cell_h * 3 + 70), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, 50), fill="#2f663f")
    draw.text((20, 17), "Figure selector ranking", fill="white")
    for row_idx, (row_title, candidates, role) in enumerate(rows):
        y0 = 60 + row_idx * cell_h
        draw.text((12, y0), row_title, fill="#111")
        for idx, cand in enumerate(candidates[:5]):
            x = idx * cell_w + 8
            y = y0 + 24
            draw.rectangle((x, y, x + cell_w - 16, y + cell_h - 34), outline="#6f9369", width=2)
            paste_fit(canvas, Path(cand.path), (x + 8, y + 8, cell_w - 32, 125))
            label = f"{idx + 1}. {cand.figure_id} {cand.width}x{cand.height}"
            draw.text((x + 8, y + 142), label, fill="#111")
            draw.text(
                (x + 8, y + 160),
                f"P {cand.problem_score} / M {cand.method_score} / R {cand.result_score}",
                fill="#111",
            )
            reason = ", ".join(cand.reasons.get(role, [])[:3])
            draw_wrapped(draw, (x + 8, y + 178), reason or cand.caption or cand.section, 36, fill="#111")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92)


def copy_selected(selection: dict[str, Any], output_dir: Path) -> dict[str, str | None]:
    copied: dict[str, str | None] = {}
    for key in ("problem_context", "method_main", "result_evidence"):
        cand: Candidate | None = selection.get(key)
        if not cand:
            copied[key] = None
            continue
        suffix = Path(cand.path).suffix.lower() or ".jpg"
        dest = output_dir / f"{key}_{cand.figure_id}{suffix}"
        shutil.copy2(cand.path, dest)
        copied[key] = str(dest)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Select original paper figures for a poster")
    parser.add_argument("--digest", type=Path, required=True)
    parser.add_argument("--figures-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--use-vlm",
        dest="use_vlm",
        action="store_true",
        default=None,
        help=("Use Qwen3-VL to pick the three anchor figures from the heuristic "
              "top-N pool. Default: ON. Disable with --no-vlm or set "
              "PAPER2POSTER_VLM_FIGURE_SELECT=0."),
    )
    parser.add_argument(
        "--no-vlm",
        dest="use_vlm",
        action="store_false",
        help="Disable VLM-based figure selection; use the heuristic top-1 only.",
    )
    parser.add_argument("--api-key", type=str, default=None,
                        help="DashScope API key override (otherwise read from env/config).")
    args = parser.parse_args()

    use_vlm = args.use_vlm
    if use_vlm is None:
        env_flag = os.environ.get("PAPER2POSTER_VLM_FIGURE_SELECT", "1").strip().lower()
        use_vlm = env_flag not in {"0", "false", "no", "off"}

    with args.digest.open("r", encoding="utf-8") as f:
        digest = json.load(f)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    candidates = build_candidates(digest, args.figures_dir)
    selection = select_figures(candidates)

    vlm_section: dict[str, Any] = {"enabled": bool(use_vlm)}
    if use_vlm:
        pool = _build_vlm_pool(selection)
        paper_title = (digest.get("metadata") or {}).get("title", "")
        vlm_result = vlm_pick_figures(pool, api_key=args.api_key,
                                      paper_title=paper_title)
        if vlm_result.get("error"):
            vlm_section.update({
                "model": vlm_result.get("model"),
                "error": vlm_result["error"],
                "fallback": "heuristic top-1 retained for all roles",
                "pool_size": len(pool),
            })
            print(f"[select_poster_figures] VLM selection failed, falling back: "
                  f"{vlm_result['error']}", file=sys.stderr)
        else:
            overrides = apply_vlm_selection(selection, candidates, vlm_result)
            vlm_section.update({
                "model": vlm_result.get("model"),
                "pool_size": len(pool),
                "picks": vlm_result.get("picks", {}),
                "reasoning": vlm_result.get("reasoning", {}),
                "overrides": overrides,
            })

    copied = copy_selected(selection, args.output_dir)

    selected_preview = args.output_dir / "selected_figures_preview.jpg"
    rank_sheet = args.output_dir / "figure_selector_ranking.jpg"
    make_selected_preview(selection, selected_preview)
    make_rank_sheet(selection, rank_sheet)

    report = {
        "paper_title": digest.get("metadata", {}).get("title", ""),
        "selected": {
            "problem_context": asdict(selection["problem_context"]) if selection.get("problem_context") else None,
            "method_main": asdict(selection["method_main"]) if selection.get("method_main") else None,
            "result_evidence": asdict(selection["result_evidence"]) if selection.get("result_evidence") else None,
        },
        "copied_files": copied,
        "artifacts": {
            "selected_preview": str(selected_preview),
            "ranking_sheet": str(rank_sheet),
        },
        "top_method_candidates": [asdict(c) for c in selection.get("top_method_candidates", [])],
        "top_problem_candidates": [asdict(c) for c in selection.get("top_problem_candidates", [])],
        "top_result_candidates": [asdict(c) for c in selection.get("top_result_candidates", [])],
        "vlm_selection": vlm_section,
    }
    report_path = args.output_dir / "selected_figures.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["artifacts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
