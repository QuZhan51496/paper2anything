# Outline Heuristics

Stage 3 的 Claude 把 `paper_meta.json` 转成 `slide_outline.json` 时使用的映射规则
与判断准则。本文件不是机械替换表——是给"理解论文 + 决策"用的脚手架。

## 总目标

覆盖论文的**核心叙事**（不是"按章节复述"）：**问题→方法→证据→结论**。
张数**默认**由叙事完整性决定：每个叙事节点该占几张就占几张，宁可多一张让单页
充实有呼吸感，也不要把内容硬塞进固定页数。学术 talk 典型 12-20 分钟、每张
1-2 分钟可作节奏参考，但**不是要去凑的指标**。

### 页数档（`config.json/deck_length_target`）

Stage 0.5 让用户选了页数档，Stage 3 进来前先读 `config.json/deck_length_target`：

- **`null`（`自动` 档）**：上一段所述——张数纯由叙事+版面定，不设上下限。
  保持现状，本节其余约束不生效。
- **非 `null`（`精简` `[8,12]` / `标准` `[13,18]` / `详尽` `[19,28]`）**：把这个
  区间当作**大纲粒度的软目标**，靠两个杠杆向目标带靠拢——
  1. **可选角色含不含**：`background` / `discussion` / 第二张 `result`（ablation）/
     `qna` 这些"否/可选"角色，详尽档多留、精简档多砍。
  2. **`method` / `result` 拆几张**：详尽档把复杂 method 拆 3–4 张、每个关键
     创新单独一张；精简档合并到 1–2 张总览。

  这是**软**目标：叙事完整性优先于落进区间。落不进就贴边，并在心里有数下一步
  Stage 4 每页仍要被内容填满。**绝不**为压进精简档而砍**必含**核心角色
  （`title`/`introduction/motivation`/`method`/`experiment`/`result`/`conclusion`），
  也**绝不**为撑进详尽档把一个点稀释成半页留白——页数档只调"内容切多细"，
  **不**改每页"空间驱动、无留白无溢出"（见下方"内容塑形规则"与
  [design-style.md](design-style.md) 0.4 节）。

## 角色 → 必含性与顺序

每个角色按内容该占几张就占几张（复杂 method 可拆多张，简单论文可合并）；选了
非 `自动` 档时，"否/可选"角色含不含与 method/result 拆分细度按上方
[页数档](#页数档configjsondeck_length_target)向目标带调节。下表只规定哪些角色
**必含**（任何档位都不能砍）与典型顺序：

| 角色 | 必含？ | 说明 |
|---|:-:|---|
| `title` | 是 | 第一张。论文标题、作者、（venue/year 可选） |
| `tldr` | 否 | 紧跟 title。论文的"一句话总结 + 核心贡献"，让听众 30 秒抓重点 |
| `introduction` / `motivation` | 是 | 当前问题是什么、为什么难、之前方法的不足（内容多可拆多张）|
| `background` | 否 | 论文有 Related Work / Preliminaries 且对理解 method 必需时才加。无脑加 == 浪费时间 |
| `method` | 是 | 核心。high-level 总览 + 关键创新；方法复杂就拆多张，别硬塞一张 |
| `experiment` | 是 | 实验设置：数据集、baseline、metric |
| `result` | 是 | 主结果（必含）+ ablation/分析（可选，按需多张）|
| `discussion` | 否 | 当论文 Discussion / Limitations 章节有重要 take-away 时加 |
| `conclusion` | 是 | 总结贡献 + 未来工作 |
| `qna` | 否 | 仅大型 talk 加；通常省略 |

**典型顺序**：`title → (tldr) → introduction/motivation → (background) → method… → experiment → result… → (discussion) → conclusion → (qna)`。

## 论文 section → slide 角色映射

不是 1:1，是 N:M 的内容重组：

| paper_meta.json 的 section.kind | 主要喂给的 slide role |
|---|---|
| `abstract` | `tldr`（取核心贡献）+ `title` 的副标题候选 |
| `introduction` | `motivation`（前 2/3）+ `tldr`（后 1/3 的 contributions）|
| `background` / `related` | `background`（最多 1 张；多数情况省略，只在 method 解释时穿插一两句）|
| `method` | `method` 全部 slide，按子节聚合主体（如 architecture / loss / training）|
| `experiment` | `experiment` slide |
| `result` | `result` slide（main results + ablation 各一张） |
| `discussion` | `discussion`（仅当 Discussion/Limitations 有强结论时）|
| `conclusion` | `conclusion` |
| `references` | **跳过**（不要做成 reference dump 的 slide） |

## 每个角色的内容指南

### `title`
- `title`：用 `paper_meta.json/title` 校核后的标题
- `bullets`：留空 `[]`（标题页只有标题、副标题、作者）
- 在 `slide_spec.json` 里通常以 dark 配色 + 大标题 + 作者居中或左对齐
- `speaker_notes`：欢迎语 + 1 句论文亮点

### `tldr`
- `title`：诸如 "TL;DR" / "Key Contributions" / "What We Did"
- `bullets`：论文的核心贡献，**动词开头**（"Propose ...", "Show that ...", "Achieve ..."）。
  来源：abstract 末尾 + introduction 的 contributions 列表
- `needs_figure`：通常 false（除非有一张极简的"main result"图）

### `introduction` / `motivation`
- `title`：诸如 "The Problem" / "Why This Matters" / "Limitations of Prior Work"
- `bullets`：先说现状（"现有 X 方法依赖 Y"），再说不足（"Y 的代价是 Z"），引向"我们需要 ..."
- `needs_figure`：可选；论文有"问题图"（before/after、典型失败 case）时强烈推荐
- 来源：`introduction` 的前半部分

### `background`（可选）
- 仅当论文 method 强依赖某个先验概念（如 Diffusion Model 的 forward/reverse process）时才加
- 优先用图说明（如公式/流程图），少用文字定义
- 不要把 Related Work 做成 background——Related Work 该融入 motivation 或省略

### `method`（2-3 张）
- 第一张：**架构总览**。`needs_figure: true`，`figure_ref` 指向 paper 的"主图"（通常是 Figure 1 或 Figure 2 的整体架构）
- 第二张：**关键创新**。论文的 novelty 集中在哪个组件？把那个组件单独讲清楚（如 Transformer 论文的"Scaled Dot-Product Attention"）
- 可选第三张：**训练/优化策略**（如有非平凡的 loss / data augmentation / curriculum）
- bullets 简短，公式用图替代而非 inline LaTeX

### `experiment`
- `title`：诸如 "Experimental Setup"
- `bullets`：**数据集**、**baseline**、**metric**、**硬件/规模**
- `needs_figure`：通常 false；如果论文 datasets 表格简洁可用 image
- 来源：`experiment` 章节

### `result`（1-2 张）
- 第一张 main results：`needs_figure: true`，配论文的主 result table（用 `page_renders` 整页裁剪即可——表格做成 PptxGenJS table 太繁琐）
- 第二张（可选）ablation / analysis：用最有说服力的 1-2 个 ablation 图
- bullets：**用数字**说话，"+3.5 BLEU on EN-DE"，避免泛泛的"显著提升"

### `discussion`（可选）
- `bullets`：包含一条 **limitation**（这非常加分，听众一眼看出做研究的诚实度）
- 来源：`discussion` 章节

### `conclusion`
- `title`：诸如 "Conclusions" / "Takeaways"
- `bullets`：通常涵盖——我们做了什么（一句）、关键结果（带数字）、未来工作（一句）
- 来源：`conclusion` 章节 + `tldr` 的反向呼应

### `qna`（可选）
- 纯文本"Questions?" + 联系方式
- 大多数 conference talk 不需要单独 Q&A slide

## 内容塑形规则

- **文字量由版面决定，不设词数上限**。Stage 3 写 bullets 时心里有数：每页最终
  要被"视觉元素 + 文字"填满——不留白也不溢出；**先想这页配什么视觉，剩下空间
  用文字补到刚好充实，不要预先把内容砍到撑不起一页**。下限/上限、字号红线、
  **每页必须有视觉元素（无纯文字页）** 等空间驱动细则的单一权威在
  [design-style.md](design-style.md) §4（+ 0.4 节空间检查闭环），Stage 4 据此
  最终填充，本节不复述
- **bullet 是提炼后的要点，不是搬运**（Stage 3 写 bullets 的直接准则）：禁整段
  抄摘要、禁完整句号 + 长定语堆叠；"够不够短"由"是不是一个清晰单点"判断，不由
  数词。完整原则见 [design-style.md](design-style.md) §4
- **不重复 slide title 出现在 bullet 里**（title 是 "Method"，bullet 别再写 "Our method..."）
- 数字必带单位/对照（"+3.5 BLEU vs. baseline"），不说空泛的"显著提升"
- speaker_notes：讲者的**口播草稿**（不是冗长背景），让讲者照念也流畅

## 图与 slide 的配对（`figure_ref` 怎么填）

`paper_meta.json/figures[]` 里每个 figure 都有 `id`、`page`、`caption`。配对策略：

1. **method 第一张 → 论文 Figure 1 或 Figure 2**（绝大多数论文的"主架构图"）
2. **result 主图 → 论文 result 章节的最大 figure 或 main table**（看 `figures` / `tables` 的 caption 里有没有 "main results" 等）
3. **motivation → 选有 before/after、failure cases 的图**（caption 里有 "examples"、"comparison"、"motivating"）
4. **ablation slide → 选 caption 含 "ablation"、"effect of"、"varying" 的 figure**
5. 不放心时优先用 `pages/page-NN.png`（整页渲染）而非 `embedded_images`——后者可能是矢量图分解后的碎片

`figure_ref` 写论文里的 figure id（如 `"figure2"`），让 Stage 4 的 Claude 决定具体怎么用（嵌入 vs. 整页裁）。

> **bbox 是 Stage 4 的事**：当 `figures_index.json/captions[i]` 已带 `bbox` 字段（脚本检出的精确表格边界），Stage 4 会直接用；缺失才走视觉估算。Stage 3 不需要操心 bbox，只填 `figure_ref` 即可。

> **公式同理**：mineru 后端会填 `paper_meta.equations[]`，每张 slide 也可填 `equation_ref: "eq_5"`（与 `figure_ref` 平行），Stage 4 据此决定 Unicode rewrite / 裁原图 / 仅入 speaker_notes。详见 `references/design-style.md` 的公式段。

> **附录 vs 正文（重要）**：每个 `figures[i]` / `tables[i]` / `equations[i]` 带 `is_appendix: bool` 字段。**Stage 3 默认只挑 `is_appendix == false` 的条目**——附录里的 figure（如 attention 论文 Figure 3-5 在 References 之后的 attention 可视化）通常是补充材料，标准 deck 通常不展示。例外：长篇 keynote、补充材料 talk、或 Claude 判断附录某 figure 对叙事关键时，可以显式挑 `is_appendix == true` 的条目，并在 speaker_notes 注明 "from appendix"。判定规则简单：page 在 References 章节之后即标 appendix；详见 `references/schemas.md` 的相关 Addendum。

## 受众适配（`audience` 字段）

- `researchers`：术语保留，bullets 可以技术性强；speaker_notes 简洁
- `general`：术语先解释；用比喻；ablation slide 通常省略
- `mixed`：method 部分 high-level；ablation 留 1 张但讲得通俗

## 当 paper_meta 不够用时

短期阶段，paper_meta 由启发式生成，会有：
- 标题抓错（首页 license 干扰）
- 章节边界错位（method 被切碎）
- abstract 含连字符污染

进入 Stage 3 之前先做 [schemas.md](schemas.md) 末尾"Claude 在 Stage 3 进入前应做的修订"列表里的 4 项校核。**校核结果不写回 paper_meta.json**，但用校核后的理解生成 outline。

---

> **Stage 4 视觉一致性硬规则**（字号 deck 内一致 / 孤词避免 / 图等比缩放 / 元素均衡分布）见 [design-style.md](design-style.md) 的 "0. 视觉一致性硬规则" 节，**先于所有其他设计建议遵守**。
