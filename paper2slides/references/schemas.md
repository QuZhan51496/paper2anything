# JSON Schemas

The schema definitions for paper2slides' per-stage artifacts. Every JSON file carries a `schema_version`
field; this file describes version `0.1`.

## Common conventions

- Encoding: UTF-8, 2-space indentation
- Field-absence policy: optional fields are written as `null` or omitted; a missing required field is treated as a pipeline error
- Path fields: relative to workdir (unless the field name carries `_absolute`). For example `embedded_path`
  looks like `figures/fig-001.png`, counted from `<paper-dir>/.paper2anything/slides/<paper-stem>/`
- Stage-artifact file names are fixed (see `STAGE_MARKERS` in `scripts/workdir.py`); do not rename them

---

## config.json (Stage 0.5 artifact; Stage 2 and Stage 5 input)

Stage 0.5 confirms three items with the user via AskUserQuestion, then you write it out. It lands at the workdir root
(the `config_path` field, see `STAGE_MARKERS["configure"]` in `workdir.py`).

```json
{
  "schema_version": "0.1",
  "deck_length": "standard",
  "deck_length_target": [13, 18],
  "visual_qa": true,
  "color_scheme": null
}
```

| Field | Type | Required | Description |
|---|---|:-:|---|
| `schema_version` | string | yes | fixed `"0.1"` |
| `deck_length` | string | yes | one of `concise` / `standard` / `detailed` / `auto` |
| `deck_length_target` | `[int,int]` \| null | yes | soft target range for page count. `concise`→`[8,12]`, `standard`→`[13,18]`, `detailed`→`[19,28]`, `auto`→`null`. Downstream reads only this; `null` = no constraint on slide count |
| `visual_qa` | bool | yes | `true` (default) runs Stage 5's visual QA (soffice→jpg→subagent); `false` runs only content QA |
| `color_scheme` | string \| null | yes | `null` (default, "auto") = Stage 3 auto-selects a palette to match the paper's character; a string = the user's description of the color scheme, against which Stage 3 maps/constrains the palette selection |

**Consumers**:

- **Stage 2** reads `deck_length_target`: when `null`, slide count is driven purely by narrative + layout; when non-`null`,
  it acts as a soft target for outline granularity (see the page-count tier section of [outline-heuristics.md](outline-heuristics.md)).
  It is **not** a per-slide word-count cap, and does **not** change each slide's "space-driven" nature.
- **Stage 3** reads `color_scheme`: when `null`, auto-selects a palette to match the paper's character; when non-`null`, treats
  the user's description as a constraint. For the rules of selecting/creating a palette, see [design-style.md](design-style.md).
- **Stage 5** reads `visual_qa`: when `false`, skips visual QA and records
  `"visual_qa": false` in `qa_log.json`.

> `schema_version` stays `"0.1"`: config.json is a standalone configuration artifact, parallel to the per-stage artifact schemas;
> when the workdir lacks this file, Stage 0.5 regenerates it (equivalent to "unconfigured", using defaults).

---

## paper_meta.json (Stage 1 artifact; Stage 2-3 input)

```json
{
  "schema_version": "0.1",
  "source_pdf": "absolute/path/to/paper.pdf",
  "title": "string",
  "authors": ["string", ...],
  "venue": "string|null",
  "year": "int|null",
  "abstract": "string",
  "sections": [
    {
      "id": "intro",
      "kind": "introduction",
      "title": "1 Introduction",
      "page_start": 1,
      "page_end": 2,
      "text": "section body, with PAGE separators stripped",
      "subsections": []
    }
  ],
  "figures": [
    {"id": "figure1", "kind": "figure", "num": 1, "page": 3, "caption": "..."}
  ],
  "tables": [
    {"id": "table1", "kind": "table",  "num": 1, "page": 6, "caption": "..."}
  ],
  "references_count": 42
}
```

Field details:

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | currently fixed `"0.1"` |
| `source_pdf` | string | yes | absolute path of the source PDF |
| `title` | string | yes | paper title. Heuristically extracted by the script, **you must verify it in Stage 2** — the first page often has license/watermark noise |
| `authors` | string[] | no | heuristically extracted, may be incomplete; fill in as needed when you spot gaps |
| `venue` / `year` | string\|null / int\|null | no | not extracted for now (the script is unreliable); judge it from the original text or leave it empty |
| `abstract` | string | no | the heuristically extracted abstract paragraph, may contain hyphenation and line-break contamination |
| `sections[]` | array | yes | heuristic segmentation result. **In Stage 2 you revise the boundaries**: merge mis-split subsections, drop obvious errors |
| `sections[].kind` | enum | yes | see the `kind` enum below |
| `sections[].text` | string | yes | section body (PAGE separators already stripped) |
| `sections[].subsections` | array | yes | always an empty array for now; subsections may be filled in later |
| `figures[]` / `tables[]` | array | no | filtered-and-copied from `figures_index.json`'s `captions` by `kind`; when a caption carries `bbox` / `bbox_source` / `bbox_confidence` fields, they are inherited along with it |
| `references_count` | int | no | estimated value (counted by `[1] [2] ...` or `1. 2. ...`) |

`sections[].kind` enum:

```
abstract | introduction | background | related | method | experiment |
result | discussion | conclusion | references | other
```

### Revisions you should make before entering Stage 2

After reading `paper_meta.json`, **first** do the following checks (do not skip):

1. Is `title` reasonable? Common error: it grabbed a license watermark ("Provided proper attribution...")
   or junk characters. If unreasonable, find the real title in `sections[0].text` or the PDF's first-page text
2. Is `authors` empty or clearly misplaced? Identify them manually from the first-page text when necessary
3. Multiple sections with the same `kind` (e.g. two `method`s) — do they represent genuinely multiple independent method sections, or one that got chopped up?
   Just merge the chopped-up ones (keep `id`/`title`, concatenate the `text`, take the latter's `page_end`)
4. Missing a key kind? (Most papers should at least have `method` + `experiment` + `conclusion`; when incomplete,
   go to `sections[].text` and check whether the script missed it)

After checking, you do **not** need to write back to `paper_meta.json`; generate `slide_outline.json` directly based on your post-check understanding.

---

## slide_outline.json (Stage 2 artifact; Stage 3 input)

```json
{
  "schema_version": "0.1",
  "deck_title": "string",
  "audience": "researchers",
  "slides": [
    {
      "id": "s01",
      "role": "title",
      "title": "Attention Is All You Need",
      "bullets": [],
      "needs_figure": false,
      "figure_ref": null,
      "source_section_ids": [],
      "speaker_notes": "1-2 sentences a presenter would say"
    }
  ]
}
```

Field details:

| Field | Type | Required | Description |
|---|---|---|---|
| `deck_title` | string | yes | usually equals the paper title; you may swap in a shorter presentation version |
| `audience` | enum | yes | `researchers` / `general` / `mixed`, affects bullet granularity and terminology |
| `slides[].id` | string | yes | `s01`, `s02`, ... (two-digit index for easy sorting) |
| `slides[].role` | enum | yes | see below |
| `slides[].title` | string | yes | short phrase; does not repeat deck_title |
| `slides[].bullets` | string[] | yes | distilled key points (not whole paragraphs moved over); count and length are determined by layout filling, see [outline-heuristics.md](outline-heuristics.md); title slide etc. may be empty |
| `slides[].needs_figure` | bool | yes | whether a paper figure is needed (method/result are usually true). **=false does not mean no visual** — every slide must have a visual element, which Stage 3 carries via icon/shape/chart etc. |
| `slides[].figure_ref` | string\|null | yes | references `paper_meta.json/figures[].id` (e.g. `"figure2"`), or `null` |
| `slides[].equation_ref` | string\|null | no | references `paper_meta.json/equations[].id` (e.g. `"eq_5"`), or omitted/`null`; parallel to `figure_ref` |
| `slides[].source_section_ids` | string[] | yes | which paper sections provided the content (for traceability) |
| `slides[].speaker_notes` | string | yes | 1–3 sentences, for the presenter |

`slides[].role` enum (this file defines only the **legal values**):

```
title | tldr | motivation | background | method | experiment |
result | discussion | conclusion | qna
```

> **Each role's required-ness, typical order, paper section→role mapping, and per-role content guide** are all
> Stage 2 heuristics, with the **single authority in [outline-heuristics.md](outline-heuristics.md)**
> (the three sections "role → required-ness and order" / "paper section → slide role mapping" / "per-role content
> guide"). This file does not restate them, to avoid drift.

---

## slide_spec.json (Stage 3 artifact; Stage 4 input)

```json
{
  "schema_version": "0.1",
  "engine": "pptxgenjs",
  "template_path": null,
  "layout": "LAYOUT_16x9",
  "theme": {
    "palette_name": "Midnight Executive",
    "primary": "#1E2761",
    "secondary": "#CADCFC",
    "accent": "#FFFFFF",
    "background": "#FFFFFF",
    "font_header": "Georgia",
    "font_body": "Calibri"
  },
  "slides": [
    {
      "id": "s01",
      "layout_kind": "title",
      "elements": [
        {"kind": "text", "role": "title",
         "text": "Attention Is All You Need",
         "x": 0.5, "y": 2.0, "w": 9.0, "h": 1.2,
         "fontFace": "Georgia", "fontSize": 44, "bold": true,
         "color": "#FFFFFF", "align": "left", "valign": "middle"},
        {"kind": "shape", "shape": "rect",
         "x": 0, "y": 0, "w": 10, "h": 5.625,
         "fill": "#1E2761", "z": -1}
      ],
      "speaker_notes": "..."
    }
  ]
}
```

Field details:

| Field | Type | Required | Description |
|---|---|---|---|
| `engine` | enum | yes | fixed `"pptxgenjs"` for now; `"template"` will appear later |
| `template_path` | string\|null | yes | only meaningful when `engine == "template"`; currently fixed `null` |
| `layout` | enum | yes | `LAYOUT_16x9` / `LAYOUT_16x10` / `LAYOUT_4x3` / `LAYOUT_WIDE`, default `LAYOUT_16x9` |
| `theme.palette_name` | string | yes | references a named palette from the table in [design-style.md](design-style.md) (e.g. `Midnight Executive`) |
| `theme.primary/secondary/accent/background` | hex | yes | 6-digit hex colors, paired with palette_name |
| `theme.font_header/font_body` | string | yes | see the font-pairing suggestions in [design-style.md](design-style.md) |
| `slides[].layout_kind` | enum | yes | see below |
| `slides[].elements` | array | yes | one object per element; five kinds: `text` / `image` / `shape` / `line` / `icon` |

`layout_kind` enum (the deck layouts from [design-style.md](design-style.md) + `title` added for the paper scenario):

```
title | two_column | icon_rows | image_half_bleed | stat_callout | grid_2x2 | comparison_columns
```

### Element substructure

**text**:

```json
{"kind": "text", "role": "title|body|caption|footer",
 "text": "string or rich-array",
 "x": 0.5, "y": 0.5, "w": 9, "h": 1,
 "fontFace": "Calibri", "fontSize": 24, "bold": false, "italic": false,
 "color": "#363636", "align": "left|center|right",
 "valign": "top|middle|bottom",
 "bullet": false, "margin": 0}
```

`text` can be a string, or a PptxGenJS rich-text array (multiple segments with different styles).
`bullet: true` together with `breakLine` is handled automatically by the renderer during the PptxGenJS call, but
**do not use it for paper decks** — PptxGenJS's default round bullets are too ugly; use a standalone `kind:"icon"`
element as the leading marker instead, see "Visual richness suggestion A" in [design-style.md](design-style.md).

**image**:

```json
{"kind": "image",
 "path": "figures/fig-04.png",   // relative to workdir
 "x": 5, "y": 1.5, "w": 4.5, "h": 3.5,
 "sizing": {"type": "contain", "w": 4.5, "h": 3.5}}
```

`sizing` may be omitted — the render side uses PIL to scale by the original aspect ratio and center (see [design-style.md](design-style.md) §0.3); it will not distort whether or not you write it.

**shape**:

```json
{"kind": "shape", "shape": "rect|oval|line|rounded_rect",
 "x": 0, "y": 0, "w": 10, "h": 0.3,
 "fill": "#1E2761", "line_color": "#000000", "line_width": 0,
 "rectRadius": 0.1,
 "transparency": 0,
 "z": 0}
```

`z` controls stacking (negative goes to the bottom, positive to the top). `render_pptx.py` draws in ascending `z` order.

**line**:

```json
{"kind": "line",
 "x": 1, "y": 3, "w": 5, "h": 0,
 "color": "#FF0000", "width": 3, "dashType": "solid|dash|dot"}
```

**icon**:

```json
{"kind": "icon",
 "icon": "FaChartLine",   // react-icons export name, PascalCase, with library prefix (Fa/Md/Hi/Bi)
 "lib": "fa",             // fa|md|hi|bi (defaults to fa)
 "color": "#1E2761",      // ⚠️ must include #: the CSS color value goes straight into react-icons; writing "1E2761" silently renders black
 "iconSize": 256,         // optional; raster resolution, not display size (display is set by w/h; ≥256 recommended)
 "x": 1, "y": 1, "w": 0.5, "h": 0.5, "z": 0}
```

The icon is rasterized live to PNG in Stage 4 via react-icons → SVG → sharp and embedded, **without writing to disk**.
Difference from `image`: `image` goes through the on-disk `path` and is scaled-to-fit and centered by `render_pptx.py`;
`icon` is already a square vector raster, does not enter `_normalize_image_boxes`, and its `w/h` take effect directly (use equal values such as `0.5×0.5`).
When a dependency is missing / the `icon` name is misspelled / rasterization fails, that icon auto warn+skips without blocking the whole deck.
For legal icon names and the naming pattern, see the "Icons" section of [pptxgenjs.md](pptxgenjs.md).

> **Color format (critical, easiest to trip on)**: `icon.color` follows the **opposite** rule from shape/text/line color.
> shape/text/line color values go through `render_pptx.py`'s `clean()` which strips `#`, so with or without `#` both work;
> but `icon.color` is **passed to react-icons as a CSS value as-is**, and **must include `#`** (e.g. `#1E2761`).
> A missing `#` raises no error — react-icons falls back to **black** (on a dark background = invisible). **Mnemonic: shape/text/line without `#`, icon with `#`.**
> See [pptxgenjs.md](pptxgenjs.md) Common Pitfalls #1 for details.

### Coordinates and units

- Unit: inches (PptxGenJS convention)
- `LAYOUT_16x9` work area: 10" × 5.625"
- Safe margin: ≥ 0.5", to avoid content touching the edge
- Element spacing: 0.3–0.5", uniform gaps to avoid a random look

For the design-aesthetics spec (avoiding AI-tell "title underlines" etc.), see [design-style.md](design-style.md).

---

## figures_index.json (Stage 1 artifact; not itself a stage marker, but read by both Stage 2 and Stage 3)

```json
{
  "schema_version": "0.1",
  "source_pdf": "absolute/path",
  "n_pages": 15,
  "captions": [
    {"id": "figure1", "kind": "figure|table", "num": 1,
     "page": 3, "caption": "string"},
    {"id": "table3", "kind": "table", "num": 3, "page": 9,
     "caption": "...",
     "bbox": [0.229, 0.164, 0.420, 0.321],
     "bbox_source": "mineru:vlm",
     "bbox_confidence": "high"}
  ],
  "page_renders": [
    {"page": 1, "path": "pages/page-1.png"}
  ]
}
```

> Figure entities are written by MinerU into `figures/`. When a figure is a vector graphic in the original and has no clear entity in `figures/`,
> fall back to cropping the same-page PNG from `page_renders` (provided by `scripts/page_screenshot.py`).

### `captions[].bbox` (both figure and table may have it)

When parsing, MinerU attaches a bbox to each detected figure / table region; for those matched to a caption, the bbox is written onto that caption
(the "first cut" coordinates of Stage 4's crop hard-gate are taken value-by-value from this; field absent = not located):

| Field | Meaning |
|---|---|
| `bbox` | 4-element array `[x, y, w, h]`, **relative to the page 0..1, top-origin** — consistent with the `page_screenshot.py` interface |
| `bbox_source` | `"mineru:vlm"` — source identifier |
| `bbox_confidence` | `"high"` / `"medium"` etc. |

**Field-absence semantics**: when a table caption has no `bbox` field (i.e. `bbox not in caption`), it means
MinerU could not locate that table. Stage 3 in this case goes through a visual-estimation fallback. **The convention uses "field omission" rather than
`null`**, to make `if "bbox" in c: ...` style checks easy.

`schema_version` stays `"0.1"`.

### Top-level fields: `extract_backend` / `mineru_task_id`

The top level of `figures_index.json` also contains the following two fields, read defensively downstream via `.get(default)`:

**`figures_index.json` top level**:

| Field | Type | Description |
|---|---|---|
| `extract_backend` | `"mineru"` | Stage 1 parse backend (fixed as `"mineru"`) |
| `mineru_task_id` | string \| null | MinerU task ID (handy for re-run diagnostics) |

**`figures_index.json/captions[i]`** (with the mineru backend every caption carries these):

| Field | Meaning |
|---|---|
| `bbox_source` | an enum value such as `"mineru:vlm"` (VLM-model recognition, `bbox_confidence == "high"`) |
| `html` | only present for `kind == "table"`; MinerU recognizes the table as HTML, which Stage 3 may choose to render directly or crop |
| `high_res_crop_path` | `"figures/<id>.png"`, `parse_pdf` has already used PIL to crop a high-resolution version from the 300 dpi full-page PNG |
| `subfigures` | `[{page, bbox}]` list of subfigures (e.g. paper Figure 2 being two side-by-side subfigures; an image with no numbered caption is merged into the next numbered figure) |

**The top level of `paper_meta.json`** also contains:

```json
"equations": [
  {"id": "eq_1", "page": 4,
   "bbox": [0.18, 0.34, 0.50, 0.04],
   "latex": "\\operatorname {Attention} (Q, K, V) = ...",
   "latex_raw": "\\operatorname {A t t e n t i o n} (Q, K, V) = ...",
   "is_appendix": false}
]
```

`latex` is the string after `clean_latex` cleanup (the spaces VLM mis-inserted between letters have been merged); `latex_raw` keeps the original for debugging. Stage 3 can handle it in one of three ways, see the "Equations" section of [design-style.md](design-style.md) for details.

`paper_meta.json/figures[]` and `tables[]` automatically inherit these fields from captions (`html` / `high_res_crop_path` / `bbox` / `bbox_source` / `bbox_confidence` / `subfigures`).

### The `is_appendix` marker (common to figures / tables / equations)

Every figure / table / equation carries `is_appendix: bool`, computed during Stage 1 parsing:

- **Decision rule**: find the section in `sections[]` with `kind == "references"` and note its `page_start` as `T`; an entry with `page > T` is treated as appendix. When there is no references section, fall back to "the `page_end` of the last non-references section".
- **Purpose**: keep all recognition results (**Stage 1 discards no figure/table** — appendix data may still be useful in long-talk / supplementary-material scenarios), but have Stage 2, when choosing `figure_ref` / `equation_ref`, **pick only `is_appendix == false` by default**. See [outline-heuristics.md](outline-heuristics.md) for details.
- **When to manually enable appendix entries**: in scenarios like a long keynote, supplementary material, or a reviewer presentation, Stage 2 may explicitly pick content with `is_appendix == true`; this is a judgment decision, not a rule.
