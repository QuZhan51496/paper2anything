# Agent Design Rules from Reference Posters

These rules are distilled from the local examples in `references/poster_examples/`.
They are intended for the Paper2Poster planner, critic, and renderer agents.

Before placing content, the planner should load
`references/poster_archetype_library.json` and choose an archetype. The examples
show that strong posters are not one template; they use different structures for
method papers, benchmark papers, theory papers, visual papers, and diagnostic
analysis papers.

Recommended archetypes:
- `visual_problem_method_results`: visual problem grid + method + results.
- `compact_method_takeaway_strip`: method-centered layout with a concise claim strip.
- `three_zone_empirical_ml`: motivation / method / experiments zones.
- `numbered_freeform_benchmark`: numbered panels for benchmark or dataset papers.
- `question_driven_evidence_map`: research-question panels for diagnostic papers.
- `thesis_rail_theory`: left thesis rail plus dense technical panels.
- `qualitative_interpretability_grid`: qualitative visual grid as primary evidence.

## 1. Header Assets Are Real Assets, Not Decoration

Reference posters use the title band for institution logos, conference logos,
author/affiliation information, and QR/code links. They do not invent fake
logos or meaningless QR-like placeholders.

Agent rule:
- If venue, institution logo, code URL, or QR is unknown, ask the user or remove
  that slot.
- Never render a fake logo/QR in the final poster.
- Header layout must reflow when assets are missing.

## 2. Captions Need Hierarchy

Good posters keep figure/table captions short. Definitions such as "denotes",
"indicates", "means", and abbreviation explanations are placed as small
footnotes or legends below the main caption.

Agent rule:
- Split raw captions into `display_title`, `footnotes`, and `legend`.
- Main caption: one short sentence.
- Footnote: notation/abbreviation explanations.
- Legend: recurring terms such as HL/LL/EM/TM/SR/GP.
- The renderer, not the language model, decides the visual level.

## 3. Tables Are Used, But Guided

Reference posters often include original tables, but they are not left
uninterpreted. They are enlarged, cropped, highlighted, or paired with a short
local interpretation.

Agent rule:
- Do not shrink a dense table into an unreadable panel.
- Prefer one readable large table over several tiny tables.
- If a full table is too dense, crop key rows/columns or add callout boxes.
- Put "what to inspect" beside or under the table.

## 4. Main Visual Depends on Paper Type

The central visual is chosen by contribution type:
- Method paper: method architecture or pipeline.
- Benchmark/data paper: task/data construction plus representative examples.
- Vision/interpretability paper: qualitative comparison grid.
- Theory/analysis paper: thesis rail plus equations and plots.

Agent rule:
- Classify the paper story before choosing layout.
- Do not force every paper into a three-column template.
- Reserve the largest visual region for the primary explanatory figure.
- For benchmark papers, consider `numbered_freeform_benchmark` before the plain
  three-zone layout because task examples often need explicit ordering.

## 5. Dense Is Acceptable When Structured

Top-conference posters are often dense. They remain readable because section
bars, arrows, boxed callouts, numbered panels, and local captions make the
reading path visible.

Agent rule:
- Penalize sparse slide-like layouts with large empty panels.
- Use 10-20 compact content units when the paper has enough material.
- Keep section chrome small; spend area on figures, tables, and evidence.

## 6. Footer Must Carry Real Content

Takeaway, references, and acknowledgments in reference posters are concise but
specific. They are not generic placeholders.

Agent rule:
- Takeaway must be a paper-specific conclusion.
- Key numbers must be grouped by meaning: dataset, method, result, limitation.
- References must use available bibliographic data only; ask if missing.
- Footer should never contain pipeline/debug text.

## 7. Critic Checks to Add

The visual critic should explicitly flag:
- fake or meaningless header assets,
- captions with notation explanations at full caption weight,
- unreadably small tables or plots,
- generic takeaway/key-number/reference sections,
- large empty visual containers,
- metric-first posters where the task is not clear,
- shuffled reading order without section numbers, arrows, or spatial grouping.
