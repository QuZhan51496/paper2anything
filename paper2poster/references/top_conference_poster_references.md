# Top-Conference Poster Reference Set

This file collects public poster-gallery entry points and representative poster
pages for improving Paper2Poster's layout critic and visual curator. Use these
as design references only; do not copy artwork, figures, or layouts verbatim.

## Gallery Entry Points

- NeurIPS 2024 poster gallery: https://neurips.cc/virtual/2024/events/poster
- ICLR 2024 virtual posters: https://iclr.cc/virtual/2024/papers.html
- ICML 2024 virtual posters: https://icml.cc/virtual/2024
- CVPR 2024 virtual posters: https://cvpr.thecvf.com/virtual/2024

## Representative Posters To Inspect

### NeurIPS 2024

- Extending Video Masked Autoencoders to 128 frames
  https://neurips.cc/virtual/2024/poster/94502
- TuneTables: Context Optimization for Scalable Prior-Data Fitted Networks
  https://neurips.cc/virtual/2024/poster/95977
- Personalized Steering of Large Language Models
  https://neurips.cc/virtual/2024/poster/96424
- Improved off-policy training of diffusion samplers
  https://neurips.cc/virtual/2024/poster/93194
- Spectral Editing of Activations for Large Language Model Alignment
  https://neurips.cc/virtual/2024/poster/93529
- Enhancing Consistency-Based Image Generation via Adversarially-Trained Classification
  https://neurips.cc/virtual/2024/poster/93288
- Identifying General Mechanism Shifts in Linear Causal Representations
  https://neurips.cc/virtual/2024/poster/93955
- Infinite-Dimensional Feature Interaction
  https://neurips.cc/virtual/2024/poster/93089
- Policy Improvement using Language Feedback Models
  https://neurips.cc/virtual/2024/poster/95969
- Synthetic Programming Elicitation for Text-to-Code
  https://neurips.cc/virtual/2024/poster/93893
- End-To-End Causal Effect Estimation from Unstructured Natural Language Data
  https://neurips.cc/virtual/2024/poster/94106

### ICLR 2024

- Eureka: Human-Level Reward Design via Coding Large Language Models
  https://iclr.cc/virtual/2024/poster/18971
- A Simple and Effective Pruning Approach for Large Language Models
  https://iclr.cc/virtual/2024/poster/18687
- Take a Step Back: Evoking Reasoning via Abstraction in Large Language Models
  https://iclr.cc/virtual/2024/poster/19503
- True Knowledge Comes from Practice
  https://iclr.cc/virtual/2024/poster/18102

### ICML 2024

- CoLoRA: Continuous low-rank adaptation for parameterized PDEs
  https://icml.cc/virtual/2024/poster/33364
- Iterated Denoising Energy Matching for Sampling from Boltzmann Densities
  https://icml.cc/virtual/2024/poster/33422

### CVPR 2024

- AV2AV: Direct Audio-Visual Speech to Audio-Visual Speech Translation
  https://cvpr.thecvf.com/virtual/2024/poster/30182
- On Scaling Up a Multilingual Vision and Language Model
  https://cvpr.thecvf.com/virtual/2024/poster/31319
- End-to-End Spatio-Temporal Action Localisation with Video Transformers
  https://cvpr.thecvf.com/virtual/2024/poster/30052
- WinSyn: A High Resolution Testbed for Synthetic Data
  https://cvpr.thecvf.com/virtual/2024/poster/31741
- MMCert: Provable Defense against Adversarial Attacks to Multi-modal Models
  https://cvpr.thecvf.com/virtual/2024/poster/30936

## Design Patterns To Extract

Use these patterns to improve the Critic and Visual Curator agents:

- Reading path: title -> one-sentence claim -> dominant visual -> supporting evidence -> takeaway.
- One dominant visual: strong posters usually avoid five equally weighted panels.
- Result compression: dense result tables should become metric cards plus a smaller evidence table.
- Figure hierarchy: method/result figures should be visibly larger than explanatory text panels.
- Text budget: side panels should have short labels and 1-2 bullets, not abstract-style paragraphs.
- Visual grouping: related sections should be spatially grouped instead of alternating left/right.
- Headline strength: the hero number should be paired with a short claim, not surrounded by empty space.
- Evidence-before-conclusion: conclusions should not visually precede the main evidence.

## Proposed Critic Metrics

- `reading_order_score`: does the eye path match a human poster-reading sequence?
- `hero_visual_score`: is the main figure/result large enough and early enough?
- `evidence_legibility_score`: can the key evidence be read without zooming?
- `text_budget_score`: are side panels concise enough?
- `visual_grouping_score`: are related panels grouped, or does the layout zig-zag?
- `headline_score`: does the headline communicate the central claim in one glance?
- `template_penalty`: does the poster look like evenly filled boxes rather than designed hierarchy?
