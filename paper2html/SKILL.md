---
name: paper2html
description: Convert an academic paper PDF into a publish-ready, self-contained single-page **project homepage** (a self-contained index.html) — the kind of paper landing page researchers host on GitHub Pages. Triggers when the user says "turn a paper into a project page/webpage", "paper2html", "generate a paper landing page / project page", "turn this PDF into an HTML page", "paper to webpage", or "make a paper homepage". A you-led, coordinated skill: the mechanical steps (MinerU parsing + deterministic fact extraction at gate 1 + post-authoring QA at gate 2) call scripts, while **you hand-author index.html yourself** (calling no LLM API), choosing from several design languages.
arguments: [pdf-path]
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - AskUserQuestion
user-invocable: true
disable-model-invocation: false
effort: high
---

# paper2html — Paper to single-page project homepage (you-led, coordinated)

Turn a paper PDF into a **self-contained, publish-ready single-page project website** — the kind of paper
homepage researchers commonly build on GitHub Pages.
**You are the lead author**: this file is the recipe, not a fully automated script — there is no `main.py`,
no renderer. The mechanical steps (parse / extract / QA) call the small tools under `scripts/`; **understanding
the paper, designing the page, and writing `index.html` are done by you** (read the material and figures with
Read, write `index.html` with Write), confirming with the user at key points via `AskUserQuestion`.

```text
PDF
 → parse + extract        (parse_pdf.py: MinerU → clean.md + manifest.json + images/, gate 1)
 → you understand it + set the design   (read manifest + clean.md + look at figures) → pick a design language   [confirm design direction]
 → you hand-author the page   (per the references/ design-language and authoring rules) → index.html            [optional confirm]
 → QA validation          (validate.py: missing figures/broken links/content fidelity, gate 2) → fix per report, loop
 → single-page project homepage index.html (+ images/, deployable as-is)
```

## How you run this skill

1. **Step by step**: run scripts for the mechanical steps via `Bash` (absolute paths, no cd needed); do the design and authoring yourself with `Read`/`Write`.
2. **Compute `WORKDIR` inline at the top of each Bash block** (each Bash call is a separate shell and does not share variables):
   ```bash
   WORKDIR="$(dirname "$pdf_path")/.paper2anything/html/$(basename "${pdf_path%.*}")"
   ```
   `$pdf_path` is the paper PDF the user gave (reset it in each block). The scripts live in `${SKILL_DIR}/scripts` — `SKILL_DIR`
   is **this skill's directory** (see "Base directory for this skill: …" injected at the top of this skill); each Bash block is a
   separate shell, so in the blocks that use it `export SKILL_DIR=<that directory>` once at the top (set it inline each time, like `WORKDIR`).
3. **Pause at decision points with `AskUserQuestion`**: after understanding the paper, confirm the **design direction** (design language / primary color / emphasis); after the draft is done, you may confirm again.
4. **Faithful to the manifest, you fill the gaps**: use only the real material in `manifest.json`, don't fabricate numbers/authors/links; fields the manifest left empty
   (authors/abstract/links etc.) you complete from the full text of `clean.md` — you are the lead author, deterministic extraction is only scaffolding.

---

## Step 0: Environment and credentials

> **Unified environment**: all `python` commands run in paper2anything's unified conda environment (top-level `environment.yml`),
> prefixed with `conda run -n paper2anything --no-capture-output`.

Credentials are centralized in the package-root `.env` (copied from `.env.example`, already gitignored); export it once per new shell:

```bash
set -a; source <paper2anything package root>/.env; set +a
```

This skill **only needs `MINERU_API_TOKEN`** (to parse the PDF). **Page design and authoring are done by you, calling no LLM API**,
so no OPENAI/LLM key is needed.

Dependency self-check:

```bash
conda run -n paper2anything --no-capture-output python -c "import requests, rich, dotenv, playwright, PIL" 2>&1
# render_check.py (Step 4 render self-check) needs the chromium engine; install it once before the first run:
#   conda run -n paper2anything --no-capture-output python -m playwright install chromium
```

---

## Step 1: Parse + deterministic extraction (script, gate 1)

```bash
pdf_path="/path/to/paper.pdf"          # ← the user's paper PDF
WORKDIR="$(dirname "$pdf_path")/.paper2anything/html/$(basename "${pdf_path%.*}")"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/parse_pdf.py" "$pdf_path" --workdir "$WORKDIR"
```

Outputs (under `$WORKDIR`):
- `clean.md` — normalized full-text markdown (for you to read through)
- `manifest.json` — deterministically extracted facts: title/authors/affiliations/abstract/links/claims/figures/tables/
  method_components/bibtex (appendix filtered; fields that couldn't be extracted are left empty for you to fill)
- `images/` — the figure files the page references (figures + result-table screenshots), referenced by you as `images/<name>`
- `parsed/` (MinerU raw parse, includes full.md for reuse on re-run), `logs/`

Optional: when you know the paper's canonical link, add `--paper-url <URL>` (**no arxiv assumption**; if omitted, `links.paper` stays empty); `--code-url` likewise.

After parsing, `Read` `manifest.json` and `clean.md` to read the full text.

---

## Step 2: Understand the paper + set the design direction (you do this) [confirm]

1. `Read` `manifest.json` (verified material) + `clean.md` (full text); `Read` the key figures under `images/` and judge **with your own eyes** which
   one works as the hero, which suit inlining, and which are result-table screenshots.
2. Read `references/design-languages.md` and **establish a design concept** for this paper (pick one design language or blend: magazine/product page/
   terminal/poster/minimal/dashboard; set the primary color, structure, what element leads). Different papers should look different — don't reuse the previous one's style.
3. Use `AskUserQuestion` to confirm the **design direction** with the user (design language / primary color / what to emphasize). Author the page with the confirmation in hand.

Fill the gaps: if the manifest's authors/abstract/links are empty, complete them yourself from the full text of `clean.md` (this is your backstop).

---

## Step 3: Hand-author index.html (you do this) [optional confirm]

Per the confirmed design direction, **author `$WORKDIR/index.html` yourself with `Write`** — a self-contained, deployable single-page website.
**First read `references/html-authoring.md`** (hard constraints and pitfalls). Key points:

- Self-contained: reference images with the relative path `images/<filename>` (from the manifest's `figures[].file` / `tables[].image`, which parse_pdf already copied into
  `images/`); inline CSS or use a CDN; every `<img>` has a non-empty `alt`; leave no `href="#"`.
- Light first screen (title/authors/affiliations/resource buttons), the main figure as a one-time large teaser, then abstract → claims → method → results →
  supporting figures → BibTeX (adjust to the paper's character, not mandatory).
- For result tables, **prefer screenshots** (`tables[].image`).
- **figure CSS: don't let the border frame whitespace, and never stretch the image to fill whitespace** (details in references/html-authoring.md).
- Faithful to the manifest, no fabrication; fill gaps from the full text.

After writing, you may use `AskUserQuestion` to show the user the design and structure (optional), and edit `index.html` directly per their feedback.

---

## Step 4: QA validation and revision (script, gate 2)

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/html/$(basename "${pdf_path%.*}")"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/validate.py" --workdir "$WORKDIR"
```

Validates the `index.html` you wrote → `validation.json` + `qa_report.md`. `Read` `qa_report.md`:
- **Errors must be cleared to zero** (missing doctype/`</html>`, a referenced `images/<x>` missing, empty `href="#"`).
- **Fix warnings as needed** (title/figure/table not present on the page, claims<3, empty alt, etc.).
Fixes are in `references/qa-checklist.md`. After fixing `index.html`, **re-run validate**, looping until errors are zero and warnings acceptable.

`validate.py` only checks static text and **can't catch render-layer visual issues** (distorted/broken figures, horizontal overflow, MathJax not rendering).
Run the render self-check too (the "post-render self-check" rule from html-authoring.md, now run as a script):

```bash
# Desktop width + mobile width must both pass — mobile most easily exposes horizontal overflow / clipped wide tables / overflowing long formulas
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/render_check.py" "$WORKDIR/index.html" 1200
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/render_check.py" "$WORKDIR/index.html" 390
```

Exit code 0=pass, 1=fail; the output JSON lists `distorted_images` (rendered vs natural aspect ratio differs by >0.02),
`broken_images`, `h_overflow_px`, `clipped_content` (wide tables/blocks clipped inside an overflow:hidden box and unscrollable),
`mathjax.fail` (leftover unrendered `$…$`/`$$…$$`), `upscaled_images_warn`.
**The hard metrics at both widths must be zero** (upscaling is a soft warning, judge it yourself); if it doesn't pass, edit `index.html` and re-run.

---

## Step 5: Collect the deliverable next to the PDF

By default the deliverable is buried under `.paper2anything/html/<stem>/` and hard to find. Once final, copy it to a
`<stem>_html/` directory **next to the PDF** (keep the copy inside `.paper2anything` untouched), so the user can open it right beside the paper:

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/html/$(basename "${pdf_path%.*}")"
DEST="${pdf_path%.*}_html"            # same dir as the PDF, same name + _html suffix
i=2; while [ -e "$DEST" ]; do DEST="${pdf_path%.*}_html_v$i"; i=$((i+1)); done   # on name clash, append _v2, _v3
mkdir -p "$DEST"
cp "$WORKDIR/index.html" "$DEST/"
cp -r "$WORKDIR/images" "$DEST/"      # index.html references images/<file> relatively, so it must come along
```

`index.html` is a single-page site referencing `images/`, so put the whole bundle into the `<stem>_html/` subdirectory and the references stay intact;
open `<stem>_html/index.html` for the final homepage.

---

## Deliverable locations

Intermediate artifacts land next to the paper at `<pdf-dir>/.paper2anything/html/<stem>/` (multiple papers in one directory are split by `<stem>`, never overwriting), and **the final deliverable is additionally copied to `<stem>_html/` next to the PDF** (Step 5):

| Path | Contents | Who writes it |
|---|---|---|
| `.paper2anything/html/<stem>/clean.md` | normalized full-text markdown | parse_pdf |
| `.paper2anything/html/<stem>/manifest.json` | deterministically extracted facts (gate 1) | parse_pdf |
| `.paper2anything/html/<stem>/images/` | figures + result-table screenshots the page references | parse_pdf |
| `.paper2anything/html/<stem>/index.html` | self-contained single-page project homepage | **you** |
| `.paper2anything/html/<stem>/validation.json` `qa_report.md` | QA results (gate 2) | validate |
| `.paper2anything/html/<stem>/parsed/` `logs/` | MinerU raw parse / per-step *_result.json | scripts |
| **`<pdf-dir>/<stem>_html/`** | **collected deliverable**: `index.html` + `images/`, next to the PDF, opens directly | **you (Step 5)** |

Re-running overwrites the workspace `.paper2anything/html/<stem>/` (intermediate artifacts); the collect step saves to `_v2`, `_v3` on a `<stem>_html/` name clash, never overwriting an old deliverable. A Step 1 re-run reuses `parsed/full.md` by default and skips the MinerU cloud parse.

---

## Troubleshooting

- **MinerU parse fails**: check `MINERU_API_TOKEN`; PDF ≤200MB / ≤200 pages; can reach `mineru.net`. Re-run Step 1 (overwrites).
- **manifest fields empty (authors/abstract/links)**: a limit of deterministic extraction (e.g. the paper has no `## Abstract` heading, or a non-arxiv paper has no link) —
  **normal**, complete them yourself from the full text of `clean.md`; not a bug.
- **QA reports missing figures**: only reference files that really exist under `images/`, copy the filename from the manifest, don't mistype the hash name.
- **Design/authoring needs no API key**: those two steps are done by you, calling no LLM API.

---

## references/

- `design-languages.md` — six design languages + concept-before-layout + real academic-homepage exemplars.
- `html-authoring.md` — authoring hard constraints, figure CSS pitfalls, self-contained/deployable, table strategy.
- `qa-checklist.md` — what each QA check means and how to fix it.
