# Design Style

The visual decision guide for you in Stage 3 when expanding `slide_outline.json` into `slide_spec.json`. This file
is **self-contained**: the general deck-design fundamentals (palettes, fonts, layout, spacing, and the "Avoid"
taboos) are all below, followed by the special cases and trade-offs **unique to the paper scenario**.

## Design fundamentals

**Don't create boring slides.** Plain bullets on a white background won't impress anyone. Before choosing per-slide
content, settle four things:

- **Pick a bold, content-informed color palette**: it should feel designed for THIS paper. If swapping your colors
  into a completely different presentation would still "work", you haven't made specific enough choices. (The 10
  palettes below are inspiration; matching one to the paper's topic is in "Matching the palette to the paper topic".)
- **Dominance over equality**: one color dominates (60–70% visual weight), with 1–2 supporting tones and one sharp
  accent. Never give all colors equal weight.
- **Dark/light contrast**: dark backgrounds for title + conclusion slides, light for content (the "sandwich"
  structure, §5). Or commit to dark throughout for a premium feel.
- **Commit to a visual motif**: pick ONE distinctive element and repeat it across every slide — rounded image
  frames, icons in colored circles, thick single-side borders.

**Every slide needs a visual element** (image, chart, icon, or shape) — text-only slides are forgettable; this is a
hard rule for a paper deck (§4). Layout options to draw from: two-column (text left, illustration right) · icon +
text rows (icon in a colored circle, bold header, description below) · 2×2 / 2×3 grid · half-bleed image with
content overlay · large stat callouts (big 60–72pt numbers with small labels) · comparison columns. These are
design ideas to draw from; the legal values of `slide_spec.json/layout_kind` are governed by
[schemas.md](schemas.md) (anything not in the enum is composed freely via element x/y/w/h).

**Type sizes**: slide title ≥36pt bold · section header 20–24pt bold · body ≥16pt (≤14pt is unreadable from the back rows, see §4) · captions 10–12pt muted.
**Spacing**: ≥0.5" margins · 0.3–0.5" between content blocks · leave breathing room, don't fill every inch.

### Avoid (common mistakes — taboos)

- **Don't repeat the same layout** — vary columns, cards, and callouts across slides
- **Don't center body text** — left-align paragraphs and lists; center only titles
- **Don't skimp on size contrast** — titles need 36pt+ to stand out from 16–18pt body
- **Don't default to blue** — pick colors that reflect the specific paper topic
- **Don't mix spacing randomly** — choose 0.3" or 0.5" gaps and use them consistently
- **Don't style one slide and leave the rest plain** — commit fully, or keep it simple throughout
- **Don't create text-only slides** — add images, icons, charts, or visual elements
- **Don't forget text-box padding** — when aligning lines or shapes with text edges, set `margin: 0` on the text box or offset the shape to account for padding
- **Don't use low-contrast elements** — icons AND text need strong contrast against the background
- **NEVER use accent lines under titles** — a hallmark of AI-generated decks; use whitespace or background color instead

For the PptxGenJS API, pitfalls, and **icon generation** (react-icons → SVG → sharp → base64), see this repo's
copy [pptxgenjs.md](pptxgenjs.md) — when writing a spec and choosing icons, consult its "Icons" section (which includes a table of high-frequency academic icon names).

Below adds the rules **unique to the paper scenario**.

---

## Matching the palette to the paper topic

**First read `config.json/color_scheme`** (written to disk in Stage 0.5):

- `null` (the user chose "auto"): pick on your own from the 10 in the table below according to the paper's temperament — the default path of this section.
- non-`null` (the user's color-scheme description):
  the user's intent **takes priority**. If the description directly names a specific palette, use that one; if it is a color-family / directional description, pick the most fitting one from the 10
  in the table below. Still obey the principles below (coordinate with the main figure's dominant color, don't mindlessly pile on blue) and the visual-consistency
  hard rules in §0.

The 10 palettes below are only **inspiration**, not a constraint — you may use them directly, or build your own coordinated palette according to the paper's temperament /
the user's `color_scheme` description. Color codes are 6-digit hex (the `theme.*` written into the
spec needs a `#`):

| Palette | Primary | Secondary | Accent |
|---|---|---|---|
| **Midnight Executive** | `1E2761` navy | `CADCFC` ice blue | `FFFFFF` white |
| **Forest & Moss** | `2C5F2D` forest | `97BC62` moss | `F5F5F5` cream |
| **Coral Energy** | `F96167` coral | `F9E795` gold | `2F3C7E` navy |
| **Warm Terracotta** | `B85042` terracotta | `E7E8D1` sand | `A7BEAE` sage |
| **Ocean Gradient** | `065A82` deep blue | `1C7293` teal | `21295C` midnight |
| **Charcoal Minimal** | `36454F` charcoal | `F2F2F2` off-white | `212121` black |
| **Teal Trust** | `028090` teal | `00A896` seafoam | `02C39A` mint |
| **Berry & Cream** | `6D2E46` berry | `A26769` dusty rose | `ECE2D0` cream |
| **Sage Calm** | `84B59F` sage | `69A297` eucalyptus | `50808E` slate |
| **Cherry Bold** | `990011` cherry | `FCF6F5` off-white | `2F3C7E` navy |

**Principles**:

- Is the paper's main figure's dominant color X? When picking a palette, make primary **coordinate** with X (same color family or complementary), rather than clash
- **Don't pick blue for every paper**. This is AI's default lazy behavior; blue has already been overused by OpenAI/Anthropic/Google and the like

## Fonts

Font pairings are only **inspiration**, not a constraint — pick a header + body pair on your own according to the paper's tone. Below are pairing options (use them directly, or pair your own):

| Header | Body |
|---|---|
| Georgia | Calibri |
| Arial Black | Arial |
| Calibri | Calibri Light |
| Cambria | Calibri |
| Trebuchet MS | Calibri |
| Impact | Arial |
| Palatino | Garamond |
| Consolas | Calibri |

**Taboos**: don't use casual fonts like Comic Sans, Papyrus, Brush Script; don't use the same font for both header
and body (unless it's a minimalist style and you strictly distinguish by weight).

## Mixing layout_kind

`layout_kind` is decided by you in Stage 3 according to slide role + content form on your own, with no preset mandatory pairing.

**Repeating the same layout is another typical fingerprint of AI generation** — a set of slides should mix at least 4 or more layout_kinds.

## 0. Visual-consistency hard rules (obey **before all other rules**)

The 4 items below are the **highest-priority** hard constraints to execute when writing a spec in Stage 3. The other design suggestions (palette, fonts, layout choices) are all second-order choices made on the premise of satisfying these 4.

### 0.1 Subtitle font size, font, and position consistent within the deck

**All `role: "title"` text elements on non-title-slide / non-conclusion-class (including qna) slides must use the same style** — `fontSize`, `fontFace`, `color`, `x`, `y`, `w`, `h`, `bold` are all identical.

**The concrete values are chosen by you in Stage 3 on your own according to the paper / theme / average title length** (fontSize anywhere in the 36-40pt range, y anywhere within 0.3-0.5), **but once chosen the entire deck is strictly consistent**: whatever s02 uses, s03 / s04 / s05 / ... / s11 all use the same set of values.

**Implementation point**: when writing the subtitle of the first non-title slide, fix a style dict (e.g. `{"fontFace": "Georgia", "fontSize": 32, "color": "<theme.primary>", "x": 0.5, "y": 0.4, "w": 9.0, "h": 0.9, "bold": true}`), and for every subsequent non-title/conclusion slide directly **reuse the fields of the same dict**, don't estimate each one separately.

**The only exceptions**:

- The title slide's (s01) main title: usually a larger font size (44-48pt) and a more centered position — this is the title-slide class's own style
- The conclusion / qna slide's main title: may match the title slide (dark background + large text), forming a sandwich structure

**Within** each class it must be consistent within the deck (not every slide being different).

### 0.2 Avoiding title orphans

When PptxGenJS textbox text is too long it wraps automatically; render_pptx.py already automatically adds `autoFit: true` to `role: "title"` text elements, which in most cases automatically shrinks the font size to keep a single line. Even so, Stage 3 must still proactively avoid orphans:

- The pairing of title word count and textbox width should let "the vast majority of" titles fit on a single line; rely on autoFit as a fallback only for the very few extra-long titles
- **Don't** specially change the `fontSize` of one extra-long title just for it — that breaks 0.1's consistency. The handling of a long title is to rewrite it shorter, or let autoFit shrink it automatically
- When the title slide's paper title is especially long (> 8 words), just lower the main title's font size one notch from the default large size (e.g. 48 → 36) — but all titles within the title-slide class use the same font size

### 0.3 Image proportional scaling (never distorted)

Before generating the `.pptx`, `render_pptx.py` **reads each image's real dimensions with PIL**, treats the `(x, y, w, h)` given in the spec as a "maximum box", automatically computes "the actual footprint after proportional scaling by the original image's ratio + centering within the original box", and then feeds it to PptxGenJS. This step happens on the Python side of the render pipeline, **independent of PptxGenJS's sizing field**, so **no image is ever stretched horizontally/vertically** — the aspect ratio of letters and numbers in a table always stays consistent with the original PNG.

When Stage 3 assigns an image's `(w, h)`, still try to stay as close to the original image's ratio as possible (so the whitespace after proportional scaling is minimal):

1. **First look at the original image's actual aspect ratio**: `Image.open(path).size` or eyeball the relative proportions of the figure/table in the full-page PNG
2. Choose an available box within the layout (e.g. the right half of `image_half_bleed`, a cell of `grid_2x2`)
3. **Make the box's aspect ratio as close to the original image's ratio as possible** — this way the image fills the box, whitespace is minimal, and it looks visually full
4. When you don't know the original image's ratio, **using a square box** (`w == h`) is safest — render will automatically scale by the original ratio and center it, never distorted

Note: the spec **does not need** a `sizing` field — the render side ignores it (because (w, h) has already been adjusted to the actual footprint on the Python side, independent of PptxGenJS's sizing). Writing it is harmless; it gets popped automatically.

### 0.4 Overall balanced distribution of elements (check **both the full page + sub-regions**)

**Principle**: a slide is a 10" × 5.625" canvas; all elements should **fill the entire canvas as much as possible**, **leaving no large blank in any direction** — it can't be skewed top-bottom, can't be skewed left-right, and even more so **can't be skewed within some sub-region**.

> **Enforced in the QA phase**: any item listed in 0.4.a / 0.4.b / 0.4.c of this section, if violated, in the QA phase
> is handled as a **hard issue** — you must change `slide_spec.json` to fix it; marking it soft / skipping it is not allowed.
> The subagent prompt already requires reporting them as hard (see the "Visual Subagent Prompt for QA" section at the end of this file),
> and when you yourself review the subagent's report, don't stuff these into the "soft" bucket either — the judgment of skipping with a single
> "looks OK / slight whitespace is a soft issue" is this skill's **most common derailment mistake**. See the final section "Principles for Fixing QA Issues" for details.

#### 0.4.a Full-page bbox check

- **Vertical**: `max(y + h)` ≥ 4.0" (elements extend below ~70% of the slide's height)
- **Horizontal**: `max(x + w)` ≥ 8.5" and `min(x)` ≤ 0.7" (elements reach both the left and right edges)

#### 0.4.b Sub-region balance (the **most error-prone** check; this is mainly where the user's visual impression comes from)

A filled full-page bbox doesn't mean it's visually full — **two-column layouts** like `two_column` / `image_half_bleed` must additionally check the vertical footprint of each of the left and right columns **separately**:

- **The left and right columns' max(y + h) differ by ≤ 0.6"**: e.g. the left column's 4 bullets only reach y=4.0 while the right column's image occupies down to y=5.0 → a difference of 1.0" is too large, leaving half-an-inch+ of blank at the lower left, and visually it "crowds the top half"
- **Method of judgment**: split elements by x_center into a left half (< 5") and a right half (≥ 5"); the max(y+h) of each group should be close

**Fixing when the two columns are uneven**: follow the **three-lever model** of the final section "Principles for Fixing QA Issues" (adjust text amount > adjust
bullet spacing > adjust image size, stackable). Unevenness is mostly because the content amounts of the two columns are unbalanced → first add
substantive content to the short column (lever 1) and re-distribute its bullet element's `y` to fill that column's height (lever 2);
if still not enough, then scale the image proportionally (lever 3).

#### 0.4.c Single-column / icon_rows / stat_callout also need internal-distribution checks

- **bullet list**: bullets are independent elements by default; if they only occupy the top half of the box (typically 4 of them only occupying 2" of a 3.5" box), adjust by the three-lever model (add text amount / widen bullet spacing to fill the region)
- **icon_rows**: the y of the 3-4 icon + text blocks should be **equidistantly distributed** over the box's full height, not piled in the middle or top

#### 0.4.d Forbidden

- Shrinking body bullet font size to < 16pt to force-fill
- Widening an element to > 10" to let PptxGenJS overflow automatically (content gets clipped)
- bullet content occupying only 1/3 of the box — bullets should be separated by default, adjusted by the three-lever model (add text amount / widen spacing), not faking a fit by shrinking the box

## Visual-Richness Recommendations

The two items below are **aesthetic tips, not hard rules** — they don't enter the section-0 hard checks, and QA won't fail because of them; but they can lift a "correct but plain" page to having a professional feel.

### A. Give bullets a leader marker (**strongly recommended**)

Don't leave body list items as unmarked plain-text lines (like a wall of text). Each bullet should have a
list-item leader marker in front — **use a standalone `kind:"icon"` element** as the leader marker (a semantic icon is best;
when you only want a neutral marker, use small geometric icons like `FaCircle` / `FaSquare` / `FaAngleRight`,
see [pptxgenjs.md](pptxgenjs.md) "Icons").

- **Disable PptxGenJS's default `bullet: true`** — the default dots it produces are too ugly; a custom
  `bullet:{code}` top-level boolean isn't passed through either, so don't take this route at all
- **Don't** hand-type `"• "` / `"- "` in the text (pptxgenjs.md pitfall: it becomes a double bullet)

Compatible with the **splitting into multiple standalone text elements** of 0.4.b / "Principles for Fixing QA Issues": after splitting, give **each**
single-line element its own marker icon; don't lose the leader markers after splitting.

**The leader marker and the text must be vertically center-aligned (iron rule)**: the marker icon's box is short (e.g. `h≈0.2`),
while the paired text box is tall and often `valign:"middle"` (`h≈0.5–0.66`) — both have a visual center of `y+h/2`,
and casually using the same `y` makes the whole row of leader markers sit too high, where "the markers aren't aligned" is visible to the naked eye (the visual QA subagent easily misses reporting this,
so rely on the quantitative self-check below to catch it).

- **Formula**: `icon_y = text_y + (text_h − icon_h) / 2` (the icon's vertical center == the text box's
  center; the same goes for multi-line bullets, the icon lands at the midpoint of the text block)
- Horizontal: leave a ~0.1" gap between the icon's right edge and the text's left edge
- **At the wrap-up, use a script to batch-self-check each leader+text pair** `icon.y+icon.h/2 ≈ text.y+text.h/2`
  (a difference > 0.02" is a naked-eye-visible offset), don't rely on eyeballing

### B. Underlay a rounded rectangle beneath structural groupings (recommended)

For grouped structures like a non-title "large text + small text" (e.g. a KPI number + caption) or "icon + phrase",
you can underlay a low-key rounded rectangle beneath it (`ROUNDED_RECTANGLE` + `rectRadius`, light fill, `z` placed below the content) to add layering and a card feel.

- For the API see [pptxgenjs.md](pptxgenjs.md); **note its pitfall #8**: don't stack a rectangular
  accent bar on top of a rounded rectangle (it can't cover the rounded corners); to stroke it, use the ROUNDED_RECTANGLE's own `line`

## Design trade-offs unique to the paper scenario

### 1. Formulas

PptxGenJS is not good at rendering math. **First look at `paper_meta.json/equations[]`** (the mineru backend fills it automatically):

```json
{"id": "eq_5", "page": 6,
 "bbox": [0.18, 0.34, 0.50, 0.04],
 "latex": "PE _ {(pos, 2 i)} = \\sin (pos / 1 0 0 0 0 ^ {2 i / d _ {\\mathrm {model}}})"}
```

#### Processing priority (must judge in order, **don't default straight to cropping the image**)

**Step one: judge whether the latex is "simple"**: the cleaned latex string contains **none of** the keywords below → simple:

```
\sum   \int   \prod   \begin{matrix}   \begin{cases}   \begin{align}   \\\\
```

**Step two: choose one of the two below** (doing "both" is not allowed):

| Formula type | Handling | Form written into the spec |
|---|---|---|
| **Simple** (default) | **Unicode rewrite**, write a text element | a single-line string, fontFace uses Cambria, e.g.: `Attention(Q,K,V) = softmax(QK^T / √d_k) V` or `PE(pos, 2i) = sin(pos / 10000^(2i/d))` |
| **Complex** | `equations[i].bbox` + `page_screenshot.py` to crop the original PDF line, as an image element | the image element points to the cropped PNG |

**Step three** (independent of the above): **always** write the original `latex` string into `speaker_notes` as a fallback — so a later revision or a renderer swap can still recover the original content.

#### No double display (**most common error**)

**The same formula is expressed on the deck only once (one of the two)**: a bullet already wrote Unicode → don't add that formula's image element, and use the saved space for a visualization; cropped image → the bullet does **not** repeat writing the formula.

### 2. The size of paper figures

Figures in papers are usually 4:3 or closer to square. A `LAYOUT_16x9` slide is 10×5.625"; when stuffing a figure
into `image_half_bleed`:

- Single figure: width 4.5–5", height auto-fit (keep the ratio, don't stretch)
- Multi-panel composite figure (e.g. the paper's Figure 1 is composed of 6 subfigures): consider cropping only **a part** of the paper figure
  as a slide element (give a bbox with `page_screenshot.py`); stuffing 6 onto a slide will be a blur
- The source of the crop bbox and the QA re-crop rule are **the same as the §3 table below**: do directional fine-tuning based on mineru's original box, don't eyeball out of thin air

### 3. Tables

A paper's result table usually has many columns + dense text. **Don't rebuild it with a PptxGenJS table** (hand-writing
50 rows of cells, tuning alignment until you break down). Just:

- Crop the result table region from the full-page PNG → use it as an image element
- Next to it, use a sentence or two of bullets to highlight "our method is +X.Y better than the baseline"

**Crop bbox (figures and tables follow the same rule): the first cut must be mineru's original box itself, and QA re-cropping also only moves that one edge on the original box — throughout, don't eyeball the full page out of thin air**

> ⚠️ **This skill's most common execution derailment in testing**: the Agent "takes it upon itself" to skip step 1 below and, before cropping
> the first version, goes to look at `pages/page-NN.png` to estimate the box → the figure cuts off the title, the table sweeps in the caption /
> misses key rows, and re-cropping two or three times still doesn't crop accurately. The rule was laid down long ago; derailment is almost always due to jumping the gun without following step 1.
> **Iron rule: the bbox of the first `page_screenshot.py` call must equal `captions[i].bbox` value by value,
> eyeballing first is not allowed.** Thinking "the original box is surely inaccurate, looking at the page first and then estimating is faster" — that very thought is the derailment point;
> the original box's first cut + single-edge fine-tuning is almost always faster and more accurate than re-estimating.

1. **First cut = original box's original values (not allowed to eyeball first)**: pass the four-tuple of `figures_index.json/captions[i].bbox` (detected by `mineru:vlm`) **unchanged** to `page_screenshot.py` to crop the first version, **and before cropping this version you are not allowed to look at `pages/page-NN.png`**. **`bbox_confidence == high` does not equal clean edges** — in testing, mineru often presses the `y` start point onto the subfigure title / caption line, causing the title to be cut or the caption to be swept in; this is expected, solved by step 2's fine-tuning of that one edge, **not a reason to abandon the original box and re-estimate**.
2. **When QA finds the crop isn't clean — don't abandon the original box and re-eyeball**. Look at the QA-rendered image to judge **which edge has too much / too little**, and only do directional incremental fine-tuning of that edge on the original bbox:
   - Top cuts off content (subfigure title, first line is cut) → decrease `y`, increase `h` in sync (expand upward)
   - Bottom / a side sweeps in the caption or body text → decrease the corresponding `h` / `w` (pull inward)
   - Move only one edge by a small amount at a time (≈0.01–0.03), re-crop → look again, usually converging in one or two rounds. **The original box's x/w and rough position are usually already correct; the wrong thing is just one edge** — change that edge, don't re-estimate the whole thing
   - **Tables must keep their own top and bottom rule lines** (booktabs `\toprule` / `\bottomrule`). When pulling the top edge down to remove the caption, **stop at the upper edge of `\toprule`**, don't pull too far and crop the top line away; a table missing the top/bottom rule lines looks "open / broken"
3. Only when the `bbox` field is entirely missing (neither the script nor mineru located it, rare) do you fall back to looking at `pages/page-NN.png` to estimate the box, still **err tight rather than loose**, with `--pad 0.005` as a fallback

**Figures and tables are the same**: this rule applies equally to the `page_screenshot.py` cropping of paper figures.

### 4. Text amount is decided by space (no word-count cap)

Don't set hard limits like "≤ N words per page / ≤ N words per bullet". Text amount serves one goal:
**this page is filled by content, with neither whitespace nor overflow of the box**.

- **Lower bound (prevent whitespace)**: content (visual elements + text) must fill the canvas, satisfying section 0.4's
  checks like `max(y+h) ≥ 4.0"`, column balance, box≈content height. When too little text causes whitespace, **prefer
  adding substantive content** (one more point / add a takeaway sentence / pair a caption), not faking a fill by enlarging the font size
  or stretching the box height
- **Upper bound (prevent overflow)**: text must not exceed the box / canvas. **The font-size lower bound is the physical-readability red line**:
  title ≥ 36pt, body ≥ 16pt (≤ 14pt is invisible to the back rows). Fix overflow with the 3 levers of the final section "Principles for Fixing QA Issues"
  (first trim the text amount); if it still doesn't fit at the red line = the content really is too much → split into two pages, don't force-cram by shrinking the font size
- **Bullets are split into standalone text elements by default**: one element per bullet, with `y` distributed within the available height
  (**recent testing shows separated layout is reliably better than a single multi-line textbox**, this is the default practice, not a remedial
  measure). Only a very short list of ≤2 items uses a single multi-line element. After the default separation, whitespace / overflow can
  be adjusted directly with the 3 levers (especially lever 2, adjusting bullet spacing), with no need for ad-hoc rearranging
- **Every page must have a visual element**: at least one of figure / table / icon / chart / meaningful shape,
  no text-only pages (the "Don't create text-only slides" taboo above). First decide how much the visual
  occupies, then fill the remaining space with text until it's substantial
- One thing still firmly held: **a bullet is a distilled point, not a transplant of the paper's abstract** — "short" is judged by "whether it is
  one clear single point", not by counting words

### 5. Sandwich structure

A dark-palette `title` and `conclusion`/`qna`, with the middle content using a light palette. This "dark-light-dark"
structure gives the audience a psychological sense of rhythm of "opening—body—closing". The `theme` is still a single palette, but
the title/conclusion slide just uses a `shape` to full-screen fill the primary color as the background.

### 6. Things to avoid (be especially wary in a paper deck)

- ❌ Adding horizontal line decoration under a title (a typical AI fingerprint — see the "Avoid" taboo "NEVER use accent lines under titles" above)
- ❌ Writing the paper title in the footer of every slide (repetitive noise; writing it once on the title slide is enough)
- ❌ Copying a whole page of formulas directly (can't be read clearly)
- ❌ A purely ceremonial slide like "Thanks for listening" (takes up space, the conclusion already wrapped up)
- ❌ All slides using the same layout_kind
- ❌ Default PowerPoint template colors (Office blue-and-white)

## Visual Subagent Prompt for QA

When going through the [QA loop](qa.md), **use the base visual-subagent prompt template in [qa.md](qa.md) §B.2 directly**,
don't rewrite it yourself. For a paper deck, beyond the base template, **add two extra paragraphs** of additional requirements:

> Which **slides** the prompt's "Read and analyze these images" lists are decided by the re-check narrowing rule in step 5 of
> "Principles for Fixing QA Issues" below (round 1 all, re-check rounds list only
> flagged ∪ changed pages, last round all) — not listing the full deck every round.

**Added paragraph A: content accuracy**

> Additionally, specially check: can all numbers (percentages, improvement amounts, model scale) find a correspondence in the caption or the paper's
> original text? Is the bullet wording consistent with the paper's abstract / contributions (don't
> fabricate on your own)?

**Added paragraph B: whitespace / column balance / leader-marker alignment (per this file's section 0.4 + section A's alignment iron rule, must be reported as a hard issue)**

> For each slide **report the following five numbers or judgments item by item**, don't vaguely say "looks OK":
>
> 1. What is the full-page `max(y + h)`? Is it ≥ 4.0"? Below that means the page is top-heavy and bottom-empty — **hard issue**
> 2. If it is `two_column` / `image_half_bleed`: split all elements by x_center into
>    a left half (< 5") and a right half (≥ 5"); what is the difference between each group's `max(y + h)`? Is it ≤ 0.6"?
>    Exceeding it means one side "crowds the top half" — **hard issue**
> 3. For each textbox containing N bullets: what is the difference between N × 0.5" (an estimate of the actual content height) and
>    `box.h`? Is it ≤ 0.6"? Exceeding it means "content crammed up top, box empty below" — **hard issue**
> 4. For each card (rect / rounded_rect container): what is the bottom blank height (the card's bottom edge −
>    the lowest element's bottom edge)? Is it ≤ 1.0"? Exceeding it means "the bottom half of the card is empty" — **hard issue**
> 5. Is the leader-marker icon **obviously misaligned to the naked eye** with the paired bullet text (the icon obviously skewed above/
>    below the text)? **Report only naked-eye-obvious misalignment** — what you see is the rendered image, you can't read coordinates, **don't fabricate
>    numbers like `icon.y+icon.h/2`, and don't misjudge "the icon centered on a multi-line text block" as skewed up**. The precise
>    `icon.y+icon.h/2 ≈ text.y+text.h/2` (≤0.02") is self-checked by the lead agent with a coordinate script ("Visual-Richness
>    Recommendation A"), not your job.
>
> Items 1–4 and item 5's naked-eye-obvious misalignment are **reported as hard issues**, **forbidden** to write vague wording like "soft / minor / looks acceptable / roughly OK"
> — such wording makes you skip the fix during review.

## Principles for Fixing QA Issues (re-read section 0.4)

After the subagent reports issues back:

1. **Whitespace / imbalance / leader-marker-misalignment issues are forbidden to be marked soft and skipped** — the 5 categories listed in added paragraph B are all
   hard issues, you must fix `slide_spec.json`. Common mis-judgments: "bottom whitespace is a soft issue" /
   "the marker being off by a little doesn't matter" — **wrong**, per section 0.4 and section A's alignment iron rule they are exactly what must be fixed.
   If you see the subagent mark these as soft, you also must reclassify them as hard and then fix.
2. Fix the corresponding field of `slide_spec.json`; don't go change `slide_outline.json` (unless the problem is further
   upstream, e.g. the outline chose the wrong figure_ref).
3. **Fix whitespace / overflow with only 3 levers** (decreasing priority, stackable). Bullets are already
   standalone text elements by default (see §4), and the levers all operate on them:
   1. **Adjust text amount (highest priority, addresses the root)**: too empty → add substantive content (one more point / expand
      an over-distilled point / add a takeaway sentence / pair a caption); overflow → trim to a clear single point.
      Echoes §4's lower / upper bound
   2. **Adjust bullet spacing**: re-distribute each bullet element's `y` evenly within the available height
      (or adjust `paraSpaceAfter`) — too empty widen the spacing to fill, overflow tighten it
   3. **Adjust image size (lowest)**: proportionally enlarge / shrink the image's footprint to eat up / yield space
      (constrained by 0.3, the image won't distort; don't hard-enlarge a small image to a blur just to fill space)

   **Stackable**: too empty → lever 1 (add text amount) + lever 2 (widen spacing) used together; overflow →
   lever 1 (trim) + lever 2 (tighten spacing). Move 1 first, if not enough then stack 2, and only 3 last.
4. **`valign:"top"` + a tall box far exceeding the content** is still an anti-pattern (content crammed in the top half, blank below);
   since bullets are separated by default, a single large textbox shouldn't appear anymore — adjust with the 3 levers above, don't rely on valign to save it.
5. After fixing, `--from-stage render` to **re-render in full** (render is cheap and deterministic; crop / spec changes
   must propagate to the whole deck; what gets narrowed is the expensive per-page visual review by the subagent below, not the render) → **QA again**,
   requiring the subagent to re-report the five items of added paragraph B, verifying the whitespace is really gone and the leader markers are really aligned. **"Fix and hand off" is not allowed**.

   **The scope of re-check rounds is narrowed per the [Verification Loop](qa.md)** ("Re-verify affected slides …
   Repeat until a full pass reveals no new issues") — the biggest token waste of multi-round visual QA is
   re-feeding the untouched pages to the subagent page by page every round:

   - **Round 1**: full deck page by page (a single subagent, "Read and analyze these images" lists all slide jpgs)
   - **From round 2 on (re-check)**: the subagent only looks at = the pages flagged in the previous round ∪ the pages whose spec actually
     changed this round; the images list lists only these, the untouched pages are **not re-fed**
   - **The last round before convergence**: a full deck full pass must be done once (a single subagent goes through all pages) — "one fix
     often introduces a new problem", and it only passes when a full pass reveals no new issues
   - The hard-issue determination, the five items of added paragraph B, the ban on marking soft — **all unchanged**, only "which pages to look at each round" is narrowed
