# Outline Heuristics

The mapping rules and decision criteria you (in Stage 2) use when turning `paper_meta.json` into
`slide_outline.json`. This file is not a mechanical substitution table — it is scaffolding for
"understanding the paper + making decisions".

## Overall goal

Cover the paper's **core narrative** (not a "section-by-section retelling"): **problem → method → evidence → conclusion**.
The slide count is **by default** decided by narrative completeness: each narrative node takes as many slides as it
needs; better one slide more so a single slide stays substantial and has room to breathe than to cram content into a
fixed page count. An academic talk is typically 12-20 minutes, and 1-2 minutes per slide can serve as a pacing
reference, but it is **not a metric to hit**.

### Deck-length tier (`config.json/deck_length_target`)

Stage 0.5 had the user choose a deck-length tier; before Stage 2 starts, first read `config.json/deck_length_target`:

- **`null` (the `auto` tier)**: as described in the previous paragraph — the slide count is decided purely by
  narrative + layout, with no upper/lower bound. Keep things as they are; the rest of this section's constraints do not apply.
- **Not `null` (`concise` `[8,12]` / `standard` `[13,18]` / `detailed` `[19,28]`)**: treat this
  range as a **soft target for outline granularity**, and pull toward the target band with two levers —
  1. **Whether to include optional roles**: the "no/optional" roles such as `background` / `discussion` / a second
     `result` slide (ablation) / `qna` — the detailed tier keeps more of them, the concise tier cuts more.
  2. **How many slides `method` / `result` split into**: the detailed tier splits a complex method into 3–4 slides,
     with each key innovation on its own slide; the concise tier merges into a 1–2 slide overview.

  This is a **soft** target: narrative completeness takes priority over landing inside the range. If you cannot land
  in it, hug the edge, and bear in mind that in the next step Stage 3 every slide still has to be filled with content.
  **Never** cut a **mandatory** core role
  (`title`/`introduction/motivation`/`method`/`experiment`/`result`/`conclusion`) to squeeze into the concise tier,
  and **never** dilute a single point into a half-empty slide to pad into the detailed tier — the deck-length tier
  only tunes "how finely the content is sliced", it does **not** change each slide's "space-driven, no whitespace
  no overflow" (see "Content-shaping rules" below and §0.4 of [design-style.md](design-style.md)).

## Roles → mandatory status and order

Each role takes as many slides as its content needs (a complex method can split into multiple slides, a simple paper
can merge); when a non-`auto` tier is chosen, whether the "no/optional" roles are included and the method/result
split granularity are adjusted toward the target band per the
[Deck-length tier](#deck-length-tier-configjsondeck_length_target) above. The table below only specifies which roles
are **mandatory** (no tier may cut them) and the typical order:

| Role | Mandatory? | Notes |
|---|:-:|---|
| `title` | Yes | First slide. Paper title, authors, (venue/year optional) |
| `tldr` | No | Right after title. The paper's "one-sentence summary + core contributions", so the audience grasps the key points in 30 seconds |
| `introduction` / `motivation` | Yes | What the current problem is, why it is hard, the shortcomings of prior methods (can split into multiple slides if there is a lot) |
| `background` | No | Add only when the paper has Related Work / Preliminaries and it is necessary for understanding the method. Adding it mindlessly == wasting time |
| `method` | Yes | The core. high-level overview + key innovations; split into multiple slides if the method is complex, do not cram it into one |
| `experiment` | Yes | Experimental setup: datasets, baseline, metric |
| `result` | Yes | Main results (mandatory) + ablation/analysis (optional, multiple slides as needed) |
| `discussion` | No | Add when the paper's Discussion / Limitations section has an important take-away |
| `conclusion` | Yes | Summarize contributions + future work |
| `qna` | No | Add only for large talks; usually omitted |

**Typical order**: `title → (tldr) → introduction/motivation → (background) → method… → experiment → result… → (discussion) → conclusion → (qna)`.

## Paper section → slide role mapping

Not 1:1, but an N:M content reorganization:

| paper_meta.json's section.kind | primarily fed to slide role |
|---|---|
| `abstract` | `tldr` (take the core contributions) + subtitle candidate for `title` |
| `introduction` | `motivation` (first 2/3) + `tldr` (the contributions in the last 1/3) |
| `background` / `related` | `background` (at most 1 slide; omitted in most cases, just weave in a sentence or two when explaining the method) |
| `method` | all `method` slides, with the body aggregated by subsection (e.g., architecture / loss / training) |
| `experiment` | `experiment` slide |
| `result` | `result` slides (main results + ablation, one slide each) |
| `discussion` | `discussion` (only when Discussion/Limitations has a strong conclusion) |
| `conclusion` | `conclusion` |
| `references` | **skip** (do not make a reference-dump slide) |

## Content guide for each role

### `title`
- `title`: use the title from `paper_meta.json/title` after verification
- `bullets`: leave empty `[]` (the title slide has only the title, subtitle, authors)
- In `slide_spec.json`, usually a dark color scheme + large title + authors centered or left-aligned
- `speaker_notes`: a welcome + 1 sentence on the paper's highlight

### `tldr`
- `title`: something like "TL;DR" / "Key Contributions" / "What We Did"
- `bullets`: the paper's core contributions, **starting with a verb** ("Propose ...", "Show that ...", "Achieve ...").
  Source: the end of the abstract + the contributions list in the introduction
- `needs_figure`: usually false (unless there is one extremely minimal "main result" figure)

### `introduction` / `motivation`
- `title`: something like "The Problem" / "Why This Matters" / "Limitations of Prior Work"
- `bullets`: first state the status quo ("existing X methods rely on Y"), then the shortcomings ("the cost of Y is Z"), leading to "we need ..."
- `needs_figure`: optional; strongly recommended when the paper has a "problem figure" (before/after, typical failure case)
- Source: the first half of `introduction`

### `background` (optional)
- Add only when the paper's method strongly depends on some prior concept (e.g., the forward/reverse process of a Diffusion Model)
- Prefer explaining with a figure (e.g., an equation/flowchart), use textual definitions sparingly
- Do not turn Related Work into background — Related Work should be folded into motivation or omitted

### `method` (2-3 slides)
- First slide: **architecture overview**. `needs_figure: true`, `figure_ref` points to the paper's "main figure" (usually the overall architecture in Figure 1 or Figure 2)
- Second slide: **key innovation**. Which component is the paper's novelty concentrated in? Explain that component clearly on its own (e.g., the "Scaled Dot-Product Attention" of the Transformer paper)
- Optional third slide: **training/optimization strategy** (if there is a non-trivial loss / data augmentation / curriculum)
- Keep bullets short, replace equations with figures rather than inline LaTeX

### `experiment`
- `title`: something like "Experimental Setup"
- `bullets`: **datasets**, **baseline**, **metric**, **hardware/scale**
- `needs_figure`: usually false; if the paper's datasets table is concise, an image can be used
- Source: the `experiment` section

### `result` (1-2 slides)
- First slide, main results: `needs_figure: true`, pair it with the paper's main result table (just crop the full page from `page_renders` — making the table as a PptxGenJS table is too tedious)
- Second slide (optional), ablation / analysis: use the 1-2 most convincing ablation figures
- bullets: **let numbers** do the talking, "+3.5 BLEU on EN-DE", avoid a vague "significant improvement"

### `discussion` (optional)
- `bullets`: include one **limitation** (this is a big plus; the audience immediately sees the honesty of the research)
- Source: the `discussion` section

### `conclusion`
- `title`: something like "Conclusions" / "Takeaways"
- `bullets`: usually cover — what we did (one sentence), key results (with numbers), future work (one sentence)
- Source: the `conclusion` section + a callback to `tldr`

### `qna` (optional)
- Plain text "Questions?" + contact info
- Most conference talks do not need a standalone Q&A slide

## Content-shaping rules

- **Text volume is decided by layout, with no word-count cap**. When writing bullets in Stage 2, keep in mind: each
  slide must ultimately be filled by "visual elements + text" — no whitespace and no overflow; **first think about
  what visual goes on the slide, then fill the remaining space with text to just-substantial, do not cut content
  down in advance to the point that it cannot hold up a slide**. The single authority for space-driven details such
  as lower/upper bound, the font-size red line, and **every slide must have a visual element (no text-only slides)**
  is §4 of [design-style.md](design-style.md) (+ the §0.4 space-check loop); Stage 3 does the final fill based on it,
  and this section does not repeat it
- **A bullet is a distilled key point, not a transcription** (the direct criterion for writing bullets in Stage 2):
  no copying a whole paragraph of the abstract, no full sentence-ending periods + stacked long modifiers; "short
  enough or not" is judged by "is it a single clear point", not by a word count. For the full principle see §4 of
  [design-style.md](design-style.md)
- **Do not repeat the slide title inside a bullet** (the title is "Method", so a bullet should not write "Our method..." again)
- Numbers must carry a unit/comparison ("+3.5 BLEU vs. baseline"), do not say a vague "significant improvement"
- speaker_notes: the speaker's **spoken-delivery script** (not lengthy background), so the speaker can read it aloud and still flow smoothly

## Pairing figures with slides (how to fill `figure_ref`)

Every figure in `paper_meta.json/figures[]` has an `id`, `page`, and `caption`. Pairing strategy:

1. **method first slide → the paper's Figure 1 or Figure 2** (the "main architecture figure" of the vast majority of papers)
2. **result main figure → the largest figure or main table in the paper's result section** (check whether the `figures` / `tables` captions contain "main results" etc.)
3. **motivation → pick a figure with before/after, failure cases** (the caption has "examples", "comparison", "motivating")
4. **ablation slide → pick a figure whose caption contains "ablation", "effect of", "varying"**
5. When unsure, prefer `pages/page-NN.png` (full-page render) or `figures/<id>.png` (the MinerU high-resolution crop)

`figure_ref` takes the figure id from the paper (e.g., `"figure2"`), letting you in Stage 3 decide exactly how to use it (embed vs. full-page crop).

> **bbox is a Stage 3 matter**: when `figures_index.json/captions[i]` already carries a `bbox` field (the precise table boundary detected by the script), Stage 3 uses it directly; only when missing does it fall back to visual estimation. Stage 2 does not need to worry about bbox, just fill `figure_ref`.

> **Equations work the same way**: the mineru backend fills `paper_meta.equations[]`, and each slide can also fill `equation_ref: "eq_5"` (parallel to `figure_ref`), from which Stage 3 decides Unicode rewrite / crop the original image / put it only in speaker_notes. For details see the equations part of `references/design-style.md`.

> **Appendix vs body (important)**: each `figures[i]` / `tables[i]` / `equations[i]` carries an `is_appendix: bool` field. **By default Stage 2 only picks entries with `is_appendix == false`** — a figure in the appendix (e.g., the attention visualizations in Figures 3-5 after References in the attention paper) is usually supplementary material and is usually not shown in a standard deck. Exceptions: for a long keynote, a supplementary-material talk, or when you judge that some appendix figure is critical to the narrative, you may explicitly pick entries with `is_appendix == true`, and note "from appendix" in speaker_notes. The decision rule is simple: a page after the References section is marked as appendix; for details see the `is_appendix` description in `references/schemas.md`.

## Audience adaptation (the `audience` field)

- `researchers`: keep the terminology, bullets can be highly technical; speaker_notes concise
- `general`: explain terminology first; use analogies; the ablation slide is usually omitted
- `mixed`: keep the method part high-level; keep 1 ablation slide but explain it in plain terms

## When paper_meta is not enough

paper_meta is auto-extracted and can be imperfect, so you may see:
- the title grabbed wrong (interference from the first-page license)
- section boundaries misaligned (the method gets chopped up)
- the abstract contaminated with hyphenation

Before entering Stage 2, first do the 4 checks in the "Revisions you should make before entering Stage 2" list at the end of [schemas.md](schemas.md). **The check results are not written back to paper_meta.json**, but generate the outline using the verified understanding.

---

> **Stage 3 visual-consistency hard rules** (consistent font size within the deck / avoid orphan words / proportional figure scaling / balanced element distribution) — see the "0. Visual-consistency hard rules" section of [design-style.md](design-style.md), **to be followed before all other design suggestions**.
