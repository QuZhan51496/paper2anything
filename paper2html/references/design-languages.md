# Design language reference (for when you author index.html)

paper2html has no fixed template — **you hand-author index.html**. First **establish a design concept**
for this paper (visual paradigm + narrative throughline), then lay it out from there, rather than filling
a fixed checklist of blocks. Different papers (NLP / agentic-RL / GUI-agent / systems) should look different.

## Concept first, layout second

1. Read `manifest.json` + `clean.md` and judge this paper's "character": is it a benchmark, a method, a system, or theory?
2. Pick a **design language** (table below) or invent one, and settle: primary color (matched to the field or
   the paper's own accent color), structure (three-column grid / left-spine flow / top hero), and which element
   leads the visuals (the architecture diagram? the results table? a one-line claim?).
3. Don't reuse "the house style of the last paper" — if the new draft looks like a page you made before, that's a signal to rethink.

## Six design languages (pick one or blend)

| Design language | Fits | Traits |
|---|---|---|
| Editorial / magazine | Strong narrative, novel concept | Big headline + serif, column whitespace, text-image interplay |
| Product landing | Tool / system / has a demo | Hero + selling-point cards + CTA buttons, emphasizes "what it does" |
| Terminal / hacker-technical | Low-level systems / code / algorithms | Monospace, dark, command-line feel |
| Academic poster | Information-dense, many results | Zoned color blocks, strong title band, scannable at a glance |
| Minimal archive | Classic/theory, text-heavy | Black-white-gray, restrained, typography is the design |
| Data dashboard | Many metrics / comparison tables | Card grid, numbers stand out, tables as the lead |

## Four real academic-homepage exemplars (structure worth borrowing)

- **Nerfies** (nerfies.github.io): centered academic hero, compact links, teaser before abstract, then video/results/BibTeX.
- **DreamFusion**: title/authors up top, paper/project/gallery links, abstract early, examples and method below.
- **3D Gaussian Splatting**: publication-style header, resource links, abstract, video/eval/visual comparisons, BibTeX.
- **Segment Anything**: research-publication hierarchy (date/topic), abstract, authors, paper link, related work.

Common ground: a strong title band, one dominant hero element, a one-line claim, color-block zoning, generous whitespace, large type.
