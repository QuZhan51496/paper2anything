---
name: paper2slides
description: "Turn an academic paper PDF into a presentation deck (.pptx) end-to-end. Use this skill whenever the user wants to \"make slides from a paper\", \"generate a deck from this PDF\", \"make a PPT from this paper\", \"generate slides from a PDF document\", \"make a deck from a research paper\", or supplies a research paper PDF and asks for a .pptx out. Trigger even when the user only says \"deck this paper\" or \"summarize as slides\". This is the dedicated, self-contained skill for academic-paper-to-deck flows."
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

# paper2slides

Turn an academic paper PDF into a presentation-ready .pptx. This is a conductor skill: **you** make the
editorial and design judgments, while the mechanical steps are handled by this skill's own self-contained
scripts — PDF parsing via the MinerU cloud API (`scripts/parse_pdf.py`) and .pptx rendering via a PptxGenJS
bridge (`scripts/render_pptx.py`). It orchestrates a "paper → outline → spec → render → QA" pipeline and
depends on no other skill.

## Quick Reference

| Stage | Input | Output | Owner |
|---|---|---|---|
| 0.5. configure | user dialogue | `<workdir>/config.json` | **you** (AskUserQuestion to confirm three items: length tier + whether to run visual QA + color scheme) |
| 1. extract    | `paper.pdf` | `paper_meta.json` + `figures_index.json` + `figures/` + `pages/` + `equations` + hi-res figure/table crops (produced in one shot by the MinerU cloud API) | `scripts/parse_pdf.py` |
| 2. outline    | `paper_meta.json` | `slide_outline.json` | **you** (per `references/outline-heuristics.md`) |
| 3. spec       | `slide_outline.json` + figures | `slide_spec.json` | **you** (per `references/design-style.md`) |
| 4. render     | `slide_spec.json` | `output.pptx` | `scripts/render_pptx.py` (PptxGenJS bridge) |
| 5. qa         | `output.pptx` | pass / fail + fix list | content QA always runs; **visual QA is gated by Stage 0.5's `config.json/visual_qa`** |

See `references/pipeline.md` for the detailed per-stage protocol.

## Invocation Contract

Invocation form:

```
/paper2slides <paper.pdf> [output.pptx] [--from-stage <name>] [--force]
```

- `output.pptx` omitted → `<paper-dir>/<paper-stem>_slides/<paper-stem>.pptx`; on a name collision the directory auto-appends `_v2 _v3`
- Intermediate artifacts land in `<paper-dir>/.paper2anything/slides/<paper-stem>/`; when the paper directory is read-only, fall back to `~/.cache/paper2anything/slides/`

**Python environment**: all scripts run in the `paper2anything` conda environment. Command prefix
`conda run -n paper2anything --no-capture-output python -m scripts.<name> ...`
(the prefix can be omitted once `conda activate paper2anything` is in effect). **Every `-m scripts.<name>` must be run from this
skill's directory (the parent of `scripts/`), otherwise you get `No module named 'scripts'`**; the prefix-omission convention is in
[references/pipeline.md](references/pipeline.md) §General Conventions.

**The first step is always to resolve the workspace**:

```bash
conda run -n paper2anything --no-capture-output python -m scripts.workdir resolve \
    <paper.pdf> [--output <out.pptx>] --ensure
```

The returned JSON contains all the named paths (`paper_meta_path`, `slide_outline_path`,
`slide_spec_path`, `figures_dir`, ...) and each stage's completion status. Every later stage references
the paths in this JSON — **do not assemble paths yourself**; the rules are centralized in `scripts/workdir.py`.

**Re-run semantics**:

| Flag | Meaning |
|---|---|
| default | already-completed stages are skipped (judged by whether the output files exist) |
| `--force` | ignore all markers and run everything |
| `--from-stage <name>` | re-run starting from the named stage (the entry point for the long-lived "interactive mode") |

`<name>` ∈ `{configure, extract, outline, spec, render, qa}`.
**To go through the three pre-flight questions again**, use `--from-stage configure` (overwrites the old `config.json`).

## Pipeline

Execute in the order below. Each stage has a "completion test" — once its output file appears the stage counts as done, and is auto-skipped on re-run.
**Each stage in this section writes only three things: (a) the minimal action to do (including the command to
type), (b) the single most error-prone pitfall, and (c) a pointer to the corresponding Stage in
[references/pipeline.md](references/pipeline.md)**. The full protocol, prerequisites, common errors, and edge cases all
live in pipeline.md; this section does not restate them.

### Stage 0.5 — Configure (you, AskUserQuestion to confirm three items)

After Stage 0 resolves the workspace and before Stage 1, use [AskUserQuestion] to confirm three items with the user,
and Write the answers to the Stage 0 JSON's `config_path` (`<workdir>/config.json`):

1. **`deck_length`**: concise / standard / detailed / auto (no page-count target, recommended)
2. **`visual_qa`**: `true` (default, adds the soffice→jpg→subagent visual loop) / `false` (run only the cheap content QA)
3. **`color_scheme`**: `auto` (default, Stage 3 matches a palette to the paper's character) / `custom` (the user describes a preference in one line, stored in config and parsed by Stage 3)

- **Reuse = skip**: when `config.json` already exists and neither `--from-stage configure` nor `--force` is given, don't ask again — reuse the last configuration.
- When the user's initial request already states a preference, set the corresponding item as the AskUserQuestion default (still show it for confirmation).
- The full option table, the `deck_length` page-count band mapping, and the prefill / downstream-consumption details are in [references/pipeline.md](references/pipeline.md) §Stage 0.5; the config.json schema is in [references/schemas.md](references/schemas.md).

### Stage 1 — Extract (script)

**Use the MinerU cloud API** (requires `MINERU_API_TOKEN`, configured uniformly in the paper2anything package-root `.env`; with no token it errors out immediately):

```bash
set -a; source <paper2anything package root>/.env; set +a   # export the unified .env (includes MINERU_API_TOKEN)
conda run -n paper2anything --no-capture-output python -m scripts.parse_pdf <paper.pdf>
```

Produces `paper_meta.json` + `figures_index.json` + `pages/` + hi-res crops in one shot (the structured metadata comes directly from MinerU).

For `--dpi` tuning (default 300) and the known imperfections of MinerU parsing (e.g. the bbox sometimes pins the `y` start onto a subfigure caption), see
[references/pipeline.md](references/pipeline.md) §Stage 1.

> **Pitfall**: before entering Stage 2 you **must run** the
> **4 checks** at the end of [references/schemas.md](references/schemas.md) (title/authors/same-kind merge/missing key kind) to verify `paper_meta.json`; **the check results are not written back to
> `paper_meta.json`**, but are reflected directly in the Stage 2 outline.

### Stage 2 — Outline (you)

Input `paper_meta.json` + `figures_index.json` + `config.json` → output
`slide_outline.json` (schema in [references/schemas.md](references/schemas.md)).
Per [references/outline-heuristics.md](references/outline-heuristics.md), set roles and
order, and write each slide's `title`/`bullets`/`figure_ref`/`speaker_notes`. **Pitfall**: read
`config.json/deck_length` first — `auto` does not constrain the slide count; a non-auto value is a **soft target for outline granularity**,
and you **must not** cut core narrative roles just to hit a number (details in outline-heuristics.md).

After writing, validate that the JSON is well-formed with Python:

```bash
conda run -n paper2anything --no-capture-output python -c \
    "import json,sys; json.load(open(sys.argv[1])); print('ok')" \
    <workdir>/slide_outline.json
```

For the full protocol and common errors, see [references/pipeline.md](references/pipeline.md) §Stage 2.

### Stage 3 — Spec (you)

Input `slide_outline.json` + `figures_index.json` + figures/ + pages/ → output
`slide_spec.json`. Per [references/design-style.md](references/design-style.md), choose
palette/fonts/`layout_kind` (avoiding consecutive repeats), and translate the content into `elements`. **Pitfall**:
every number and term must have a source in paper_meta / figures_index — do not fabricate.

When you need an icon use `kind:"icon"`; for naming see the "Icons" section of [references/pptxgenjs.md](references/pptxgenjs.md),
and for the schema see the icon element in [references/schemas.md](references/schemas.md).

When you need to crop a region from a full paper page:

```bash
conda run -n paper2anything --no-capture-output python -m scripts.page_screenshot \
    <workdir> <page> <x> <y> <w> <h>
```

bbox uses relative ratios 0..1; fill the output relative path into the corresponding image element's `path`. **Hard gate for cropping**:
the first call's bbox must be **value-for-value equal** to `figures_index.json/captions[i].bbox`, and **you may not eyeball
the full page before cropping the first version** — for the full baseline and the QA re-crop loop see
[references/design-style.md](references/design-style.md) §3 (**skipping the first cut and going straight to eyeballing
= violating §3**). The Stage 3 key constraints (coordinates ≤ canvas / `margin:0` etc.) are in
[references/pipeline.md](references/pipeline.md) §Stage 3.

### Stage 4 — Render (script)

```bash
conda run -n paper2anything --no-capture-output python -m scripts.render_pptx \
    <workdir>/slide_spec.json <workdir>/output.pptx
```

The output is `<workdir>/output.pptx`; after a successful render, copy it to the final `output_path` given by Stage 0 (first `mkdir -p` its parent directory `<paper-stem>_slides/`).
**Pitfall**: it depends on `node`+`pptxgenjs` (installed globally); if node is not on PATH the script errors. On failure, first
`--dry-run` to generate only `render/build.js` and locate the spec problem. For prerequisites and common errors see
[references/pipeline.md](references/pipeline.md) §Stage 4.

### Stage 5 — QA

Execute per the [QA](#qa) section below: content QA always runs, and visual QA is gated by `config.json/visual_qa`.

## Defaults & Errors

### Default behavior

| Input | Default |
|---|---|
| `output.pptx` omitted | `<paper-dir>/<paper-stem>_slides/` (containing `<paper-stem>.pptx`); on a name collision the directory appends `_v2`, `_v3` |
| work directory not writable in the paper directory | fall back to `~/.cache/paper2anything/slides/<paper-stem>-<hash12>/` |
| re-run on the same paper | already-completed stages (output files already exist) are auto-skipped |
| `config.json` already exists | Stage 0.5 skips the questions and reuses the last configuration; to change config use `--from-stage configure` |
| Stage 0.5 not asked / `visual_qa` defaulted | `deck_length=auto`, `visual_qa=true` (run visual QA) |
| `--from-stage <N>` | force a re-run from the named stage, without checking outputs |
| `--force` | force a re-run of all stages (rare, only on a schema upgrade) |

### Error-Recovery Quick Reference

Only the few classes that need **your judgment / routing** are listed (all technical recovery is in pipeline.md):

| Symptom | Handling |
|---|---|
| Stage 1 section count < 5 or > 15 | you manually add / merge during the Stage 2 check |
| Stage 5 reports "card bottom half empty / unbalanced columns / bottom whitespace" | **not soft** — fix per the **three-lever model** in `references/design-style.md` "Principles for Fixing QA Issues" (adjust text amount > adjust bullet spacing > adjust image size, stackable), then `--from-stage render` to re-run |
| user/QA reports "leader markers not aligned with text" | per `references/design-style.md` "Visual-Richness Recommendations" item A, batch-reset icon_y to the alignment formula + a final self-check, then `--from-stage render` to re-run |
| skill triggered but the user only wants to "read the PDF" | mis-trigger — tell the user this skill builds a slide deck and ask whether to proceed; do not continue with paper2slides if they only want to read the PDF |

For the full error recovery (Stage 1/4 technical, annotation green box, dpi, figure_ref, etc.) see the
"Error-Recovery Quick Reference" section of [references/pipeline.md](references/pipeline.md).

## QA

Apply the QA loop in [references/qa.md](references/qa.md) (the self-contained "Verification Loop" — content QA
+ visual subagent review). **Read `config.json/visual_qa` first**; the key points:

- **content QA always runs**: `markitdown` checks placeholders / number consistency / bullets not lifted from the abstract / no leftover placeholder in the title.
- **visual QA runs only when `config.json/visual_qa == true`**: soffice→pdf→jpg→**dispatch a single subagent to batch-review**.
- After fixing issues, edit `slide_spec.json` then `--from-stage render` to **fully re-render** before QA; **the recheck rounds narrow per the Verification Loop** — round 1 covers the full deck, from round 2 on look only at the pages flagged last round ∪ the pages changed this round, with a final full pass over the whole deck before convergence.
- **The final report must state whether visual QA was run**; when skipped, note "visual QA was skipped per config; to change config use `--from-stage configure` then `--from-stage qa`".
- **Whitespace / unbalanced columns / misaligned leader markers are not soft, they are hard issues that must be fixed** — this is where this skill most often misjudges; don't wave them off as "soft" when reviewing the subagent's report.

For the verification loop and the base visual-subagent prompt template, see [references/qa.md](references/qa.md);
for the full A/B protocol and the `qa_log.json` structure, see [references/pipeline.md](references/pipeline.md) §Stage 5;
for the visual subagent prompt's two added paragraphs, the three-lever fix model, and the recheck-narrowing details,
see the "Visual Subagent Prompt for QA" + "Principles for Fixing QA Issues" sections of
[references/design-style.md](references/design-style.md).

## Where to Look When Stuck

This skill is self-contained — everything you need is under `references/` in this directory:

| Confusion | Go here |
|---|---|
| MinerU parsing anomalies (missing figure / garbled text / misaligned table / lost formula) | [references/pipeline.md](references/pipeline.md) §Stage 1 + `scripts/lib/mineru_client.py` (token, `model_version`, zip-download retry) |
| PPT visual design, color palettes, layout choices, taboos | the "Design fundamentals" + "Avoid" sections of [references/design-style.md](references/design-style.md) |
| PptxGenJS API usage, gotchas, icon generation | [references/pptxgenjs.md](references/pptxgenjs.md) (includes the academic icon-name table) |
| QA flow and the visual-subagent prompt | [references/qa.md](references/qa.md) |
| Detailed JSON schema fields for each stage's output (including config.json) | [references/schemas.md](references/schemas.md) |
| How sections map to slide roles | [references/outline-heuristics.md](references/outline-heuristics.md) |
| Matching color/layout to the paper's scenario | [references/design-style.md](references/design-style.md) |
