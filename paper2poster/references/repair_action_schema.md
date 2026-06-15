# Repair Action Schema

Agents may propose repair actions, but `layout_actions.py` is the only module that mutates outline or layout geometry. This keeps revisions predictable and prevents free-form agent coordinates from breaking the poster.

## Action Object

```json
{
  "type": "increase_hero_visual",
  "target": "results",
  "factor": 1.25,
  "confidence": 0.8
}
```

Required:

- `type`: action name.
- `target`: section role/title or `all`.

Optional:

- `factor`: numeric strength for spatial changes.
- `max`: bullet count limit for text-reduction actions.
- `priority`: section priority after emphasis.
- `column`: target column for move actions.
- `confidence`: critic confidence, currently informational.

## Supported Actions

| Type | Purpose | Typical Target |
| --- | --- | --- |
| `fix_reading_order` | Reassign problem, result, method, and takeaway roles into a clearer visual path. | `all` |
| `convert_results_table_to_metrics` | Render result numbers as metric cards instead of relying on a dense raw table. | `results` |
| `increase_hero_visual` | Promote the dominant result/method visual and metric cards. | `results`, `method` |
| `increase_figure_area` | Raise figure scale and priority for a target section. | `method`, `results` |
| `tighten_side_text` | Limit low-priority side panels to short bullets. | `support`, `all` |
| `compact_sidebars` | Mark side support panels as compact. | `support` |
| `compact_headline` | Reduce headline height when it crowds the main visual. | `headline` |
| `emphasize_section` | Raise a section's priority or move it to a stronger region. | `results`, `method` |
| `move_section` | Move a target section to a named column. | section role/title |
| `hide_section` | Remove a low-value section from the generated outline. | section role/title |

## Critic JSON Contract

Qwen-VL critique should return this shape:

```json
{
  "verdict": "The main evidence is visible, but the reading order is unclear.",
  "reading_path": ["title", "headline", "main result", "support panels"],
  "issues": [
    {
      "severity": "high",
      "type": "figure_legibility",
      "affected_element": "main_visual",
      "problem": "The result figure is too dense to read.",
      "fix": "Extract the two strongest numbers into metric cards."
    }
  ],
  "repair_actions": [
    {"type": "convert_results_table_to_metrics", "target": "results"},
    {"type": "increase_hero_visual", "target": "results", "factor": 1.25}
  ]
}
```

The UI may format this JSON as Markdown for users, but the repair loop should consume the structured `repair_actions` field directly.

## HTML Self-Feedback `design_patch`

For HTML poster rendering (`render_html_poster.py` / `run_html_self_feedback_pipeline.py`),
the visual critic returns a richer constrained-enum revision plan instead of free-form actions.
The renderer only executes values that match the allowed enums; everything else is silently
clamped to the safe default. `scripts/quality_gate.py` consumes the resulting subscores to
decide pass/fail.

### Envelope

```json
{
  "diagnosis": "short critique of why the poster is not yet top-tier (<=500 chars)",
  "revision_goal": "one sentence visual goal (<=300 chars)",
  "patch": { ... see Patch Enums ... },
  "content_guardrails": {
    "drop": ["content roles to remove or compress, not facts"],
    "keep": ["facts or figures that must remain visible"]
  }
}
```

`normalize_design_patch()` truncates `diagnosis` to 500 chars and `revision_goal` to 300 chars.
`content_guardrails` must be an object; non-object values are coerced to `{}`.

### Patch Enums

Eight design dimensions, each with a fixed allowed-values set. Unknown values fall back to the default in parentheses.

| Key | Allowed values | Default |
| --- | --- | --- |
| `macro_layout` | `center_hero`, `method_band` | `center_hero` |
| `hero_mode` | `original_figure`, `original_with_overlay`, `zoomed_triptych`, `explainer_plus_source` | `original_with_overlay` |
| `results_mode` | `table_plus_metrics`, `bars_plus_metrics` | `bars_plus_metrics` |
| `support_mode` | `compact_table`, `minimal_metrics`, `error_bars` | `error_bars` |
| `diagnosis_mode` | `paper_ablation_plus_cost`, `ablation_bars_cost_cards` | `ablation_bars_cost_cards` |
| `visual_style` | `conference_clean`, `editorial_dense` | `conference_clean` |
| `reading_order` | `problem_method_results`, `method_first` | `problem_method_results` |
| `text_density` | `low`, `medium` | `medium` |

### `specific_edits` (max 5 entries)

Each entry is an object with six fixed-cap string fields:

| Field | Purpose | Cap |
| --- | --- | --- |
| `target_panel` | Which panel the edit applies to (e.g. `Hero`, `Results`, `Diagnostic Evidence`, `Ablation + Cost`, `Header`, `Footer`). | 80 |
| `issue` | Specific visual problem visible in the rendered image. | 160 |
| `operation` | Concrete constrained edit (e.g. "enlarge full figure without cropping"; "convert three parallel note cards into a vertical bullet stack"; "raise this panel font size to 18px"). | 160 |
| `empty_region` | Where the unused space is: `top` / `bottom` / `left` / `right` / `around_image` / `between_blocks` / `none`. | 80 |
| `magnitude` | Concrete amount (e.g. "+20% figure height", "notes from 3 columns to 1 vertical stack", "font 14px->18px"). | 100 |
| `keep_or_drop` | Exact paper fact, figure, or text to keep or drop. | 160 |

Plain-string entries are accepted and coerced to objects with only `operation` populated.
Entries beyond the first 5 are dropped.

### Authoring Rules (from `DESIGN_PATCH_PROMPT`)

- Do not invent numbers, datasets, authors, claims, or figures.
- Do not output HTML or CSS — return JSON only.
- Every critique must contain at least three module-level operations.
- When a paper figure is too dense, prefer `hero_mode="zoomed_triptych"` (enlarged crops)
  or `explainer_plus_source` (figure plus paper-grounded readout).
- When tables are dense, prefer metric or bar summaries.
- Name where blank space lives (`top`/`bottom`/`around_image`/`between_blocks`).
- For sparse modules, give concrete font-size targets such as `16px->19px` body notes
  or `31px->36px` metric values.

### Validation Pipeline

1. `propose_design_patch()` calls the VLM with the locked content + layout payload.
2. `normalize_design_patch()` clamps enums to defaults, truncates strings, and caps
   `specific_edits` at 5.
3. The renderer reads only the normalized patch — it never sees raw VLM output.
4. After re-render, `quality_gate_report()` (in `scripts/quality_gate.py`) checks
   `layout >= 70`, `content >= 85`, `visual_judge >= 85`, `slot_relevance >= 72`.
   Any axis below threshold blocks acceptance and triggers another patch round.
