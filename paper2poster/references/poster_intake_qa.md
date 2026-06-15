# Poster Intake QA

Use this checklist before generating an academic poster. The goal is to collect
layout-critical constraints without turning intake into a long form.

## Ask Before Layout

Ask these questions before committing to the poster layout. Keep them grouped in
one short message.

1. **Poster size / aspect**
   - Ask: "What poster size or aspect ratio should I use?"
   - Common choices: `16:9 screen`, `48x36 in landscape`, `36x24 in landscape`,
     `A0 portrait`, `A0 landscape`, `A1`.
   - Default if unknown: `48x36 in landscape` for physical academic posters;
     `16:9` if the user says demo, slide, screen, online, or AAAI-style preview.

2. **Venue / presentation context**
   - Ask: "Which conference, workshop, course, or review setting is this for?"
   - Use this to tune density and tone, not to invent venue rules.
   - If the venue has strict official poster dimensions, ask the user to provide
     the rule or proceed with a clearly stated default.

3. **Author block**
   - Ask: "Should I use the authors/affiliations parsed from the PDF, anonymize
     them, or replace them with custom text?"
   - Default: use parsed title/authors/affiliations when available.
   - If the paper is blind-review or anonymous, use `Anonymous Authors` and omit
     affiliations/contact.

4. **Visual source policy**
   - Ask: "Should the poster use original paper figures, and fall back to text
     when a figure isn't poster-friendly?"
   - Default: original paper figures where they read well; text (worded
     explanation or short list) for any section whose original figure is too
     cluttered/small or missing. No figure quota — as few or as many original
     figures as the content earns, down to zero.

## Ask Only If Missing Or Ambiguous

Use these after parsing the PDF, only when the answer is not obvious.

- **Poster language:** default to the paper language or the user's language.
- **Contact / QR / website:** ask only if a contact block should be shown.
- **Branding:** ask only if the user mentions lab, project, logo, or color.
- **Reference template:** ask if the user wants to mimic a specific poster
  example; otherwise study the real posters in `references/poster_examples/` for
  the target aesthetic and design freely.
- **Audience emphasis:** ask when the paper can be pitched in multiple ways,
  e.g. method-first vs result-first vs dataset/benchmark-first.

## Compact QA Message Template

Use this when the user starts with only a PDF or "make a poster":

```text
Before I generate the poster, please confirm a few layout-critical choices:

1. Size/aspect: 16:9, 48x36 in, A0, or another size?
2. Venue/context: which conference or presentation setting?
3. Author block: use parsed authors/affiliations, anonymize, or custom text?
4. Visual policy: original paper figures, with text fallback when a figure isn't poster-friendly?

If you are unsure, I will use: 48x36 landscape, parsed authors, and original paper figures with text fallback when a figure isn't poster-friendly.
```

## Do Not Over-Ask

- Do not ask for title/authors if the PDF parser already extracted them; show
  the parsed values and ask for confirmation.
- Do not ask for exact colors unless the user cares about branding.
- Do not ask for every possible conference rule. Ask for the venue, then proceed
  with a reasonable default if no official constraint is provided.
- Do not block generation for optional fields such as email, QR code, lab logo,
  funding acknowledgments, or social links.

## Store Intake Answers

When possible, store the final answers in the generated outline under:

```json
{
  "poster_intake": {
    "size": "48x36 in landscape",
    "venue": "AAAI poster session",
    "author_policy": "parsed|anonymous|custom",
    "output_target": "html_png",
    "visual_policy": "original_figures_or_text"
  }
}
```

Downstream layout and critique agents should treat `poster_intake` as a hard
constraint unless the user later changes it.
