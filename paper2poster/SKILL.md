---
name: paper2poster
description: "Convert academic papers (PDF) into conference posters (HTML/PNG). You are the conductor: you decide what each section needs — an original paper figure or text — write the outline, hand-author the poster HTML, and iterate on the render using your own visual read and a blind-reader content quiz. Use when the user wants a poster from a paper PDF."
arguments: [pdf-path]
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
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
  → render + score          (Playwright PNG → deterministic geometry check + your own visual read + blind-reader content quiz)
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
   - after Step 5: your rendered `poster.png`, plus your visual read and the blind-reader quiz result.
3. **Pause for the user at the decision points** with `AskUserQuestion`:
   - After Step 2 — intake: size, venue, author block, visual policy.
   - After Step 3 — is your per-section visual plan (which sections use an original figure, which use text) acceptable?
   - After Step 4 — is the outline structure acceptable?
   - After Step 8 — accept the poster, or revise/restyle it?
4. **Let the content decide whether a section gets a figure.** Use an original paper figure where one genuinely helps; carry a section with text when no figure earns its place. Don't pad the poster with weak figures to hit a count, and don't strip a figure that's doing real work. A text-only section — or a text-only poster — is fine.
5. **Score every render, then iterate (Steps 5–7).** After each render, run the deterministic geometry check and **look at the PNG yourself** (your visual read — hierarchy/density/balance/readability); run the **blind-reader content quiz** (Step 7) at milestones rather than on every micro-edit (it spawns a subagent, so it costs more than reading a PNG). Let what they surface drive the next edit; don't ship the first render unscored. The geometry check is **two-sided**: not just "no overflow" but also a **fill ratio ≥ 0.95** — a poster that fits but leaves large whitespace (or shrinks text to do so) fails and must be iterated. Verify this gate yourself; how you reach it is your judgment.
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
pip install Pillow requests playwright
playwright install chromium
```

**Credentials (unified):** all keys live in the package-root `.env` (copy from `.env.example`, gitignored). Export once per shell before running any command below: `set -a; source <paper2anything 包根>/.env; set +a`. This skill needs **only `MINERU_API_TOKEN`** (PDF parsing). Everything else — figure choice, design, the visual read (Step 6), and the content check (Step 7) — is done by you and a blind subagent, with **no external VLM / LLM API**.

| Variable | Purpose | Default |
|---|---|---|
| `MINERU_API_TOKEN` | MinerU PDF parsing | — |

---

## Step 1: Parse the PDF

产出统一落在**论文旁** `<pdf目录>/.paper2anything/poster/`（与 slides / html / xhs / wechat 一致）。下面每个步骤是**独立的 Bash 调用、互不共享 shell 变量**，所以每个用到运行目录的命令块都在开头就地从 `$pdf_path` 算出 `RUN_DIR`（和始终可用的 `${SKILL_DIR}` 一样、每次都在；切勿只在某一步 `export` 一次就指望后续步骤还在）。脚本仍在 `${SKILL_DIR}/scripts`。

```bash
RUN_DIR="$(dirname "$pdf_path")/.paper2anything/poster"
mkdir -p "$RUN_DIR"
conda run -n paper2anything --no-capture-output python ${SKILL_DIR}/scripts/parse_pdf.py "$pdf_path" \
  --output-dir "${RUN_DIR}/parsed"
```

MinerU (cloud) is the only parser — on failure the script exits non-zero. Fix the token / network and re-run.

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

`digest.json` is ~17× smaller than `mineru_raw.json`: section-grouped, figures/tables attached to their nearest preceding section, References/Appendix dropped. It also exposes a typed `assets[]` array (PosterAgent-style) where each entry has `type` (`claim` / `metric` / `figure` / `table`), `role` (`problem` / `method` / `result` / `takeaway` / `contribution` / `limitation`), and `priority` (1–5). **The `role`/`priority` tags are raw keyword heuristics — convenience hints, not a ranking to trust.** When you write the outline (Step 3) you judge content importance yourself from `content.md`; don't defer to these scores.

(`mineru_raw.json` is always produced by the MinerU parse, so `auto_outline.py` always has its input.)

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

---

## Step 4: Write the outline [INTERACT]

You read the **full parsed paper** (`parsed/content.md`) and write `outline.json` directly with the `Write` tool, following the per-section visual plan you set in Step 3 (which sections embed an original figure, which are carried by text). You are the conductor here — selecting and condensing the paper's content into poster form is a judgment task, not a mechanical extraction. Do **not** just copy `digest.json`'s auto-extracted sections (they are dense source prose); decide yourself what belongs on the poster and how to phrase it.

**Goal, not quota.** Make a poster that reads like a real conference poster — study the 8 real CVPR/ICLR examples in [`references/poster_examples/`](references/poster_examples/) for how much text, how many sections, and what density real posters use. Let the paper's own shape drive the structure: a method-heavy paper may need a long process section with a big diagram; a results paper may be one line plus a dominant table. There is **no fixed section count or bullet count** — use what the content and the real-poster aesthetic call for.

**The one hard constraint** is physical, not stylistic: every bullet and label must fit inside its panel and stay readable at 1–2 m — no overflow, no text shrunk to fit. The geometry check and your visual read in Step 5 measure this; if a panel overflows or is too sparse, that's your signal to cut, tighten, or add — not a reason to keep dense source text. Write each bullet as `**Bold lead**: short detail`, keep raw numbers inside worded sentences/lists rather than as standalone visual anchors, and for any section you decided gets an original figure (Step 3), reference it in that section's `figure` field. Sections you decided to carry with text simply have no `figure` field.

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
   Those examples are **wide (~2:1)**; at a squarer size like the 48×36 default
   (≈4:3) a *full-width* hero band or figure eats too much vertical budget and
   overflows — keep the hero **column-scoped** (or pick a 2:1 size) so the vertical fits.

2. **Check any figures' real shape.** For each section you decided gets an
   original figure, get its pixel size
   (e.g. `conda run -n paper2anything --no-capture-output python -c "from PIL import Image; print(Image.open('…').size)"`). A
   wide figure (≈2–3:1) must be placed full-column or full-width so it stays
   sharp — never squeeze a wide figure into a narrow box; that is what makes
   figures look like thumbnails.

3. **Write `poster.html` yourself** with the `Write` tool. **While iterating,
   reference figures by relative path** (`src="parsed/figures/x.jpg"`) —
   screenshot.py and geom_check.py resolve them via `file://`, and the file
   stays small and editable. Only at the end run
   `scripts/embed_figures.py poster.html` once to inline them as base64 `data:`
   URIs for a self-contained, distributable poster (don't hand-paste base64 — it
   bloats the file beyond what the render/edit loop can handle). Design freely —
   pick the grid, the type scale, the color blocking, where the claim sits, what
   dominates. Size the poster to the intake (`poster_intake.size`, e.g. 20×15 in
   → 1920×1440 px at 96 dpi). Use the outline you wrote in Step 4 as the content
   source. Sections you planned as text get a worded treatment (a paragraph, a
   styled text box, or a short list); sections with a figure embed it.

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
     --width 2304 --height 1728
   ```

   The example uses the **default** intake size (48×36 in → 2304×1728 at 48 dpi).
   Set `--width/--height` to *your* intake size (e.g. 20×15 in → 1920×1440 at 96 dpi)
   — they must match the size you recorded in `poster_intake`, not the example.
   This tool only screenshots the HTML you wrote — it picks no template and makes
   no design decision. Then run all three checks (none is optional — they are how
   you know what to fix next):

   - **(a) Deterministic geometry check — two-sided.** Overflow, clipping,
     unequal columns, *and underfill* are all measurable — measure them, don't
     eyeball a downscaled PNG. **Run the shipped checker for the three
     structure-agnostic gates** (no overflow; fill ratio ≥ 0.95 computed from the
     true content frontier — real text/image extent, not a fixed-height container;
     per-image aspect within 0.02). It exits non-zero on failure:
     ```bash
     conda run -n paper2anything --no-capture-output python ${SKILL_DIR}/scripts/geom_check.py \
       "${RUN_DIR}/poster.html" 2304 1728
     ```
     (pass the same width/height you rendered at — the example is the 48×36 default)
     It does **not** know your panel structure — still measure the per-panel
     voids below yourself (Playwright box model) and read the PNG:
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
       *filled* the voids with real content read markedly cleaner than the same
       poster "fixed" with `space-between`, which only moved the whitespace around.)
     - **No block overlap (manual — the geometry gate does NOT catch this).** A
       `geom_check` PASS does *not* prove blocks don't overlap: a `flex:1` column
       whose content exceeds its shrunk height *escapes downward* (overflow is
       visible by default) and can paint over a following full-width band, yet the
       box and the content both fit the canvas so overflow/fill/clip all pass. While
       you measure the per-panel boxes, also confirm each column's content `bottom`
       sits **above** the next full-width band's `top` — never trust the gate alone
       for overlap.
     - **No distorted figures (aspect-ratio gate):** for every `<img>`, the
       rendered `width/height` must match `naturalWidth/naturalHeight` within
       ~0.02. A figure stretched to fill space (e.g. a forced `height:`) is an
       obvious eyesore you and any viewer catch instantly. (A real run
       squashed a 1.64:1 chart to 1.02:1.) If flagged, restore proportional
       scaling — see the figure-CSS rule in step 3, and fill the freed space with
       content, not a stretched image.
     - **No clipped panels (panel-clip gate):** the checker also flags a panel that
       *hides* its own overflow — `overflow:hidden`/`auto` on a flex equal-height
       column whose content is taller than the box silently cuts the bottom off, and
       page-level `scrollHeight` won't catch it. If `clipped_panels` fires, don't
       mask it with `overflow:hidden` — drop the hidden so the box can grow, or cut
       the content until it genuinely fits.

     This check is **two-sided on purpose**: a single "did it overflow?" test has
     only a ceiling and silently passes an under-filled, shrunk-down poster. Do not
     stop at "fits." After every edit, re-measure and confirm `0.95 ≤ fill ≤ 1.0`
     with no overflow — this is a pass/fail gate you verify yourself, not a
     suggestion, and how you reach it (what to resize, cut, reflow, or enlarge) is
     your judgment. Your eyes on a shrunk full-poster PNG can mis-read
     a full-bleed figure as "clipped" and miss both real bottom overflow and dead
     whitespace — trust the pixel math over your eyes for anything geometric.
   - **(b) Your own visual read — required, every render.** `Read` the rendered
     `poster.png` yourself and judge hierarchy, density, balance, and readability —
     the subjective read the geometry check can't give you. This is the standing
     "eyes" of the loop. **Caveat:** some harnesses/proxies strip image blocks, so
     `Read` returns empty for a valid image — sanity-check at run start by
     `Read`-ing one small known PNG. If it comes back empty you have no eyes here:
     lean on the deterministic geometry check (a), keep the design conservative, and
     tell the user the visual read was unavailable. Never fake a visual judgment on a
     PNG you couldn't actually see.
   - **(c) Blind-reader content check — at milestones (Step 7).** A good-looking
     poster can still fail to convey the paper. You write questions from the paper,
     then spawn a **blind subagent given only the rendered `poster.png`** (not the
     paper) to answer them — which roles it gets wrong are the roles not landing.
     Run this at milestones (it spawns an agent), not on every micro-edit.

5. **Iterate until it reads like a real poster AND scores well.** Let the three
   checks drive each edit: the geometry check catches overflow/clipping/imbalance
   *and underfill*; your visual read catches weak hierarchy, cramped or sparse
   panels, a bare number used instead of a sentence, poor balance; the blind-reader quiz catches
   content that isn't getting through. When a check flags something, **edit the HTML
   and re-render** — shrink/cut overflowing text, enlarge a figure that reads as a
   thumbnail, fill or merge an empty panel with text, rewrite a number into a claim
   sentence, or move/replace a figure. Re-run the three checks after each edit.
   **Before a big restyle or structural change, snapshot the current render as a
   numbered candidate** (`poster_candN.html` + `poster_candN.png`) with its scores,
   so a regression doesn't destroy a version that read better — iteration isn't
   always monotonic, and you pick the final from the best-scoring candidate, not the
   latest edit. Repeat until the geometry check passes (no overflow **and fill ratio
   ≥ 0.95**), your visual read is clean, and the blind-reader quiz shows the key roles land. **Don't stop the
   moment content stops overflowing** — that only clears the ceiling; verify the
   fill gate too, or you ship a shrunk-down poster full of whitespace. This is open
   visual iteration — your judgment guided by the scores, not a fixed op set.

**Hard constraint (the only one):** every piece of text and every figure label
must be fully visible inside its panel and readable at 1–2 m. No overflow, no
clipping, no text shrunk to illegibility. If content does not fit, cut or
condense it (back in the outline) — never let it spill or shrink to dust.

The final poster is `${RUN_DIR}/poster.png` (+ `poster.html` for editing).

---

## Step 6: Visual read — your own eyes, every render

This is the "eyes" of the iteration loop (Step 5, check b). After each render,
`Read` `${RUN_DIR}/poster.png` yourself and judge it as a poster: visual hierarchy
(does the title / claim / hero dominate?), density (any panel cramped or too
sparse?), balance (columns even? whitespace intentional?), and readability at
1–2 m. Note the top 2–3 issues and let them drive the next edit — exactly the
subjective read the deterministic geometry check can't give you. No external model
needed — this is your own judgment on the rendered PNG.

---

## Step 7: Blind-reader content check — you orchestrate

A good-looking poster can still fail to convey the paper. This is the PaperQuiz
idea (PosterAgent metric, arXiv:2505.21497): its whole value is that the answerer
is **blind** — it sees only the poster, never the paper — so a wrong answer means
*the poster* didn't carry that content. You authored the poster and have the paper
in context, so you **cannot** answer blind yourself (you'd score inflated). Keep the
independence by splitting the roles:

1. **You write the questions** (you know the paper). Draft 5–8 multiple-choice
   questions across `problem` / `method` / `result` / `takeaway` (+ optional
   `contribution` / `limitation`), with distractors pulled from sibling sections so
   wrong options stay plausible. Keep the correct answers to yourself.
2. **A blind subagent answers them.** Spawn one subagent (the `Agent` tool) whose
   context contains **only** the rendered `poster.png` and the questions — **not**
   the paper, digest, or outline. Ask it to answer each (single letter A/B/C/D + a
   one-line "where on the poster I saw it", or `?` if absent). Because it has only
   the poster, its answers measure what the poster actually communicates.
3. **You score by role.** Compare its answers to your key; any role it misses
   (miss rate ≥ 0.5) is content that isn't landing — make that role bigger, clearer,
   or add the missing fact, then re-render.

Run this at milestones (after the poster reads cleanly, and before user preview),
not on every micro-edit — each round spawns an agent. Use it to: drive a repair
round on a failing role; decide if it's good enough to ship (all key roles answered
correctly); and re-rank candidates when you tried more than one layout.

You fix content fidelity by editing the outline / `poster.html` directly.

---

## Step 8: Preview & iterate with the user [INTERACT]

Once your own iteration (Steps 5–7) has the poster reading cleanly and scoring
well, show it to the user:

1. **Get the current design into your context** — `Read` `${RUN_DIR}/poster.png`.
   If image read is unavailable in your harness, rely on the deterministic geometry
   check (Step 5a) and say so when you present.
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
- **Playwright missing**: `pip install playwright && playwright install chromium`. The geometry check (Step 5, check a) and `screenshot.py` both need it.
- **No external VLM / LLM**: this skill calls no vision/LLM API. Figure choice, design, the visual read (Step 6), and the content check (Step 7, blind subagent) are all done by you; the geometry check (Step 5a) is pure pixel math. The only network dependency is MinerU for PDF parsing (Step 1). For a fully offline run, parse the PDF elsewhere and drop `content.md` + `mineru_raw.json` + `figures/` into `parsed/` by hand.

For layout principles see [references/layout_guide.md](references/layout_guide.md) and [references/poster_design_guide.md](references/poster_design_guide.md). For agent-extracted design rules see [references/agent_design_rules_from_posters.md](references/agent_design_rules_from_posters.md).
