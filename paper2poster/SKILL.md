---
name: paper2poster
description: "Convert academic papers (PDF) into conference posters (HTML/PNG). You are the conductor: you decide what each section needs — an original paper figure or text — write the outline, hand-author the poster HTML, and iterate on the render using a VLM visual score and a content-fidelity quiz. Use when the user wants a poster from a paper PDF."
arguments: [pdf-path]
allowed-tools:
  - Bash(python *)
  - Bash(conda run *)
  - Read
  - Write
  - Glob
  - Grep
  - Agent
user-invocable: true
disable-model-invocation: false
effort: high
---

# Paper2Poster — Conference Poster Skill (You as Conductor)

Convert a paper PDF into an academic conference poster (HTML/PNG) by walking a small set of CLI scripts. **You are the conductor**: this file is the recipe, not an orchestrator. There is no `run_pipeline.py` — at each step you run one Bash command, read the intermediate artifact, and ask the user for confirmation at the decision points below.

```text
PDF
  → parse_pdf.py            (MinerU → content.md + figures/)
  → intake QA               (you ask size/venue/authors/visual policy)
  → auto_outline.py         (digest.json + assets[])
  → choose visuals          (you read parsed/figures/ + captions: which sections use an original figure, which use text)
  → outline.json            (you write from content.md; user confirms)
  → poster.html             (you hand-author the poster: original figures where they help, text elsewhere)
  → render + score          (Playwright PNG → geometry check + VLM visual score + PaperQuiz content check)
  → iterate on poster.html  (edit + re-render + re-score until it reads like a real poster)
  → poster.png
```

`problem_context`, `method_main`, and `result_evidence` are a useful **reading-order spine** to think about — what's the paper about, how does it work, what's the evidence. For each, decide what carries it best: an original paper figure if one reads well at poster scale, or text (a worded explanation, a labelled box, a short list) if no figure fits. There is **no figure quota** — use as many or as few original figures as the content calls for, down to zero. A text-only section, or a text-only poster, is a legitimate outcome when the figures don't earn their place.

---

## How you run this skill

This skill only works if you execute it as a sequence of small Bash + Read + AskUserQuestion turns. Do not try to short-circuit it.

1. **Run one step at a time** with the `Bash` tool, exactly as written below. Use absolute paths under `${SKILL_DIR}` (the directory this skill lives in — e.g. `<…>/paper2anything/paper2poster`; set it once per shell with `export SKILL_DIR=<…>/paper2anything/paper2poster`).
2. **Read the intermediate artifact** before moving on:
   - after Step 3: the figures you considered, viewed in `parsed/figures/` (and their captions in `digest.json`), and which sections you decided to carry with text instead,
   - after Step 5: your rendered `poster.png`, plus its VLM visual score and PaperQuiz result.
3. **Pause for the user at the decision points** with `AskUserQuestion`:
   - After Step 2 — intake: size, venue, author block, visual policy.
   - After Step 3 — is your per-section visual plan (which sections use an original figure, which use text) acceptable?
   - After Step 4 — is the outline structure acceptable?
   - After Step 8 — accept the poster, or revise/restyle it?
4. **Let the content decide whether a section gets a figure.** Use an original paper figure where one genuinely helps; carry a section with text when no figure earns its place. Don't pad the poster with weak figures to hit a count, and don't strip a figure that's doing real work. A text-only section — or a text-only poster — is fine.
5. **Score every render, then iterate (Steps 5–7).** After each render, run the geometry check, the VLM visual score, and (for content fidelity) PaperQuiz; let what they surface drive the next edit. Don't ship the first render unscored. The geometry check is **two-sided**: not just "no overflow" but also a **fill ratio ≥ 0.95** — a poster that fits but leaves large whitespace (or shrinks text to do so) fails and must be iterated. Verify this gate yourself; how you reach it is your judgment.
6. **Don't overwrite a good render — keep scored candidates.** Iteration is not always monotonic: an edit aimed at one issue can regress overall quality, and the version you had three edits ago may have read better. Before a non-trivial restyle or structural change, save the current render as a numbered candidate (e.g. copy `poster.html`/`poster.png` to `poster_candN.html`/`poster_candN.png`) and record its scores. Pick the final from the best-scoring candidate, not just the latest edit. Never let a higher-scoring intermediate be silently overwritten by a worse one.
7. **On error, stop and diagnose.** Do not silently fall back to a degraded path to "make it run."

---

## Step 0: Environment Check

> **统一环境**：本 skill 所有 `python` 命令都运行在 paper2anything 包的统一 conda 环境里（由顶层 `environment.yml` 创建），命令均以 `conda run -n paper2anything --no-capture-output` 为前缀。下面的 `pip install` 仅在统一环境缺依赖时兜底；`playwright install chromium` 仍需单独执行一次。

```bash
conda run -n paper2anything --no-capture-output python ${SKILL_DIR}/scripts/check_env.py
```

If anything is missing:

```bash
pip install Pillow PyMuPDF requests openai playwright
playwright install chromium
```

**Credentials (unified):** all keys live in the package-root `.env` (copy from `.env.example`, gitignored). Export once per shell before running any command below: `set -a; source <paper2anything 包根>/.env; set +a`. This skill uses `MINERU_API_TOKEN` and `DASHSCOPE_API_KEY`/`API_KEY`.

| Variable | Purpose | Default |
|---|---|---|
| `MINERU_API_TOKEN` | MinerU PDF parsing | — |
| `DASHSCOPE_API_KEY` / `API_KEY` | Qwen LLM + Qwen3-VL | — |
| `API_BASE_URL` | OpenAI-compatible base URL override | DashScope |
| `VLM_MODEL` | Vision critic model | `qwen3-vl-plus` |
| `PAPER2POSTER_VLM_FIGURE_SELECT` | VLM toggle for the optional figure selector (Step 3) | `1` (on) |
| `PAPER2POSTER_ALLOW_NO_SELECTION` | Bypass figure gate (text-only papers) | unset |

DashScope endpoint: `https://dashscope.aliyuncs.com/compatible-mode/v1`. Do not reuse Anthropic env vars from Claude Code — its proxy rejects non-CLI traffic.

---

## Step 1: Parse the PDF

产出统一落在**论文旁** `<pdf目录>/.paper2anything/poster/`（与 slides / html / xhs / wechat 一致）。下面每个步骤是**独立的 Bash 调用、互不共享 shell 变量**，所以每个用到运行目录的命令块都在开头就地从 `$pdf_path` 算出 `RUN_DIR`（和始终可用的 `${SKILL_DIR}` 一样、每次都在；切勿只在某一步 `export` 一次就指望后续步骤还在）。脚本仍在 `${SKILL_DIR}/scripts`。

```bash
RUN_DIR="$(dirname "$pdf_path")/.paper2anything/poster"
mkdir -p "$RUN_DIR"
conda run -n paper2anything --no-capture-output python ${SKILL_DIR}/scripts/parse_pdf.py "$pdf_path" \
  --output-dir "${RUN_DIR}/parsed"
```

Fallbacks: `--parser marker` (local, GPU) or `--parser pymupdf` (basic, no semantic figures).

Produces:
- `parsed/content.md` — full text in Markdown
- `parsed/metadata.json` — title, authors, affiliations, abstract
- `parsed/mineru_raw.json` — typed blocks with bbox + captions (MinerU only)
- `parsed/figures/`, `parsed/tables/`

---

## Step 2: Poster intake — confirm layout-critical choices [INTERACT]

Before designing anything, collect the few choices that actually change the poster. Now that the PDF is parsed you can show the user the parsed title/authors and ask the rest in **one short grouped `AskUserQuestion`** (don't turn this into a long form). The full checklist and defaults are in [`references/poster_intake_qa.md`](references/poster_intake_qa.md); the five that matter:

1. **Size / aspect** — e.g. `48x36 in landscape`, `36x24`, `A0`, `16:9 screen`. Default: `48x36 in landscape` (or `16:9` if the user says demo/slide/screen). This sets the render pixel size in Step 5.
2. **Venue / context** — which conference, workshop, or review setting. Tunes density and tone, not hard rules.
3. **Author block** — use the parsed authors/affiliations (show them), anonymize (`Anonymous Authors`, blind review), or custom text. Default: parsed.
4. **Visual policy** — use the original paper figures. When an original figure isn't poster-friendly (too cluttered, too small, or no figure fits a section), use text for that section instead — a worded explanation, a text box, or a short list. Default: original figures where they read well, text otherwise; no figure quota.
5. **Output directory** — the **run/work directory** for this whole job: every artifact the workflow produces (`parsed/`, `digest.json`, `outline.json`, `poster.html`, `poster.png`, the score JSONs, any candidates) is written here, not just the final poster. Default: `${RUN_DIR}`. Ask so the user can redirect the entire run to a folder they choose (e.g. their Desktop or a project dir); if they name one, use it as the `--output-dir` / `--output` base for **every** step below (Step 1 parse, Step 2 digest, Step 4 outline, Step 5 render, Steps 6–7 scores) so nothing lands in the default work dir. Report that path in Step 8.

The output is an HTML/PNG poster (`poster.html` + `poster.png`). If the user just says "make a poster" with no answers, state the defaults you're using and proceed — don't block. **Record the answers in `outline.poster_intake`** (Step 4) so the design and any critique treat them as hard constraints. The size you settle on here is what Step 5 renders at (e.g. `20x15 in` → `1920x1440 px`, `48x36 in` → `2304x1728` at 48 dpi or scale to taste).

```bash
RUN_DIR="$(dirname "$pdf_path")/.paper2anything/poster"
conda run -n paper2anything --no-capture-output python ${SKILL_DIR}/scripts/auto_outline.py \
  --parsed-dir "${RUN_DIR}/parsed" \
  --output     "${RUN_DIR}/digest.json"
```

`digest.json` is ~17× smaller than `mineru_raw.json`: section-grouped, figures/tables attached to their nearest preceding section, References/Appendix dropped. It also exposes a typed `assets[]` array (PosterAgent-style) where each entry has `type` (`claim` / `metric` / `figure` / `table`), `role` (`problem` / `method` / `result` / `takeaway` / `contribution` / `limitation`), and `priority` (1–5). **The `role`/`priority` tags are raw keyword heuristics — convenience hints for the optional fallback selector, not a ranking to trust.** When you write the outline (Step 3) you judge content importance yourself from `content.md`; don't defer to these scores.

If `mineru_raw.json` is missing (pymupdf path), skip this step and read `content.md` directly.

---

## Step 3: Decide each section's visual — figure or text, YOU choose by eye [INTERACT]

Deciding what carries each section is the **same judgment you make when hand-authoring the HTML** (does this section need a figure at all; if so, which one dominates, which is wide enough to span full width). So make it yourself, here, by looking at the figures — not with a keyword script.

1. **List the extracted figures.** `digest.json` has a `figures[]` / `tables[]` array (each with `image_path`, `caption`, `section`, `page`); the image files live in `parsed/figures/`. Read the captions, and **Read the actual image files** for the plausible candidates — a caption that says "pipeline" can sit over a figure that is useless at poster scale, and only your eyes catch that.

2. **For each part of the reading-order spine, decide figure-or-text:**
   - `problem_context` — frames the task / prior-work limitation / a vivid input example. *"What is this paper about"* should land here.
   - `method_main` — how it works: the dominant pipeline / architecture / algorithm.
   - `result_evidence` — the strongest evidence for the headline claim: a comparison plot, a qualitative grid, an ablation curve, or results numbers.

   For each, use an **original figure** if one is self-explanatory at a glance, large enough to stay sharp when enlarged, and not awkwardly tall/narrow — otherwise carry that part with **text** (a worded explanation, a labelled box, or a short list). Don't reuse the same figure twice, don't force a figure where none fits, and don't cap yourself at three — a section outside this spine can take a figure too if it earns one. The spine is a thinking aid, not a quota.

3. **Confirm with the user** via `AskUserQuestion`: lay out your per-section plan (for each: figure id + one-line "why this one", or "text — no good figure"), and ask *accept this plan, or swap something?* Proceed only when accepted.

You don't need to copy files anywhere — just record each chosen figure's path so you can reference it in `outline.json` (Step 4) and embed it in the HTML (Step 5).

**Optional fallback — heuristic + VLM selector.** If you want a scripted short-list to start from (or a reproducible deterministic run), `scripts/select_poster_figures.py --digest … --figures-dir … --output-dir …` ranks candidates by caption/geometry heuristics and (with `--use-vlm`, the default) has Qwen3-VL suggest one per role, writing `selected_figures.json` + a preview composite. This is a convenience, not the primary path — its picks are a suggestion you still verify by eye, and you remain free to choose text over any of them.

---

## Step 4: Write the outline [INTERACT]

You read the **full parsed paper** (`parsed/content.md`) and write `outline.json` directly with the `Write` tool, following the per-section visual plan you set in Step 3 (which sections embed an original figure, which are carried by text). You are the conductor here — selecting and condensing the paper's content into poster form is a judgment task, not a mechanical extraction. Do **not** just copy `digest.json`'s auto-extracted sections (they are dense source prose); decide yourself what belongs on the poster and how to phrase it.

**Goal, not quota.** Make a poster that reads like a real conference poster — study the 8 real CVPR/ICLR examples in [`references/poster_examples/`](references/poster_examples/) for how much text, how many sections, and what density real posters use. Let the paper's own shape drive the structure: a method-heavy paper may need a long process section with a big diagram; a results paper may be one line plus a dominant table. There is **no fixed section count or bullet count** — use what the content and the real-poster aesthetic call for.

**The one hard constraint** is physical, not stylistic: every bullet and label must fit inside its panel and stay readable at 1–2 m — no overflow, no text shrunk to fit. The geometry check and VLM score in Step 5 measure this; if a panel overflows or is too sparse, that's your signal to cut, tighten, or add — not a reason to keep dense source text. Write each bullet as `**Bold lead**: short detail`, keep raw numbers inside worded sentences/lists rather than as standalone visual anchors, and for any section you decided gets an original figure (Step 3), reference it in that section's `figure` field. Sections you decided to carry with text simply have no `figure` field.

Then use `AskUserQuestion` to confirm structure with the user before continuing to the render step.

If the user wants an explicitly text-only poster, set `outline.poster_intake.visual_policy = "text_only"`; this also short-circuits the fallback figure gate. (Choosing text for some sections while using figures in others does not need this flag — it's just your normal per-section judgment from Step 3.)

(Outline JSON schema is below; color palettes too.)

---

## Step 5: Design the poster — YOU hand-author the HTML

**You are the poster designer, not a template picker.** The best
posters in this pipeline are the ones you write yourself: you have seen the
paper, you know each section's visual plan (figure or text) and the real pixel
dimensions of any figures you chose, and you can study real conference posters.
A fixed template cannot make the design judgments a good poster needs — whether
a section even wants a figure, which figure dominates, whether a wide figure
spans full width, where the claim anchors the eye, how dense each region is.
So **write the poster's HTML directly** and iterate on it by scoring the render.
There is no template to select and no repair-op vocabulary to obey.

**Design fresh for each paper — do not reuse a house style.** A real risk when
you've made posters before is silently copying your last one's look (same title
band, same color blocking, same grid). Resist it. Let *this* paper's content,
field, and figure shapes drive the layout: a benchmark paper, an RL/method
paper, and a systems paper should not look alike. Vary the palette (match the
field or the paper's own accent color), the structure (3-column grid vs a
left-spine flow vs a hero-on-top), and what dominates. If your new draft looks
like your previous poster, that's a signal to rethink, not a shortcut to take.

1. **Study the references.** Read 2–3 of the real CVPR/ICLR posters in
   [`references/poster_examples/`](references/poster_examples/) so your design
   targets that visual language (strong title band, a dominant hero element, a
   one-sentence claim, color-blocked sections, generous whitespace, big type).

2. **Check any figures' real shape.** For each section you decided gets an
   original figure, get its pixel size
   (e.g. `conda run -n paper2anything --no-capture-output python -c "from PIL import Image; print(Image.open('…').size)"`). A
   wide figure (≈2–3:1) must be placed full-column or full-width so it stays
   sharp — never squeeze a wide figure into a narrow box; that is what makes
   figures look like thumbnails.

3. **Write `poster.html` yourself** with the `Write` tool: a self-contained
   HTML file (embed each original figure as a base64 `data:` URI so it opens
   standalone). Design freely — pick the grid, the type scale, the color
   blocking, where the claim sits, what dominates. Size the poster to
   the intake (`poster_intake.size`, e.g. 20×15 in → 1920×1440 px at 96 dpi).
   Use the outline you wrote in Step 4 as the content source. Sections you
   planned as text get a worded treatment (a paragraph, a styled text box, or a
   short list); sections with a figure embed it.

   **Figure CSS — make the border hug the image, never frame empty space.** A
   recurring bug: setting `width:100%` + `max-height:X` + `object-fit:contain`
   on an `<img>` paints the border on the *full-width box* while the image
   shrinks to fit inside it, leaving large white margins between the border and
   the actual picture (a small image floating in a big framed box). Avoid it —
   pick one of two patterns so the border traces the image edge:
   - **Fill the column** (preferred when the figure's natural height fits):
     `display:block; width:100%; height:auto;` + border. The image spans the
     column and the border hugs it; this also keeps the figure's own labels as
     large as possible.
     - **Cap the height, center it** (when full-width would be too tall):
     `display:inline-block; max-height:X; width:auto; height:auto;` + border, in
     a `text-align:center` wrapper. The border still traces the image; a small
     side margin is fine — what you must avoid is `object-fit:contain` on a
     fixed-width box. Don't combine `width:100%` with `object-fit:contain`.

   **Never force a fixed `height` (or fixed `width` *and* `height`) to fill a
   gap — it distorts the figure.** Tempting fix when a panel has leftover
   whitespace: stretch its image taller with `height:640px`. Don't. A figure
   must always scale *proportionally* — set at most ONE axis (`width:100%;
   height:auto`, or `max-height:X; width:auto`) and let the other follow. A real
   run set `height:640px; width:auto` on a 1.64:1 chart; a competing width
   constraint then pinned the width too, squashing it to 1.02:1 (60% vertical
   stretch) — a screenshot bug the eye catches instantly. Fill leftover
   whitespace with *content* (a takeaway box, an extra bullet) or by rebalancing
   columns — never by distorting a figure. Verify after every render:
   `renderedWidth/renderedHeight` must equal `naturalWidth/naturalHeight` within
   ~0.02 for every `<img>`; flag any mismatch as a distortion bug.

4. **Render, then score it — three checks, every render.** Screenshot at the
   poster's exact pixel size with the standalone screenshot instrument:

   ```bash
   RUN_DIR="$(dirname "$pdf_path")/.paper2anything/poster"
   conda run -n paper2anything --no-capture-output python ${SKILL_DIR}/scripts/screenshot.py \
     "${RUN_DIR}/poster.html" \
     "${RUN_DIR}/poster.png" \
     --width 1920 --height 1440
   ```

   Set `--width/--height` to your intake size (20×15 in → 1920×1440 at 96 dpi).
   This tool only screenshots the HTML you wrote — it picks no template and makes
   no design decision. Then run all three checks (none is optional — they are how
   you know what to fix next):

   - **(a) Deterministic geometry check — two-sided.** Overflow, clipping,
     unequal columns, *and underfill* are all measurable — measure them, don't
     eyeball a downscaled PNG. Use Playwright to read the box model:
     - **No overflow:** `body.scrollHeight` must be `<=` the canvas height (else
       content spills off the bottom); each figure's `<img>` right/bottom must sit
       inside its panel; columns should end at roughly the same `y`.
     - **No underfill (hard gate):** the poster must actually *fill* the canvas.
       Compute a fill ratio (content height ÷ canvas height, and per-column /
       per-panel where it helps); **the fill ratio must be ≥ 0.95.** A poster that
       merely "doesn't overflow" is not done — large bottom whitespace, sparse
       panels, or text shrunk small enough to leave gaps all fail this gate.
     - **No trapped internal whitespace (per-panel gate):** page-level
       `scrollHeight` does NOT catch this — when flexbox stretches panels to equal
       height, a panel with too little content silently pools a large empty gap at
       its *bottom* while the page still looks "full." Measure **both** the
       bottom gap AND the gaps *between* a panel's children: for each panel,
       `panel.bottom − lastChild.bottom` (bottom void) and
       `max(child[j].top − child[j−1].bottom)` (inter-element void); **flag either
       if it exceeds ~60px.** Measuring only the bottom gap has a blind spot:
       `justify-content:space-between` (and similar) makes the bottom gap read ~0
       while shoving the same whitespace *between* the figure and the text — a
       real run looked "fixed" by the bottom test yet had a 347px hole between a
       figure and its caption. **Fill a void with real content, not by spacing
       things apart.** The right fixes: add genuine paper content (one or two
       more bullets — papers usually have more findings than one panel shows),
       enlarge a figure to fill the column (proportionally — never a forced
       height), bump the body type scale (also helps legibility), or rebalance
       which sections share a column. The wrong fix is `space-between` /
       `margin:auto` / giant gaps, which just relocate the void. (A real run that
       *filled* the voids with content rose from VLM 69→78, severe 2→0; the same
       poster "fixed" with `space-between` stayed at 69.)
     - **No distorted figures (aspect-ratio gate):** for every `<img>`, the
       rendered `width/height` must match `naturalWidth/naturalHeight` within
       ~0.02. A figure stretched to fill space (e.g. a forced `height:`) is an
       obvious eyesore the VLM and any viewer catch instantly. (A real run
       squashed a 1.64:1 chart to 1.02:1.) If flagged, restore proportional
       scaling — see the figure-CSS rule in step 3, and fill the freed space with
       content, not a stretched image.

     This check is **two-sided on purpose**: a single "did it overflow?" test has
     only a ceiling and silently passes an under-filled, shrunk-down poster. Do not
     stop at "fits." After every edit, re-measure and confirm `0.95 ≤ fill ≤ 1.0`
     with no overflow — this is a pass/fail gate you verify yourself, not a
     suggestion, and how you reach it (what to resize, cut, reflow, or enlarge) is
     your judgment. A VLM looking at a shrunk full-poster PNG repeatedly mis-reports
     a full-bleed figure as "clipped" and misses both real bottom overflow and dead
     whitespace — trust the pixel math over the VLM for anything geometric.
   - **(b) VLM visual score — required.** Run `scripts/score_poster_visual.py`
     (Qwen3-VL via DashScope; see Step 6 for the command). It returns `score`,
     `verdict`, and `top_issues` for hierarchy, density, balance, and readability —
     the subjective read the geometry check can't give you. This is the standing
     "eyes" of the loop, **especially** when your own `Read` can't surface the PNG
     (some harnesses/proxies strip image blocks, so `Read` returns empty for a
     valid image — sanity-check at run start by `Read`-ing one small known PNG; if
     it's empty, lean entirely on the VLM rather than faking a visual judgment).
     When `Read` does work, look at the PNG too and cross-check the VLM — but the
     VLM score is run every render either way.
   - **(c) PaperQuiz content check — required (Step 7).** A good-looking poster
     can still fail to convey the paper. Run `scripts/paper_quiz.py`; it has a VLM
     answer questions from the poster alone and flags which roles aren't landing.

5. **Iterate until it reads like a real poster AND scores well.** Let the three
   checks drive each edit: the geometry check catches overflow/clipping/imbalance
   *and underfill*; the VLM `top_issues` catch weak hierarchy, cramped or sparse
   panels, a bare number used instead of a sentence, poor balance; PaperQuiz catches
   content that isn't getting through. When a check flags something, **edit the HTML
   and re-render** — shrink/cut overflowing text, enlarge a figure that reads as a
   thumbnail, fill or merge an empty panel with text, rewrite a number into a claim
   sentence, or move/replace a figure. Re-run the three checks after each edit.
   **Before a big restyle or structural change, snapshot the current render as a
   numbered candidate** (`poster_candN.html` + `poster_candN.png`) with its scores,
   so a regression doesn't destroy a version that read better — iteration isn't
   always monotonic, and you pick the final from the best-scoring candidate, not the
   latest edit. Repeat until the geometry check passes (no overflow **and fill ratio
   ≥ 0.95**), the VLM score is clean, and PaperQuiz shows the key roles land. **Don't stop the
   moment content stops overflowing** — that only clears the ceiling; verify the
   fill gate too, or you ship a shrunk-down poster full of whitespace. This is open
   visual iteration — your judgment guided by the scores, not a fixed op set.

**Hard constraint (the only one):** every piece of text and every figure label
must be fully visible inside its panel and readable at 1–2 m. No overflow, no
clipping, no text shrunk to illegibility. If content does not fit, cut or
condense it (back in the outline) — never let it spill or shrink to dust.

The final poster is `${RUN_DIR}/poster.png` (+ `poster.html` for editing).

---

## Step 6: VLM visual score — run on every render

This is the "eyes" of the iteration loop (Step 5, check b) — run it after each
render, not just once at the end:

```bash
RUN_DIR="$(dirname "$pdf_path")/.paper2anything/poster"
conda run -n paper2anything --no-capture-output python ${SKILL_DIR}/scripts/score_poster_visual.py \
  --png       "${RUN_DIR}/poster.png" \
  --outline   "${RUN_DIR}/outline.json" \
  --output    "${RUN_DIR}/visual_score.json"
```

Returns JSON with `score`, `verdict`, `top_issues`, `reading_order`, `repair_actions`.
Use `score`/`top_issues` to decide what to fix next — this is the subjective read
(hierarchy, density, balance, readability) that the geometry check can't give you,
and the primary signal when your own `Read` can't surface the PNG. The
`repair_actions` are a fixed enum the scorer emits — treat them as hints about
*what* is off, not a vocabulary you must translate edits into; you still iterate by
editing `poster.html` directly. Cross-check against your own eyes when `Read` works,
but run the score every render regardless.

---

## Step 7: PaperQuiz content fidelity — required content check

The VLM visual score (Step 6) tells you whether a poster *looks* right.
**PaperQuiz** tells you whether a reader can actually answer questions about the
paper from the poster (PosterAgent metric, arXiv:2505.21497) — run it as part of
the iteration loop, not just as a final gate, so content gaps drive edits too.

```bash
RUN_DIR="$(dirname "$pdf_path")/.paper2anything/poster"
conda run -n paper2anything --no-capture-output python ${SKILL_DIR}/scripts/paper_quiz.py \
  --digest      "${RUN_DIR}/digest.json" \
  --poster-png  "${RUN_DIR}/poster.png" \
  --output      "${RUN_DIR}/paper_quiz.json" \
  --language en --n 6
```

Pipeline:

1. `qwen-plus` reads the digest and writes 5–8 multiple-choice questions across `problem` / `method` / `result` / `takeaway` (+ optional `contribution` / `limitation`). Distractors come from sibling sections so wrong options stay plausible.
2. `qwen3-vl-plus` is shown only the rendered poster PNG and answers each question (single letter A/B/C/D + short evidence note, or `?`).
3. The script scores correctness, breaks accuracy down by role, and flags any role with miss rate ≥ 0.5. It also emits a fixed `suggested_repair_actions` enum — treat these as advisory hints about *which content is not landing*, not a vocabulary you must translate edits into. You fix content fidelity by editing the outline / `poster.html` directly.

Use it to:

- Drive a repair round whenever a role's miss rate is high — that role's content isn't getting through, so make it bigger, clearer, or add the missing fact.
- Decide whether the poster is good enough to ship (e.g., `quiz_score ≥ 80` with no role failing).
- Re-rank candidates by `quiz_score` when you've tried more than one layout.

---

## Step 8: Preview & iterate with the user [INTERACT]

Once your own iteration (Steps 5–7) has the poster reading cleanly and scoring
well, show it to the user:

1. **Get the current design into your context** — `Read` `${RUN_DIR}/poster.png`
   if image read works; otherwise rely on the latest VLM `visual_score.json`.
2. Briefly describe the design choices you made (layout, what dominates, claim,
   which sections use a figure vs text).
3. Use `AskUserQuestion` to offer:
   - **Accept** — deliver `${RUN_DIR}/poster.png` as final.
   - **Revise** — the user points at something; you **edit `poster.html`
     directly** and re-render. Same scored iteration as Steps 5–7 — re-run the
     three checks after the edit. No fixed repair vocabulary.
   - **Restyle** — try a different visual direction (different grid, color, or
     what dominates, or swapping a figure for text / text for a figure) by editing
     `poster.html`.

When approved, report the final `poster.png` from the run directory (`outline.poster_intake.output_dir`, e.g. `${RUN_DIR}/poster.png` by default, or the folder the user chose in Step 2 — where every artifact for this run already lives).

---

## Outline JSON Format

```json
{
  "title": "Paper Title",
  "authors": "Author1, Author2",
  "affiliations": "University of X",
  "contact": "email@example.com",
  "poster_intake": {
    "size": "20x15 in landscape",
    "venue": "AAAI poster session",
    "author_policy": "parsed",
    "output_target": "html_png",
    "output_dir": "<pdf目录>/.paper2anything/poster",
    "visual_policy": "original_figures_or_text"
  },
  "color_scheme": {
    "primary": "#1B3A5C", "secondary": "#2E86AB",
    "accent": "#A3D5FF", "background": "#FFFFFF", "text": "#1A1A2E"
  },
  "sections": [
    {
      "title": "Method", "column": "middle",
      "content": [
        "**Key Idea**: one-sentence summary",
        "Step 1: …", "Step 2: …"
      ],
      "figure": "figures/fig1.png"
    }
  ]
}
```

Suggested starting palettes (pick whatever the design calls for — `color_scheme` is free): CS/AI blue (`#1B3A5C`/`#2E86AB`), Bio/Med green (`#2D6A4F`/`#52B788`), Physics/Math purple (`#5A189A`/`#9D4EDD`), Engineering orange (`#E76F51`/`#F4A261`). More in [references/color_palettes.md](references/color_palettes.md).

---

## Troubleshooting

- **MinerU 401**: token missing — set `MINERU_API_TOKEN` from `https://mineru.net/apiManage/token`.
- **MinerU OSS download stalls**: requests through MinerU's presigned OSS URLs need `proxies={"http": None, "https": None}` to bypass system proxy (already handled in `parse_pdf.py`).
- **DashScope 401 / 403**: confirm `DASHSCOPE_API_KEY` (or `API_KEY`) is set and base URL is `https://dashscope.aliyuncs.com/compatible-mode/v1`. Don't reuse Anthropic env vars from Claude Code — its proxy rejects non-CLI traffic.
- **Playwright missing**: `pip install playwright && playwright install chromium`. The geometry check (Step 5, check a) and `screenshot.py` both need it.
- **Offline / no DashScope**: the visual score (`score_poster_visual.py`) and PaperQuiz (`paper_quiz.py`) both call DashScope and have no offline switch — for an explicitly offline run, just skip those two steps and rely on the deterministic geometry check (Step 5, check a). If a VLM call fails, `score_poster_visual.py` returns an error verdict rather than crashing.

For layout principles see [references/layout_guide.md](references/layout_guide.md) and [references/poster_design_guide.md](references/poster_design_guide.md). For agent-extracted design rules see [references/agent_design_rules_from_posters.md](references/agent_design_rules_from_posters.md).
