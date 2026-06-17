# 设计语言参考（Claude 创作 index.html 时用）

paper2html 没有固定模板——**你（Claude）亲手写 index.html**。先为这篇论文**确立一个设计概念**
（视觉范式 + 叙事主线），再据此布局，而不是套固定区块清单。不同论文（NLP / agentic-RL /
GUI-agent / systems）应当长得不一样。

## 先立概念，再布局

1. 读 `manifest.json` + `clean.md`，判断这篇论文的"气质"：是 benchmark、方法、系统、还是理论？
2. 选一种**设计语言**（下表）或自创，定下：主色（贴合领域或论文自带强调色）、结构
   （三栏网格 / 左脊柱流 / 顶部 hero）、什么元素主导视觉（架构图？结果表？一句话主张？）。
3. 不要复用"上一篇的房子风格"——若新稿和你之前做的页面雷同，是该重想的信号。

## 六种设计语言（可选其一或融合）

| 设计语言 | 适合 | 特征 |
|---|---|---|
| Editorial / 杂志风 | 叙事性强、概念新颖 | 大标题 + 衬线、栏宽留白、图文穿插 |
| Product landing / 产品落地页 | 工具 / 系统 / 有 demo | hero + 卖点卡片 + CTA 按钮、强调"能做什么" |
| Terminal / 极客技术风 | 底层系统 / 代码 / 算法 | 等宽字体、深色、命令行质感 |
| Academic poster / 学术海报 | 信息密集、多结果 | 分区色块、强标题带、一眼看完 |
| Minimal archive / 极简档案 | 经典/理论、重文本 | 黑白灰、克制、排版即设计 |
| Data dashboard / 数据看板 | 大量指标/对比表 | 卡片网格、数字突出、表格为主角 |

## 四个真实学术主页范式（结构可借鉴）

- **Nerfies** (nerfies.github.io)：居中学术 hero、紧凑链接、teaser 先于 abstract，再 video/results/BibTeX。
- **DreamFusion**：title/authors 在前，paper/project/gallery 链接，abstract 早现，examples 与 method 在下。
- **3D Gaussian Splatting**：publication 式页眉、资源链接、abstract、video/评测/可视化对比、BibTeX。
- **Segment Anything**：研究出版物层级（日期/主题）、abstract、authors、paper 链接、相关工作。

共同点：强标题带、一个主导 hero 元素、一句话主张、色块分区、慷慨留白、大字号。
