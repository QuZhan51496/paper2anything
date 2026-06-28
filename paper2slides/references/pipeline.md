# Pipeline Protocol

Detailed execution protocol for the six stages. This file is more detailed than the
SKILL.md Quick Reference — SKILL.md is the index, this file is the manual.

## General Conventions

- **Python environment**: all `python` commands run in the `paper2anything` conda
  environment by default. When executing inside Claude Code, use it explicitly:

  ```bash
  conda run -n paper2anything --no-capture-output python -m scripts.<name> ...
  ```

  For brevity the prefix is omitted below, but every command implies this prefix.

- **Work directory**: all stages share `<paper-dir>/.paper2anything/slides/<paper-stem>/`,
  with the path resolved by `scripts/workdir.py resolve <paper.pdf>`. **Do not assemble
  paths by hand** — the rules are centralized in workdir.py.

- **Re-run**: by default uses "skip if the output file exists" semantics; `--from-stage <name>`
  forces a full run starting from a given stage, `--force` re-runs everything. `config.json`
  (the Stage 0.5 output) follows the same semantics — if it already exists, the questions are
  skipped and the last configuration is reused; `--from-stage configure` asks again.

- **Failure handling**: when a script errors, stderr gives a diagnostic; locate the problem
  from it, do not blindly retry.

---

## Stage 0: Resolve workspace (prerequisite that must run every time)

```bash
python -m scripts.workdir resolve <paper.pdf> [--output <out.pptx>] --ensure
```

The output JSON contains: `paper_path` / `output_path` / `workdir` / the path of each output /
each stage's `stage_status`.

**Your responsibility**: read this JSON and decide which stages are done and which need to run.
All subsequent commands reference the paths given here; do not concatenate strings.

---

## Stage 0.5: Configure (user dialogue → config.json)

**No script**. Using the [AskUserQuestion] tool, after Stage 0 and before Stage 1 you confirm
three key parameters with the user, then write the answers with the Write tool to the
`config_path` given by the Stage 0 JSON
(`<workdir>/config.json`; for the schema see [schemas.md](schemas.md#configjson-stage-05-artifact-stage-2-and-stage-5-input)).

**Input**: user dialogue (+ preferences already expressed in the user's initial request)

**Output**: `workdir/config.json`

**Completion criterion**: `config.json` exists (`stage_status.configure == true`).

### The three confirmations

| # | Field | Options | Default/recommended |
|---|---|---|---|
| 1 | `deck_length` | `concise` ~8–12 slides (10 min short talk / quick group-meeting run-through) / `standard` ~13–18 slides (12–20 min conference talk) / `detailed` ~19–28 slides (30–45 min keynote/job talk) / `auto` no slide-count target, decided by narrative + layout | default `auto`; `auto` fully preserves the recent "no upper/lower bound on slide count" philosophy |
| 2 | `visual_qa` | `true` runs the soffice→jpg→subagent visual loop / `false` runs only the cheap content QA | **default `true`** (use visual QA); note that it is expensive (token/time nearly the sum of all preceding stages combined), choose `false` when you do not need it to save cost |
| 3 | `color_scheme` | `auto` lets Stage 3 choose the palette by the paper's character / `custom` the user describes a color-scheme preference in one sentence, written into config | **default `auto`**; custom only stores the user's original wording, parsed and mapped by Stage 3; this stage does not settle on a specific palette |

### What to write in config.json

```json
{
  "schema_version": "0.1",
  "deck_length": "standard",
  "deck_length_target": [13, 18],
  "visual_qa": true,
  "color_scheme": null
}
```

- `deck_length_target`: `concise`→`[8,12]`, `standard`→`[13,18]`, `detailed`→`[19,28]`,
  `auto`→`null`. Downstream only needs to read this range (`null` = no constraint).
- `color_scheme`: choosing `auto` writes `null`; choosing `custom` stores the user's original wording as a string. Stage 3 chooses the palette from this; this stage does not parse it and does not fix a specific palette.
- For the full field semantics, see [schemas.md](schemas.md#configjson-stage-05-artifact-stage-2-and-stage-5-input).

### Reuse and reconfigure

- **Skip the questions**: when `config.json` already exists and neither `--from-stage configure`
  nor `--force` is passed, do not ask again; reuse the last configuration (consistent with other
  stages' "skip if the output exists").
- **Reconfigure**: `--from-stage configure` (overwrites the old `config.json`, and because configure
  is at the front of STAGES, all subsequent stages re-run as well).
- **Pre-fill**: when the user's initial request has already expressed a preference ("make a concise one" /
  "a detailed keynote" / "do visual QA while you're at it"), set the corresponding item as the
  AskUserQuestion preferred option — still show the confirmation, do not silently decide for the user.

### Downstream consumption

`deck_length_target` → **Stage 2** (soft target for outline granularity), `color_scheme` → **Stage 3**
(choose the palette), `visual_qa` → **Stage 5** (visual QA switch). For each field's semantics and
consumption details, see the "consumers" part of
[schemas.md](schemas.md#configjson-stage-05-artifact-stage-2-and-stage-5-input).

---

## Stage 1: Extract (PDF → MinerU cloud parse → metadata + figures + full-page render)

Parsing always goes through the **MinerU cloud API**: upload the PDF to mineru.net, and after the
cloud parses it, download the result. `MINERU_API_TOKEN` (in the package-root `.env`) is required;
with no token or on a parse failure it **errors out directly**.

```bash
python -m scripts.parse_pdf <paper.pdf> [--dpi 300]
```

**Input**: `<paper.pdf>` (absolute path or relative to the current working directory)

**Output** (written to workdir, by `lib/mineru_parser`):

| Output | Content |
|---|---|
| `paper_meta.json` | title / authors / sections / figures / tables / equations / references_count (structured metadata, provided directly by MinerU) |
| `figures_index.json` | lists such as captions (figure/table captions; tables carry `bbox` + `bbox_source: mineru:vlm`), figures, page_renders |
| `figures/` | figure/table entities extracted by MinerU and high-resolution crops (table high-resolution crops also land in `figures/`; there is no separate `tables/` directory) |
| `pages/page-NN.png` | pdftoppm full-page render, **300 dpi by default, with `-hide-annotations`** (removes the green hyperlink boxes the PDF carries); `--dpi 200` to reduce load, `--dpi 400` for fine equations |

**Completion criterion**: `paper_meta.json` + `figures_index.json` exist.

**Known imperfections**:

- A table/figure `bbox` occasionally puts the `y` start on a subfigure title / caption line → the first
  cut clips the title or pulls in the caption; per [design-style.md](design-style.md) §3, make a directed
  micro-adjustment to that one edge on the original box — do not discard the original box and re-estimate.
- For some papers MinerU may still extract title/authors incompletely → before entering Stage 2,
  **you must run** [the 4 checks at the end of schemas.md](schemas.md#revisions-you-should-make-before-entering-stage-2)
  (title / authors / merge same-kind / missing key kind) to verify `paper_meta.json`; **the check results
  are not written back to `paper_meta.json`**, they are reflected directly in the outline.

**When to re-run**: switching papers, the PDF changed, or you want a different `--dpi`.

---

## Stage 2: Outline (paper metadata → slide outline)

**No script**. This is your job.

**Input**: `workdir/paper_meta.json` (read-only) + `workdir/figures_index.json`
+ `workdir/config.json` (read-only)

**Output**: `workdir/slide_outline.json` (for the schema see [schemas.md](schemas.md))

**Protocol**:

1. Read `paper_meta.json` and `figures_index.json`; read `config.json/deck_length_target`
2. Run the 4 checks at the end of [schemas.md](schemas.md) (title / authors / merge same-kind / missing kind)
3. Per [outline-heuristics.md](outline-heuristics.md), decide slide roles and order:
   when `deck_length_target == null` (`auto`), the slide count is decided purely by narrative + layout;
   when not `null`, treat that range as a **soft target for outline granularity** (tune method/result
   split granularity and whether optional roles are included), **do not** cut core narrative roles to
   hit a number, **do not** change each slide's "space-driven, no whitespace no overflow"
4. For each slide write `title` / `bullets` / `figure_ref` / `speaker_notes` / `source_section_ids`
5. Serialize the result to `workdir/slide_outline.json`; you must run `python -c "import json; json.load(open(...))"`
   to verify the JSON is valid

**Completion criterion**: `slide_outline.json` exists and is schema-valid.

**Common Stage 2 mistakes**:

- Copying the paper abstract directly as bullets (violates the distillation principle — a bullet is a key point, not a transcription)
- Cramming all method details into a single method slide
- Bullets missing a subject + missing a verb, all noun phrases
- speaker_notes written as an expansion of the bullets (they should be the speaker's spoken-delivery script)

---

## Stage 3: Spec (slide outline → render spec)

**No script**. Your work.

**Input**: `workdir/slide_outline.json` + `workdir/figures_index.json` + various PNGs

**Output**: `workdir/slide_spec.json` (for the schema see [schemas.md](schemas.md))

**Protocol**:

1. Read `slide_outline.json`
2. Per [design-style.md](design-style.md), choose the palette and font_header/body
3. For each slide choose a `layout_kind` (avoid the same layout in a row)
4. Translate `title` / `bullets` / figures / shapes/lines etc. into the `elements` array; use inches for coordinates
5. For figures: if `figure_ref` is given, first look up `figures_index.json/captions[].id == figure_ref`
   to find the page; then decide whether to use `figures/<id>.png` (the MinerU high-resolution crop) or the
   full page from `page_renders` (when necessary, `scripts/page_screenshot.py` crops the bbox)
6. Serialize, validate the JSON

**Key constraints** (these are the points where Stage 3 most easily goes wrong):

- `slide.id` stays consistent with `slide_outline.json`
- Element coordinates + size ≤ slide size (10 × 5.625 for 16:9)
- The `text` field of text elements: **every number and term must have a source in paper_meta or figures_index**
  (do not hallucinate numbers that are not in the paper)
- Figure paths: relative to workdir, and the file actually exists
- `margin: 0` on text elements must be added when aligning to a shape/icon (PptxGenJS's default margin causes an offset)

**Completion criterion**: `slide_spec.json` exists and is schema-valid.

---

## Stage 4: Render (spec → .pptx)

```bash
python -m scripts.render_pptx <slide_spec.json> <output.pptx>
```

**Input**: `workdir/slide_spec.json`

**Output**: `workdir/output.pptx` (lands in workdir first), then copied by the caller to the final `output_path`

**Mechanism**: `render_pptx.py` translates `slide_spec.json` into a PptxGenJS `.js` program,
saves it to `workdir/render/build.js`, then `node` produces the `.pptx`.

**Prerequisites**:

- `node` is on PATH
- `pptxgenjs` has been `npm install -g`'d (or, after a local `npm install`, `NODE_PATH` points to it)
- icon elements additionally need `npm install -g react-icons react react-dom sharp` (when missing, icons warn+skip, without blocking the render)

**Completion criterion**: `workdir/output.pptx` exists and has ≥ N slides (N == `slide_spec.json/slides.length`).

**Common Stage 4 mistakes**:

- Misspelled font name (PptxGenJS does not error; the pptx falls back to the default font when opened)
- Image path relative to workdir but render_pptx.py does not resolve it correctly (render_pptx.py passes workdir
  as an argument to node, and the JS side uses `path.join(workdir, path)` to build an absolute path)
- Wrong z-order on a shape (a background shape ends up in the foreground and covers the text)

---

## Stage 5: QA

**Apply the Verification Loop in [qa.md](qa.md)** — the deck-QA protocol and the visual-subagent prompt
template live there in full; this section adds only the paper-pipeline specifics (the `<workdir>/qa/`
artifact convention and the `qa_log.json` structure). **First read `config.json/visual_qa`**, then follow its flow:

### A. Content QA — always runs

1. `python -m markitdown <workdir>/output.pptx`, grep "lorem|xxxx|placeholder|TODO"
2. **Additional items** (special checks for paper decks):
   - Number consistency: every number in a stat callout has a source in paper_meta or figures_index
   - bullets are not a copy-paste of the paper abstract
   - the title slide has no leftover "YOUR TITLE HERE"

### B. Visual QA — runs only when `config.json/visual_qa == true`

3. `soffice --headless --convert-to pdf <workdir>/output.pptx --outdir <workdir>/qa/` →
   `pdftoppm -jpeg -r 150 <workdir>/qa/output.pdf <workdir>/qa/slide` → dispatch **a single** subagent
   to review multiple pages in batch (a single subagent, not one per page), using the visual-subagent
   prompt template in [qa.md](qa.md) §B.2 to visually check `<workdir>/qa/slide-*.jpg` (for the prompt's two
   added paragraphs + re-check round scope see the end of [design-style.md](design-style.md))

> When `visual_qa == false`, **the entire section B is skipped** — no PDF/JPG is generated, no subagent
> is dispatched. This is the user's explicit choice at Stage 0.5 based on "expensive and of limited
> marginal value", not an omission. `qa_log.json` records `"visual_qa": false`, and **the final report
> must clearly state "visual QA was skipped per config; to change the configuration, re-run with
> `--from-stage configure` and then `--from-stage qa`"**.

**When B runs, all intermediate outputs (PDF + JPG) go uniformly into `<workdir>/qa/`** — do not write to
`<workdir>/render/`, `/tmp/`, or the `<workdir>` root. That directory is created automatically by
`workdir.py` during `ensure()`; for the absolute path use the `qa_dir` field of the JSON output by
`python -m scripts.workdir resolve <paper.pdf>`.

4. **Fix issues**: change the corresponding field in `slide_spec.json`, **do not edit the .pptx directly**
5. Re-run Stage 4 (`--from-stage render` for a full re-render) → QA again, until there are no new findings.
   **For re-check rounds, narrow the subagent scope per the [Verification Loop](qa.md)** (round 1 is full;
   from round 2 on, only review last round's flagged ∪ this round's spec-changed pages; the final round is
   a full pass as a fallback), the criteria are unchanged; for details see the "QA issue-fixing principles"
   step 5 in [design-style.md](design-style.md)

**Completion criterion**: write a `qa_log.json` with the structure:

```json
{
  "visual_qa": true,
  "rounds": [
    {"timestamp": "2026-04-26T15:00:00Z",
     "issues": ["..."], "fixed": ["..."], "pass": false},
    {"timestamp": "2026-04-26T15:15:00Z",
     "issues": [], "fixed": [], "pass": true}
  ]
}
```

The last round with `pass: true` is treated as pipeline completion. Copy (or rename) `workdir/output.pptx`
to the final `output_path` given by the workspace.

---

## Error-Recovery Quick Reference

| Symptom | Most likely root cause | Action |
|---|---|---|
| Stage 1 MinerU parse failure / timeout | token expired / network / PDF too large | verify `MINERU_API_TOKEN`, that mineru.net is reachable; PDF ≤200MB/200 pages; re-run |
| `paper_meta.json` section count < 5 | MinerU section segmentation incomplete | you fill it in manually during the Stage 2 checks |
| `paper_meta.json` section count > 15 | subsections too granular | check paper_meta.json/sections, merge them yourself |
| Stage 3 references a figure that does not exist | figure_ref is wrong | check figures_index.json/captions, fix figure_ref or switch to page_renders |
| Stage 4 PptxGenJS reports image not found | path relative to workdir but node's working directory is wrong | render_pptx.py passes workdir as an argument to node, and the JS side builds an absolute path |
| Stage 5 visual QA reports "lorem ipsum leftover" | you used a placeholder in Stage 3 | fix the corresponding text in slide_spec.json, re-run from render |
| Stage 5 reports "table bottom line is clipped" / "the crop pulls in the body text below" | bbox too tight / your visual estimate is off | `page_screenshot.py` already adds +0.005 padding by default; if it still drops content, manually increase `--pad 0.01`; prefer `figures_index.json/captions[i].bbox` (detected by mineru) |
| Stage 5 reports "a green rectangle box appears on a `[N]` citation inside a table/figure" | pdftoppm by default renders the hyperlink annotation the PDF carries | parse_pdf.py already defaults to `-hide-annotations`; if it still appears, the machine's poppler is too old (< 0.69), upgrade or `apt install -y poppler-utils` |
| Stage 5 reports "figure/table text is blurry" | dpi too low | already 300 dpi by default; if you lowered to `--dpi 200` for a very long paper and it is not clear enough, restore 300 or raise to `--dpi 400` |
