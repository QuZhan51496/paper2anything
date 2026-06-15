# Academic Poster Design Guide

## Research Summary

Based on analysis of 50+ academic poster templates from:
- bolei_awesome_posters (CVPR/NeurIPS/ECCV posters)
- SuperBruceJia/Poster_Template (15 templates across CVPR/ECCV/MMSP)
- PosterNerd (26 templates, 5 aspect ratios each)
- PosterPresentations.com (13 designs, 20+ sizes)
- Better Poster / Posters 2.0 (Mike Morrison's billboard format)

---

## Layout Archetypes

### 1. Traditional 3-Column (most common, ~70% of conference posters)
- Equal-width columns with 0.4-0.6" gaps
- Full-width title banner at top (12-18% of height)
- Sections flow top-to-bottom within each column
- Optional full-width conclusion/footer at bottom

### 2. Better Poster / Billboard (trending, ~15%)
- Large center panel with ONE key finding in large text
- Narrow left sidebar: methods/approach
- Narrow right sidebar: results/details
- Proportions: 25% | 50% | 25%
- Center panel uses dark background with white text

### 3. Two-Column Wide (common for methods-heavy papers)
- Two wider columns, sometimes with a narrow sidebar
- Better for papers with large diagrams/architectures

### 4. Asymmetric (rare but striking)
- One wide column (60%) + one narrow column (40%)
- Wide column for main results, narrow for methodology

---

## Visual Hierarchy Rules

### Font Size Hierarchy (48x36 inch poster, readable at 1-2m)
| Element | Size | Weight |
|---------|------|--------|
| Title | 72-96pt | Bold |
| Authors | 36-48pt | Regular |
| Affiliations | 28-36pt | Light/Italic |
| Section Headers | 44-56pt | Bold |
| Body Text | 28-36pt | Regular |
| Captions | 22-28pt | Italic |
| References | 20-24pt | Regular |

### Spacing
- Outer margin: 0.6-1.0 inches
- Column gap: 0.4-0.6 inches
- Section gap (vertical): 0.3-0.5 inches
- Internal padding: 0.3-0.5 inches
- Line spacing: 1.2-1.4x body font size

---

## Color Usage Patterns

### Title Bar
- Always uses primary/darkest color as background
- White or very light text for contrast
- Spans full width of poster

### Section Headers
- Two styles equally popular:
  - **Colored bar**: Secondary color background, white text
  - **Text-only**: Colored text (primary/secondary) on white/light background, with underline or bottom border
- Rounded corners (4-8px radius) on colored bars are trending

### Section Bodies
- Light background (#F5F7FA to #FFFFFF)
- Subtle border (1-3pt) in secondary color OR no border with shadow
- Alternatively: white cards on a tinted background

### Accent Colors
- Used for bullet markers, highlights, figure borders
- Should contrast with both primary and secondary

### Popular Academic Palettes
1. **Deep Blue** (CS/AI): #1B3A5C / #2E86AB / #A3D5FF
2. **Teal Academic**: #004D40 / #00897B / #B2DFDB
3. **Royal Purple** (Theory): #1A237E / #5C6BC0 / #C5CAE9
4. **Forest Green** (Bio): #1B5E20 / #43A047 / #A5D6A7
5. **Warm Professional**: #BF360C / #E64A19 / #FFCCBC

---

## Figure Placement Best Practices

1. **Stacked below text** (recommended for narrow columns)
   - Text takes upper 50-60%, figure takes lower 40-50%
   - Works best when column width < 15 inches

2. **Side-by-side** (for wide sections or 2-column layouts)
   - Text 55-60%, figure 40-45% with small gap
   - Only when section width > 14 inches

3. **Full-width figure** (for architecture diagrams)
   - Spans the entire section width
   - Caption below, 22-28pt italic

4. **Figure grid** (for results with multiple sub-figures)
   - 2x2 or 1x3 arrangement
   - Uniform sizing with shared caption

---

## Section Organization Patterns

### Standard Academic Flow (Left → Middle → Right)
| Left | Middle | Right |
|------|--------|-------|
| Introduction/Motivation | Method/Approach | Results |
| Background/Related Work | Architecture/Pipeline | Analysis/Ablation |
| Problem Statement | Implementation | Conclusion |

### Alternative: Problem-Solution-Evidence
| Left | Middle | Right |
|------|--------|-------|
| Problem & Motivation | Our Solution | Evidence & Impact |
| Background | Technical Details | Experiments |
| | | Future Work |

---

## Modern Design Trends (2024-2026)

1. **Flat design**: No gradients, clean solid colors
2. **Card-based sections**: White cards with subtle shadows on tinted background
3. **Generous whitespace**: Less content, more breathing room
4. **Icon bullets**: Small icons instead of bullet points
5. **Rounded corners**: 6-12px on section boxes
6. **Accent lines**: Thin colored lines as separators
7. **QR codes**: Bottom-right for paper link/code repo
8. **Logo placement**: Top-left or top-right of title bar

---

## Template Styles for paper2poster

### Style A: "Classic Academic" (default)
- 3-column equal width
- Colored title bar (primary) + colored section header bars (secondary)
- White section bodies with thin border
- Clean, professional, conference-standard

### Style B: "Modern Card"
- 3-column on light gray (#F0F2F5) background
- White section cards with rounded corners + subtle shadow
- Section headers: bold colored text with bottom accent line (no bar)
- More whitespace, contemporary feel

### Style C: "Billboard / Better Poster"
- Large center panel (50% width) with key finding
- Two narrow sidebars (25% each) for details
- Center: dark background, large white text
- Sidebars: standard academic sections
