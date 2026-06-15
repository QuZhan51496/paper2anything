# Public Top-Conference Poster Pattern Notes

Downloaded examples live in `references/poster_examples/`.

Sources:
- ICLR 2024 virtual poster PNGs from `https://iclr.cc/media/PosterPDFs/ICLR%202024/<id>.png`
- CVPR 2024 virtual poster PNGs from `https://cvpr.thecvf.com/media/PosterPDFs/CVPR%202024/<id>.png`

## What Real Posters Do Differently

1. They are dense but anchored.
   Most examples have many panels, but one or two large visual anchors control
   the reading path: a method diagram, qualitative grid, result matrix, or
   side-color thesis block.

2. They use more shapes than columns.
   A poster is not usually just three columns. Common primitives include:
   full-width title, side thesis rail, large central workflow, top method band,
   right result stack, bottom takeaway strip, and figure grids spanning multiple
   columns.

3. They tolerate tables, but tables are edited.
   Tables are cropped, highlighted, boxed, and paired with small conclusions.
   Raw paper tables are rarely pasted without visual guidance.

4. They use visual ordering inside panels.
   Arrows, numbered callouts, colored frames, and highlighted rows guide the
   viewer through dense material. Our current panels lack these internal
   reading cues.

5. They often put method before result when method is the contribution.
   Our current solver assumes result-first too often. In many ML/CV posters,
   the center of the poster is the proposed method, with result evidence to the
   side or bottom.

6. They avoid oversized empty containers.
   Real posters pack visual content tightly. Empty white card space makes our
   output look like a slide deck rather than a poster.

7. They use asymmetry strongly.
   Examples include a 25%-75% split, a dark left thesis block plus right
   evidence field, a wide center diagram with narrow support strips, or a
   top-half method / bottom-half results structure.

## Layout Primitives To Add

- `side_thesis_rail`: a dark or tinted left rail containing motivation,
  contributions, or the main claim.
- `wide_method_band`: a large horizontal method/process figure across the
  upper or middle poster.
- `result_matrix_zone`: dense result grid/table area with highlighted rows or
  metric callouts.
- `qualitative_grid_zone`: visual comparison grid for image/video/vision papers.
- `callout_overlay`: numbered labels or colored outlines over figures.
- `takeaway_footer`: bottom strip with 2-3 final claims, not a normal text card.
- `two_anchor_layout`: one method anchor plus one result anchor, each large
  enough to read.

## Rules To Apply To Our Solver

- Stop defaulting to three-column structure.
- Choose an archetype from paper content:
  - method contribution -> method-dominant poster
  - benchmark/evaluation -> result-matrix poster
  - visual generation/CV -> qualitative-grid poster
  - theory/proof -> thesis-rail plus equation/result panels
- Allocate 45-65% of body area to visual evidence.
- Generated process figures should become `wide_method_band`, not normal cards.
- If the main evidence is a chart, crop and enlarge the chart itself rather than
  putting it inside a large empty card.
- Put the final takeaway in a footer or highlighted strip.
- Allow dense panels, but add labels/highlights/callouts.

## Reading-Order Patterns From The Downloaded Posters

The stronger examples do not begin with an isolated metric. They first establish
the research object, then route attention into a visual explanation:

1. **Title band.** The paper title stays stable at the top. It is not replaced
   by a claim, number, or marketing sentence.
2. **Subject/intro entry.** The first body area answers "what is this work
   about?" Examples use a short motivation block, a problem sketch, or a
   one-sentence claim tied to the method/system.
3. **Central visual anchor.** The viewer then sees the largest method diagram,
   qualitative grid, task schematic, or result matrix. This is where the poster
   explains the work, not merely where it decorates the page.
4. **Evidence lane.** Numbers, tables, charts, and metric cards appear beside
   or below the main visual as proof. They are rarely the first thing the poster
   asks the viewer to interpret.
5. **Detail panels.** Dense text blocks, ablations, metric definitions, and
   failure modes are placed around the anchor. They support close reading but
   do not compete with the central visual.
6. **Takeaway/footer.** The final row or corner summarizes implications,
   limitations, or links. It should feel like the end of the visual path.

For Paper2Poster, the default human reading path should therefore be:

`Title -> intro/problem -> central method/result visual -> evidence/results -> takeaway`

This is different from a metric-first path such as:

`Title -> giant number -> scattered support cards`

The latter is closer to a dashboard or slide headline than a conference poster.

## Content Density Patterns

The examples are often dense, but the density is organized:

- They use 10-20 short content units, not 5 large sparse cards.
- They combine diagrams, captions, metric callouts, and short bullets.
- They crop figures so the figure itself fills the reserved region.
- They use bold labels, arrows, outlines, and numbered callouts inside figures.
- They keep repeated section chrome small; the content area carries the weight.
- They avoid large empty containers around small plots.

For the agent workflow this means:

- The strategist should decide the subject-first story before selecting a
  metric.
- The layout designer should place intro/context before or beside the main
  visual, not after results.
- The visual curator should choose an original paper figure that makes the
  paper topic obvious at first glance, or a worded text explainer where no
  original figure works.
- The critic should penalize metric-first, empty, dashboard-like posters even
  if they are tidy.
