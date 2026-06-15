# University of Indianapolis Template Notes

Local source inspected:

`C:\Users\Admin\Downloads\学术会议模板University of Indianapolis Templates`

Representative previews exported to `_work/template_previews/`:

- `style_b_36_48_wide.ppt`
- `style_c_36_48_wide.ppt`
- `style_f_36_48_wide.ppt`
- `blueBevel_36x48.ppt`
- `CMS-Poster_template48x36-Pro.ppt`
- `postertemplate.ppt`

These templates are visually dated, so Paper2Poster should not copy their
colors, gradients, bevels, or decorative bars. The useful lessons are layout
discipline and visual grammar.

## Reusable Layout Lessons

### 1. Title Is A Dedicated Poster Object

The paper title lives in a stable full-width top region with authors and
affiliations directly below. It is not replaced by a result claim.

Paper2Poster implication:

- Keep `title_bar` separate from `headline`.
- Render paper title first.
- Render the hero claim below title, not as the title.

### 2. Columns Are Clear Reading Lanes

Several templates use strong vertical lanes or separators. Even when the
content is sparse, each lane has a clear left-to-right reading order.

Paper2Poster implication:

- Layout diagnostics should reward row-major and column-major consistency.
- Avoid layouts where the eye must alternate left -> right -> center -> left.
- If using rows, all blocks in a row should align on top and bottom edges.

### 3. Section Headers Create A Visual Index

Most templates use repeated colored header bars. The exact style is dated, but
the principle is useful: section headers form a scannable index across the
poster.

Paper2Poster implication:

- Section titles should be short and consistent.
- Header treatment should be uniform.
- Avoid oversized section titles inside small cards.

### 4. Main Figures Need Reserved Space

The templates reserve large blank zones for graphs/images. They do not treat
figures as incidental thumbnails.

Paper2Poster implication:

- A method or result figure should get a planned region before text is placed.
- Figures should not be squeezed into right-bottom corners.
- Dense tables should become metric cards or simplified charts, with the full
  table treated as secondary evidence.

### 5. References Are Visually Secondary

Old templates often include references, acknowledgments, and contact details,
but they are visually pushed to low-priority footer/right regions.

Paper2Poster implication:

- Default generated posters should omit references unless requested.
- If included, references should be compact and never compete with results.

### 6. Sparse Templates Are Better Than Overfilled Templates

Many templates deliberately leave large figure placeholders and whitespace.
They assume the poster author will insert images or graphs, not fill every
region with prose.

Paper2Poster implication:

- Critic should penalize wall-of-text more than moderate whitespace.
- Text panels should have strict budgets.
- Empty space is acceptable only when it frames a dominant visual, not when it
  is accidental leftover.

## Patterns To Avoid

- Heavy gradients and bevels.
- Low-contrast colored text on saturated header bars.
- Too many equal columns.
- Repeated "Results / Results continued" panels with no hierarchy.
- Decorative backgrounds that reduce figure legibility.

## Suggested Framework Changes

- Add a `poster_structure` layer before geometry:
  - title band
  - hero claim band
  - row 1 evidence/story blocks
  - row 2 method/secondary blocks
  - optional footer
- Add alignment constraints:
  - row blocks share top/bottom coordinates
  - column blocks share x/width
  - main visual gets reserved space before support text
- Add critic metrics:
  - `title_separation_score`
  - `row_alignment_score`
  - `section_header_consistency_score`
  - `figure_reserved_space_score`
