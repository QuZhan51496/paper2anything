---
name: paper2slides
description: "Turn an academic paper PDF into a presentation deck (.pptx) end-to-end. Use this skill whenever the user wants to \"make slides from a paper\", \"generate a deck from this PDF\", \"把这篇论文做成 PPT\", \"生成幻灯片\", \"做一个 PPT\", or supplies a research paper PDF and asks for a .pptx out. Trigger even when the user only says \"deck this paper\" or \"summarize as slides\". This skill is the orchestrator for academic paper to deck flows; invoke it instead of going to `pptx` or `pdf` skills directly when the upstream is a research paper."
---

# paper2slides

把一篇学术论文 PDF 转成可演讲的 .pptx。这是协调器 skill：自己**不**重新实现 PDF
解析或 PPT 渲染，而是按"论文 → 大纲 → 渲染"的流水线编排，**调用官方 `pdf` skill
与 `pptx` skill** 的能力。

## Quick Reference

| 阶段 | 输入 | 产物 | 责任方 |
|---|---|---|---|
| 0.5. configure | 用户对话 | `<workdir>/config.json` | **你**（AskUserQuestion 三项确认：页数档 + 是否做视觉 QA + 配色）|
| 1. extract    | `paper.pdf` | `paper_meta.json` + `figures_index.json` + `figures/` + `pages/` + `equations` + 高清 figure/table 裁图（MinerU 云 API 一次性产出）| `scripts/extract_paper.py` |
| 2. outline    | `paper_meta.json` | `slide_outline.json` | **你**（按 `references/outline-heuristics.md`）|
| 3. spec       | `slide_outline.json` + 图 | `slide_spec.json` | **你**（按 `references/design-style.md`） |
| 4. render     | `slide_spec.json` | `output.pptx` | `scripts/render_pptx.py`（PptxGenJS 桥）|
| 5. qa         | `output.pptx` | pass / fail + 修复列表 | content QA 始终跑；**视觉 QA 由 Stage 0.5 的 `config.json/visual_qa` 门控**|

阶段详细协议见 `references/pipeline.md`。

## Invocation Contract

调用形式：

```
/paper2slides <paper.pdf> [output.pptx] [--from-stage <name>] [--force]
```

- `output.pptx` 缺省 → `<paper-dir>/<paper-stem>.pptx`，重名自动 `-v2 -v3`
- 中间产物落在 `<paper-dir>/.paper2anything/slides/<paper-stem>/`，论文目录只读时回退到 `~/.cache/paper2anything/slides/`

**Python 环境**：所有脚本跑在 `paper2anything` conda 环境。命令前缀
`conda run -n paper2anything --no-capture-output python -m scripts.<name> ...`
（已 `conda activate paper2anything` 时可省前缀）。前缀省略约定见
[references/pipeline.md](references/pipeline.md) §通用约定。

**第一步永远是解析 workspace**：

```bash
conda run -n paper2anything --no-capture-output python -m scripts.workdir resolve \
    <paper.pdf> [--output <out.pptx>] --ensure
```

返回的 JSON 包含所有命名路径（`paper_meta_path`, `slide_outline_path`,
`slide_spec_path`, `figures_dir`, ...）和各阶段的完成状态。后续所有阶段都引用
这个 JSON 里的路径，**不要自己拼路径**——规则统一在 `scripts/workdir.py` 里。

**重跑语义**：

| 标志 | 含义 |
|---|---|
| 默认 | 已完成的阶段跳过（按产物文件存在判定）|
| `--force` | 忽略所有 marker，全跑 |
| `--from-stage <name>` | 从指定阶段开始重跑（长期"交互模式"的入口）|

`<name>` ∈ `{configure, extract, outline, spec, render, qa}`。
**重新走一遍开工前三项询问**用 `--from-stage configure`（覆盖旧 `config.json`）。

## Pipeline

按下面的顺序执行。每阶段都有"完成判定"——产物文件出现即算完成，重跑时自动跳过。
**本节每阶段只写三件事：(a) 该 do 的最小动作（含要敲的命令）、(b) 一条最易翻车
的关键陷阱、(c) 指向 [references/pipeline.md](references/pipeline.md) 对应 Stage 的
指针**。完整协议、前置依赖、常见错误、边界情况一律在 pipeline.md，本节不复述。

### Stage 0.5 — Configure（你，AskUserQuestion 三项确认）

Stage 0 解析完 workspace 后、Stage 1 之前，用 [AskUserQuestion] 与用户确认三项，
答案 Write 到 Stage 0 JSON 的 `config_path`（`<workdir>/config.json`）：

1. **`deck_length`**：精简 / 标准 / 详尽 / 自动（不设页数目标，推荐）
2. **`visual_qa`**：`true`（默认，加 soffice→jpg→子代理 视觉闭环）/ `false`（只跑便宜 content QA）
3. **`color_scheme`**：`自动`（默认，Stage 3 按论文气质匹配 palette）/ `自定义`（用户一句话描述偏好，存进 config 由 Stage 3 解析）

- **复用即跳过**：`config.json` 已存在且未带 `--from-stage configure` / `--force` 时不再问，沿用上次配置。
- 用户初始请求已表达偏好时把对应项设为 AskUserQuestion 首选项（仍展示确认）。
- 完整选项表、`deck_length` 页数带映射、预填与下游消费细则见 [references/pipeline.md](references/pipeline.md) §Stage 0.5；config.json schema 见 [references/schemas.md](references/schemas.md)。

### Stage 1 — Extract（脚本）

**走 MinerU 云 API**（必填 `MINERU_API_TOKEN`，统一在 paper2anything 包根 `.env` 配置；无 token 直接报错）：

```bash
set -a; source <paper2anything 包根>/.env; set +a   # 导出统一 .env（含 MINERU_API_TOKEN）
conda run -n paper2anything --no-capture-output python -m scripts.extract_paper <paper.pdf>
```

一次性产出 `paper_meta.json` + `figures_index.json` + `pages/` + 高清裁图（结构化元数据由 MinerU 直接给出）。

`--dpi` 调节（默认 300）、MinerU 解析的已知不完美（如 bbox 偶把 `y` 起点压在子图标题上），见
[references/pipeline.md](references/pipeline.md) §Stage 1。

> **陷阱**：进 Stage 2 前你 **必跑** [references/schemas.md](references/schemas.md) 末尾的
> **4 项校核**（title/authors/同 kind 合并/缺关键 kind）核对 `paper_meta.json`，**校核结果不写回
> `paper_meta.json`**，直接体现在 Stage 2 的 outline 里。

### Stage 2 — Outline（你）

输入 `paper_meta.json` + `figures_index.json` + `config.json` → 产物
`slide_outline.json`（schema 见 [references/schemas.md](references/schemas.md)）。
按 [references/outline-heuristics.md](references/outline-heuristics.md) 定角色与
顺序、写每张 `title`/`bullets`/`figure_ref`/`speaker_notes`。**陷阱**：先读
`config.json/deck_length`——`自动` 不约束张数；非自动是**大纲粒度软目标**，
**不得**为凑数砍核心叙事角色（细则见 outline-heuristics.md）。

写完用 Python 验证 JSON 合法：

```bash
conda run -n paper2anything --no-capture-output python -c \
    "import json,sys; json.load(open(sys.argv[1])); print('ok')" \
    <workdir>/slide_outline.json
```

完整协议与常见错误见 [references/pipeline.md](references/pipeline.md) §Stage 2。

### Stage 3 — Spec（你）

输入 `slide_outline.json` + `figures_index.json` + figures/ + pages/ → 产物
`slide_spec.json`。按 [references/design-style.md](references/design-style.md) 选
palette/字体/`layout_kind`（避免连续重复），把内容译成 `elements`。**陷阱**：
所有数字与术语必须在 paper_meta / figures_index 里有出处，不要捏造。

需要图标用 `kind:"icon"`，命名见 [references/pptxgenjs.md](references/pptxgenjs.md)
"Icons" 节，schema 见 [references/schemas.md](references/schemas.md) icon 元素。

需从论文整页裁图区时：

```bash
conda run -n paper2anything --no-capture-output python -m scripts.page_screenshot \
    <workdir> <page> <x> <y> <w> <h>
```

bbox 用相对比例 0..1，输出相对路径填到对应 image 元素 `path`。**裁图硬门禁**：
第一次调用 bbox 必须**逐值等于** `figures_index.json/captions[i].bbox`，**裁出
第一版前不许目测整页**——完整基准与 QA 重裁循环见
[references/design-style.md](references/design-style.md) §3（**跳过第一刀直接目测
＝违反 §3**）。Stage 3 关键约束（坐标≤画布 / `margin:0` 等）见
[references/pipeline.md](references/pipeline.md) §Stage 3。

### Stage 4 — Render（脚本）

```bash
conda run -n paper2anything --no-capture-output python -m scripts.render_pptx \
    <workdir>/slide_spec.json <workdir>/output.pptx
```

产物 `<workdir>/output.pptx`，渲染成功后复制到 Stage 0 给出的最终 `output_path`。
**陷阱**：依赖 `node`+`pptxgenjs`（全局装），node 不在 PATH 脚本会报错；失败先
`--dry-run` 只生成 `render/build.js` 定位 spec 问题。前置依赖与常见错误见
[references/pipeline.md](references/pipeline.md) §Stage 4。

### Stage 5 — QA

按下方 [QA](#qa) 一节执行：content QA 始终跑，视觉 QA 由 `config.json/visual_qa`
门控。

## Defaults & Errors

### 默认行为

| 输入 | 默认 |
|---|---|
| `output.pptx` 缺省 | `<paper-dir>/<paper-stem>.pptx`；重名追加 `-v2`、`-v3` |
| 工作目录写不进论文目录 | 回退到 `~/.cache/paper2anything/slides/<paper-stem>-<hash12>/` |
| 同一论文重跑 | 已完成阶段（产物文件已存在）自动跳过 |
| `config.json` 已存在 | Stage 0.5 跳过提问，沿用上次配置；要改配置走 `--from-stage configure` |
| Stage 0.5 未问 / `visual_qa` 缺省 | `deck_length=自动`、`visual_qa=true`（跑视觉 QA）|
| `--from-stage <N>` | 从指定阶段起强制重跑，不检查产物 |
| `--force` | 全部阶段强制重跑（罕用，仅在 schema 升级时） |

### 错误恢复速查

只列需要 **你判断/路由**的几类（技术类恢复全在 pipeline.md）：

| 症状 | 处理 |
|---|---|
| Stage 1 章节数 < 5 或 > 15 | 你在 Stage 2 校核时手动补 / 合并 |
| Stage 5 报"卡片下半空 / 栏不均衡 / 底部留白" | **不是 soft**——按 `references/design-style.md` "QA 修问题原则" **3 杠杆模型**（调文字量 > 调 bullet 间隔 > 调图片大小，可叠加）修，`--from-stage render` 重跑 |
| 用户/QA 报"引导符与文字没对齐" | 按 `references/design-style.md` "视觉丰富度建议 A" 对齐公式批量重置 icon_y + 收尾自检，`--from-stage render` 重跑 |
| 触发了 skill 但用户只要"读 PDF" | 误触发——让用户走官方 `pdf` skill，不要继续走 paper2slides |

完整错误恢复（Stage 1/4 技术类、annotation 绿框、dpi、figure_ref 等）见
[references/pipeline.md](references/pipeline.md) "错误恢复速查" 一节。

## QA

直接套用官方 pptx skill 的 QA Loop（官方 `SKILL.md` "QA (Required)" 一节；绝对
路径与 `find` 兜底见 [§Where to Look When Stuck](#where-to-look-when-stuck)）——
本 skill 不复述协议。**先读 `config.json/visual_qa`**，要点：

- **content QA 始终跑**：`markitdown` 查占位 / 数字一致性 / bullet 非 abstract 搬运 / title 无残留占位。
- **视觉 QA 仅 `config.json/visual_qa == true` 时跑**：soffice→pdf→jpg→**派单个子代理批量审**。
- 修问题改 `slide_spec.json` 后 `--from-stage render` **全量重渲**再 QA；**复检轮按官方 Verification Loop 收窄**——第 1 轮全 deck，第 2 轮起只看 上轮 flagged ∪ 本轮改动页，收敛前末轮全量 full pass。
- **终态报告必须说明视觉 QA 是否执行**；跳过时提示"视觉 QA 已按 config 跳过，如需 `--from-stage configure` 改配置后 `--from-stage qa`"。
- **留白 / 栏不均衡 / 引导符未对齐不是 soft，是 hard issue，必须修**——本 skill 最常误判处，复审子代理报告时不要拿 "soft" 打发。

完整 A/B 协议、`qa_log.json` 结构、产物统一放 `<workdir>/qa/` 等存放约定见
[references/pipeline.md](references/pipeline.md) §Stage 5；视觉子代理 prompt（加段
A/B）、3 杠杆修复模型、复检收窄细则见 [references/design-style.md](references/design-style.md)
"QA 时的视觉子代理 prompt" + "QA 修问题原则" 两节。

## Where to Look When Stuck

| 困惑 | 去这里 |
|---|---|
| PDF 文本/图表/表格提取异常 | 官方 **pdf skill** `SKILL.md`（路径见下） |
| PPT 视觉设计、配色、版式选择 | 官方 **pptx skill** `SKILL.md` 的 "Design Ideas" 一节 |
| PptxGenJS API 用法、踩坑点、icon 生成 | [references/pptxgenjs.md](references/pptxgenjs.md)（本仓库副本，含学术 icon 名表）|
| QA 流程与子代理 prompt | 官方 pptx skill `SKILL.md` 的 "QA (Required)" 一节 |
| 各阶段产物 JSON schema 详细字段（含 config.json）| `references/schemas.md` |
| 章节如何映射到 slide 角色 | `references/outline-heuristics.md` |
| 配色/版式与论文场景的适配 | `references/design-style.md` |

官方 skill 的绝对路径（**`~` 即用户 home，跨机器通用**；如下面路径不存在，用
`find ~/.claude -path '*marketplaces*pptx*'` 或 `find ~/.claude -path '*marketplaces*pdf*'` 定位）：

```
~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/pptx/
~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/pdf/
```

阅读这两个 skill 是本 skill 的"基础课"——遇到底层细节优先查它们，本 skill 只提
供论文领域的**编排**与**判断指南**。
