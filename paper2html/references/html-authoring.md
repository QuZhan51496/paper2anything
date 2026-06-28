# index.html authoring rules (hard constraints + pitfalls)

## manifest is the single source of truth

Use only the **verified material** in `manifest.json` (title/authors/abstract/links/claims/figures/tables/
method_components/bibtex). **Do not fabricate** numbers, authors, affiliations, or links the paper doesn't have.
Fields left empty in the manifest (e.g. authors=[], abstract="", links.paper="") are limits of deterministic
extraction — **you fill them in from the full text of `clean.md`** (this is exactly "you are the backstop":
you are the lead author, the extractor is only scaffolding). Appendix/supplementary figures and tables were
already filtered at gate 1 and never enter the manifest.

## Self-contained, deployable

- The deliverable is `<workdir>/index.html` + a sibling `<workdir>/images/`, droppable straight onto GitHub Pages.
- Reference images with a **relative path** `images/<filename>` (the filename comes from `manifest.figures[].file` /
  `tables[].image`, which parse_pdf has already copied into `images/`). **Don't** write absolute paths or `../` cross-directory references.
- Every `<img>` needs a **non-empty `alt`** (use the caption). Don't leave `href="#"` empty anchors.
- Inline CSS/JS or use a CDN (e.g. MathJax) so the single file just opens and works. When writing formulas with
  MathJax (`$…$` / `$$…$$`), the `<` and `>` inside the delimiters must be written as `\lt` / `\gt` — a bare `<`
  followed by a letter is treated by the browser as an opening HTML tag, splitting the formula and making MathJax
  skip it (the literal `$$…$$` stays on the page and render_check reports FAIL). A long display formula (`$$…$$`)
  won't wrap in a narrow viewport and pushes the page wide (render_check at 390 reports FAIL) — wrap it in an
  `overflow-x:auto` container so the formula scrolls horizontally within itself instead of widening the page (same as wide tables).

## Project-homepage layout suggestions

- Keep the first screen editorial and light: title, authors, affiliations, resource buttons (paper/code/project,
  from manifest.links; omit the empty ones).
- Show the main figure (architecture/pipeline) as a one-time teaser, not a repeated background.
- Suggested order: teaser → abstract → claims → method → results → supporting figures → BibTeX (adjust to the paper's character, not mandatory).
- For result tables, **prefer the table screenshots cropped from the paper** (`tables[].image`), since extracted HTML tables often lose formulas and alignment.
- Use cards only for repetitive content (claims, story, table, gallery items); don't overuse them.
- Size figures by role: give the architecture diagram a large readable stage, method figures secondary, gallery capped.

## figure CSS pitfalls (border hugs the image, never distort)

- **The border must hug the image itself**, not frame whitespace: don't combine `width:100%` + `object-fit:contain`
  on a fixed-width box (the image shrinks inside a big frame with whitespace around it). Pick one of two safe forms:
  - Fill the column width: `display:block; width:100%; height:auto;` + border (border hugs the image, in-figure text maximized).
  - Cap the height, centered: `display:inline-block; max-height:X; width:auto; height:auto;` + border, with outer `text-align:center`.
- **Never force a fixed `height` (or fix both `width`+`height`) to fill whitespace** — it stretches the image out of shape.
  Set at most one axis (`width:100%;height:auto` or `max-height:X;width:auto`), let the other adapt. Fill whitespace with
  **content** (one more takeaway / one more bullet) or re-balance the columns; don't stretch the image.
- Post-render self-check: each `<img>`'s `renderedW/renderedH` should equal `naturalW/naturalH` (±2%), otherwise it's distorted.

## Table strategy

- `manifest.tables[]` are mostly **image tables** (`image` has a value, `html` is empty) — display directly with `<img src="images/...">`.
- If a table has `html` (pipeline table reconstruction), you may render it as a native HTML table styled to match the site; otherwise use the screenshot.
- Native wide tables (multi-column comparison tables) must go in a **horizontally scrollable container** (`overflow-x:auto`
  + set a `min-width` on the table to hold column widths); don't use `overflow:hidden` — in a narrow viewport the right-side columns get clipped and can't be scrolled to.
