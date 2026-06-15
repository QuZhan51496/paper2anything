# Poster Examples: Individual Design Analysis

This note summarizes the poster examples in `references/poster_examples` one by one. The goal is not to copy a fixed template, but to extract reusable design behavior for Paper2Poster: how a strong academic poster creates a first-glance story, preserves reading order, handles dense evidence, and uses figures as the main carrier of meaning.

## 1. `cvpr2024_29230_poster.png`

**Topic:** RobustSAM: Segment Anything Robustly on Degraded Images.

**First-glance entry:** The poster starts with a full paper title, then immediately frames the work as a robustness problem for SAM under degraded images. The left column shows degraded visual examples before the method, so the viewer sees the task before seeing metrics.

**Reading order:** Title and affiliations at top, then left-to-right: introduction/problem, proposed method, experimental results. Inside each zone, the order is top-to-bottom.

**Main visual:** The poster has two main visual anchors: a degradation/segmentation comparison grid on the left and a large method pipeline in the center. The result tables and qualitative comparisons on the right are evidence, not the first entry.

**Information density:** Very dense. It uses large blocks of text, tables, plots, and qualitative grids, but the section headers are heavy and clear. The density works because every major block has a visible role: problem, existing solution, goal, proposed method, quantitative comparison, ablation, qualitative comparison, conclusion.

**Figure-text relationship:** Images are not decorations. The degraded image grid explains the problem; the architecture diagram explains the solution; the qualitative grid proves the solution. Text bullets provide interpretation of the figure rather than repeating the paper abstract.

**Reusable rules for Paper2Poster:**

- Put the problem visualization before the metric.
- Use one large method diagram plus one large evidence panel, not many isolated mini cards.
- Use tables only after the viewer knows what comparison is being made.
- Highlight best rows or key cells instead of extracting one detached number as the whole poster story.

**Warning for our current system:** This poster is closer to a real conference poster than our earlier sparse layouts. Our system should avoid replacing this structure with a single giant statistic.

## 2. `cvpr2024_29245_poster.png`

**Topic:** Condition-Aware Neural Network for Controlled Image Generation.

**First-glance entry:** The title states the method and task. A thin row of star-marked takeaways under the title gives three quick claims: adapt diffusion weights, select condition-aware layers, match a larger model with fewer MACs.

**Reading order:** Title, takeaway strip, then left-to-right: core idea and intuition, applying the method to diffusion transformer, comparison/results. Bottom panels continue with intuition and efficiency plots.

**Main visual:** The central method pipeline is the strongest visual anchor. The poster is method-first because the paper contribution is a mechanism. Result tables and plots are compact and placed to the right.

**Information density:** Medium-dense. It uses fewer large zones than some other posters, but each zone contains multiple visual and textual units. White space exists, but it separates dense diagrams instead of becoming empty layout.

**Figure-text relationship:** Small diagrams explain component-level differences: CAN, attention, adaptive normalization, diffusion transformer insertion. The plots then validate the efficiency claim.

**Reusable rules for Paper2Poster:**

- If the contribution is a method, make the method mechanism the main visual, not the result metric.
- A compact takeaway strip can work, but it should contain complete claims, not fragments like "<5% success".
- Use multiple small diagrams around one central pipeline to explain why the method exists.

**Warning for our current system:** A headline band can be useful, but it should summarize the paper contribution in complete language. It should not become a decorative metric card.

## 3. `cvpr2024_29809_poster.png`

**Topic:** Convolutional Prompting meets Language Models for Continual Learning.

**First-glance entry:** The poster is entered through a large title and three broad content bands: Motivation, Method, Experiments. The viewer can immediately identify the research flow.

**Reading order:** Top title, then left-to-right across large vertical zones: motivation, method, experiments. Within the motivation area, the task progression and catastrophic forgetting diagram establish the problem before the method.

**Main visual:** The left motivation schematic and central method architecture dominate. The right column uses tables and curves as evidence.

**Information density:** Very high. It has many diagrams, tables, curves, and text blocks. The density is controlled by strong colored section headers and repeated visual grammar: green headers, blue method box, red rectangles for key results.

**Figure-text relationship:** The poster repeatedly pairs a visual explanation with a short text interpretation. Result tables use red boxes to direct attention to important rows or cells.

**Reusable rules for Paper2Poster:**

- Use large semantic regions such as Motivation / Method / Experiments when the paper has a standard empirical ML structure.
- Preserve high information density by aligning many small units to a grid, rather than reducing content to a few big cards.
- Use emphasis boxes or arrows to tell the viewer what to inspect in a table.

**Warning for our current system:** Dense posters can still be readable. Our current evaluator should not reward low-density layouts just because they look clean in a thumbnail.

## 4. `cvpr2024_31412_poster.png`

**Topic:** VCoder: Versatile Vision Encoders for Multimodal Large Language Models.

**First-glance entry:** The poster uses numbered modules. The first visible module states that MLLMs struggle with object perception, supported by concrete Q&A examples. This immediately tells the viewer what failure mode is being addressed.

**Reading order:** Title, then numbered sections: problem examples, dataset, method/control adapters, evaluation setup, results. The numbering gives an explicit reading path while allowing a non-uniform layout.

**Main visual:** The main visuals are task examples and the VCoder adapter pipeline. The large tables on the right serve as quantitative proof after the task and method are clear.

**Information density:** High, but it is segmented by strong borders, vertical dividers, and numbered labels. The poster uses many screenshots, diagrams, tables, and captions.

**Figure-text relationship:** Examples do the explanatory work. The model failure examples make the motivation concrete; dataset examples define the task; pipeline diagrams explain the mechanism; tables validate the method.

**Reusable rules for Paper2Poster:**

- Add an explicit reading sequence when layout is free-form.
- Use example-driven motivation for papers about capabilities, failures, or benchmarks.
- If many modalities or inputs exist, show the actual input-output examples instead of describing them only in text.

**Warning for our current system:** Free layout needs ordering signals. Without numbers, arrows, or strong visual grouping, flexible layouts can look random.

## 5. `iclr2024_17503_poster.png`

**Topic:** Remote Sensing Vision-Language Foundation Models without Annotations via Ground Remote Alignment.

**First-glance entry:** The title names both domain and key idea. The first content block is Motivation and contains a clear problem statement: align text concepts and satellite images without paired satellite-text data.

**Reading order:** Title, then left motivation/training idea, center method overview, right results and applications, bottom takeaway/references. This is a strong left-to-right research story.

**Main visual:** The central method overview is the anchor, with a world map and image-pair examples. Results are organized as classification/retrieval, VQA, segmentation, and applications.

**Information density:** Dense but clean. It has many small images, tables, and maps, but each section has a green title bar and a predictable internal layout.

**Figure-text relationship:** Figures connect the paper's core analogy: satellite images are aligned through ground images and text. The applications section shows why the method matters beyond benchmark tables.

**Reusable rules for Paper2Poster:**

- For domain-transfer or dataset papers, show the data bridge visually.
- Put applications near the results if they help the viewer understand value.
- End with a short takeaway bar that states the contribution in one or two bullets.

**Warning for our current system:** The central diagram should often be a data/method bridge, not necessarily a neural network architecture.

## 6. `iclr2024_17798_poster.png`

**Topic:** The Truth is in There: Improving Reasoning in Language Models with Layer-Selective Rank Reduction.

**First-glance entry:** The poster is organized as a sequence of research questions. Each section header starts with "Q.", which turns the poster into a guided investigation.

**Reading order:** Top title, then question panels from left to right and top to bottom. The viewer follows: how do models reason, how broadly does the method work, which data improves, how much can models be compressed, what do matrix components store, and whether the idea extends.

**Main visual:** The left method diagram and multiple charts/tables are co-anchors. There is no single hero graphic; instead, the poster works as a dense evidence map.

**Information density:** Very high. It uses compact charts, tables, method diagrams, and short interpretive captions. The light-blue question strips keep the structure readable.

**Figure-text relationship:** Every chart has an adjacent sentence explaining the conclusion. This is important: the viewer is not forced to infer the message from raw plots alone.

**Reusable rules for Paper2Poster:**

- Use question-style section titles when the paper is analytical or diagnostic.
- Pair every plot/table with a one-sentence interpretation.
- Let multiple evidence panels coexist when no single visual can summarize the whole paper.

**Warning for our current system:** For theory/analysis papers, forcing one central pipeline can be wrong. The layout agent should choose an evidence-map structure when the paper's story is a sequence of findings.

## 7. `iclr2024_18118_poster.png`

**Topic:** Understanding Certified Training with Interval Bound Propagation.

**First-glance entry:** A large dark left rail states the thesis in oversized text: the work theoretically analyzes IBP and introduces a new metric. This gives a direct "what this paper does" signal before the technical details.

**Reading order:** Title on top, large thesis rail on the left, then technical explanation and results to the right. The right side is read top-to-bottom in columns, with formulas, diagrams, plots, and tables.

**Main visual:** The main design device is not a single figure but a thesis rail plus technical panels. It is effective for a theory-heavy paper because it separates the human-readable claim from the dense math.

**Information density:** Mixed. The left rail is sparse and dramatic; the right side is dense. This contrast makes the poster approachable without removing technical content.

**Figure-text relationship:** Mathematical definitions and diagrams sit next to result plots. The visual style helps distinguish "claim summary" from "technical evidence".

**Reusable rules for Paper2Poster:**

- For theory papers, create a left-side thesis rail or summary strip that states the contribution plainly.
- Keep the technical panels dense enough for expert readers.
- Use visual contrast to separate high-level claim from proof/results.

**Warning for our current system:** Sparse space can be useful only when it has a clear rhetorical role. Empty space without a thesis is just wasted poster area.

## 8. `iclr2024_18324_poster.png`

**Topic:** A Simple Interpretable Transformer for Fine-Grained Image Classification and Analysis.

**First-glance entry:** The title states the method and task. The left "Highlights" block then gives the key idea with example images, arrows, and emphasized terms.

**Reading order:** Title, left highlights and method, center results/analysis, right additional interpretation and comparisons. The dashed vertical separators create three major reading columns.

**Main visual:** The strongest visuals are heatmap grids and image comparison panels. The method diagram is large enough to explain the architecture, but the result visuals dominate because interpretability is the paper's selling point.

**Information density:** High. There are many image grids, heatmaps, comparisons, and charts. The density is controlled through dashed separators, bold red method name, and repeated grid structures.

**Figure-text relationship:** The poster uses figures to show interpretability directly. Heatmaps, trait rows, image edits, and comparison grids are more persuasive than a table alone.

**Reusable rules for Paper2Poster:**

- If the paper's contribution is visual or interpretability-focused, use qualitative grids as primary evidence.
- Use color emphasis on key terms, but keep the overall palette consistent.
- Use vertical separators when the poster has three parallel evidence streams.

**Warning for our current system:** For visual papers, cropping and enlarging representative qualitative examples is more important than showing full-size raw paper figures.

## Cross-Poster Design Patterns

Across these examples, strong posters usually follow these principles:

1. **The title is the real title, not a marketing slogan.** The poster may add claims under the title, but it does not replace the paper title with a metric.
2. **The first content region explains the task or problem.** Viewers should know what the work is about before seeing a result number.
3. **The main visual is selected by paper type.** Method papers use a pipeline; benchmark/data papers use task/data examples; theory papers use a thesis rail plus evidence panels; visual papers use qualitative grids.
4. **Results are evidence, not the whole story.** Tables, plots, and metrics usually appear after motivation and method.
5. **Dense is acceptable when structured.** Top-conference posters often contain 10-20 content units. They stay readable through section bars, numbered flow, question headers, dividers, captions, and visual emphasis.
6. **Every figure needs a job.** Figures either explain the problem, explain the method, show data, prove a result, or demonstrate an application.
7. **Reading order must be visible.** Free layout still needs ordering signals: numbered sections, aligned bands, question strips, arrows, or strong left-to-right zoning.
8. **Tables need local interpretation.** Good posters highlight rows/cells and add a short caption explaining the takeaway.
9. **Whitespace is rhetorical, not decorative.** Sparse space works only when it creates a thesis rail, separates zones, or improves readability around a major visual.
10. **The poster should be glanceable and inspectable.** It needs a fast story at 3 seconds and enough dense material for close reading.

## Implications for Paper2Poster

The layout/design agent should not choose from one rigid template. It should first classify the paper story type:

- **Method contribution:** problem/examples -> central method pipeline -> experiments.
- **Benchmark/dataset contribution:** motivation -> task/data construction -> representative examples -> benchmark results -> limitations/takeaway.
- **Theory/analysis contribution:** thesis rail -> definitions -> finding sequence -> plots/tables -> conclusion.
- **Visual/interpretability contribution:** task examples -> method diagram -> qualitative grids -> quantitative support.
- **Application/domain contribution:** domain problem -> data bridge -> method -> application panels -> evidence.

The critique agent should explicitly penalize:

- metric-first posters where viewers cannot tell the task,
- sparse dashboard layouts with too few content units,
- shuffled reading order,
- raw paper figures pasted too small to read,
- tables without highlighted takeaway,
- missing local captions for plots/figures,
- decorative whitespace that does not support a visual story.
