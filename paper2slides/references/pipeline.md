# Pipeline Protocol

六个阶段的详细执行协议。本文件比 SKILL.md Quick Reference 更细——SKILL.md 是
索引，本文件是手册。

## 通用约定

- **Python 环境**：所有 `python` 命令默认在 `paper2anything` conda 环境中跑。在
  Claude Code 里执行时显式用：

  ```bash
  conda run -n paper2anything --no-capture-output python -m scripts.<name> ...
  ```

  下文为简洁起见省略前缀，但每条命令都隐含这个前缀。

- **工作目录**：所有阶段共享 `<paper-dir>/.paper2anything/slides/<paper-stem>/`，路径由
  `scripts/workdir.py resolve <paper.pdf>` 解析。**不要手动拼路径**——规则
  集中在 workdir.py。

- **重跑**：默认按"产物文件存在则跳过"语义，`--from-stage <name>` 强制从某阶段起
  全跑，`--force` 全部重跑。`config.json`（Stage 0.5 产物）同此语义——已存在则
  跳过提问沿用上次配置，`--from-stage configure` 重新问。

- **失败处理**：脚本出错时 stderr 给出诊断；你应读 `run.log`（如果脚本写了），
  不要盲目重试。

---

## Stage 0: 解析 workspace（每次必跑的前置）

```bash
python -m scripts.workdir resolve <paper.pdf> [--output <out.pptx>] --ensure
```

输出 JSON 含：`paper_path` / `output_path` / `workdir` / 各产物路径 / 各阶段
`stage_status`。

**你的职责**：读这份 JSON，决定哪些阶段已完成、哪些要跑。后续所有命令引用
此处给出的路径，不要拼字符串。

---

## Stage 0.5: Configure（用户对话 → config.json）

**无脚本**。你用 [AskUserQuestion] 工具在 Stage 0 之后、Stage 1 之前与用户
确认三项关键参数，把答案用 Write 工具落到 Stage 0 JSON 给出的 `config_path`
（`<workdir>/config.json`，schema 见 [schemas.md](schemas.md#configjsonstage-05-产物)）。

**输入**：用户对话（+ 用户初始请求里已表达的偏好）

**输出**：`workdir/config.json`

**完成判定**：`config.json` 存在（`stage_status.configure == true`）。

### 三项确认

| # | 字段 | 选项 | 默认/推荐 |
|---|---|---|---|
| 1 | `deck_length` | `精简` ~8–12 张（10 min 短讲/组会快过）/ `标准` ~13–18 张（12–20 min 会议 talk）/ `详尽` ~19–28 张（30–45 min keynote/job talk）/ `自动` 不设页数目标，由叙事+版面决定 | 默认 `自动`；`自动` 完全保留近期"张数不设上下限"哲学 |
| 2 | `visual_qa` | `true` 跑 soffice→jpg→子代理 视觉闭环 / `false` 只跑便宜的 content QA | **默认 `true`**（采用视觉 QA）；注意它昂贵（token/时间近乎前面所有阶段总和），不需要时选 `false` 省开销 |
| 3 | `color_scheme` | `自动` 由 Stage 3 按论文气质选 palette / `自定义` 用户用一句话描述配色偏好，写进 config | **默认 `自动`**；自定义只存用户原话，由 Stage 3 解析映射，本阶段不选定具体 palette |

### config.json 写什么

```json
{
  "schema_version": "0.1",
  "deck_length": "标准",
  "deck_length_target": [13, 18],
  "visual_qa": true,
  "color_scheme": null
}
```

- `deck_length_target`：`精简`→`[8,12]`、`标准`→`[13,18]`、`详尽`→`[19,28]`、
  `自动`→`null`。下游只需读这个区间（`null` = 不约束）。
- `color_scheme`：选 `自动` 写 `null`；选 `自定义` 把用户原话存成字符串。Stage 3 据此选 palette，本阶段不解析、不定具体 palette。
- 完整字段语义见 [schemas.md](schemas.md#configjsonstage-05-产物)。

### 复用与重配

- **跳过提问**：`config.json` 已存在且未带 `--from-stage configure` / `--force`
  时不再问，沿用上次配置（与其它阶段"产物存在即跳过"一致）。
- **重新配置**：`--from-stage configure`（会覆盖旧 `config.json`，并因 configure
  在 STAGES 最前、其后所有阶段一并重跑）。
- **预填**：用户初始请求已表达偏好（"做个精简的" / "详尽 keynote" / "顺便做下
  视觉 QA"）时，把对应项设为 AskUserQuestion 首选项——仍展示确认，不静默替用户决定。

### 下游消费

`deck_length_target` → **Stage 2**（大纲粒度软目标）、`color_scheme` → **Stage 3**
（选 palette）、`visual_qa` → **Stage 5**（视觉 QA 开关）。各字段语义与消费细则见
[schemas.md](schemas.md#configjsonstage-05-产物) 的"消费方"。

---

## Stage 1: Extract（PDF → MinerU 云解析 → 元数据 + 图 + 整页渲染）

解析统一走 **MinerU 云 API**：上传 PDF 到 mineru.net，云端解析后下载结果。必填
`MINERU_API_TOKEN`（包根 `.env`）；无 token 或解析失败**直接报错**。

```bash
python -m scripts.extract_paper <paper.pdf> [--dpi 300]
```

**输入**：`<paper.pdf>`（绝对路径或相对当前工作目录）

**输出**（写到 workdir，由 `lib/mineru_parser` 写）：

| 产物 | 内容 |
|---|---|
| `paper_meta.json` | title / authors / sections / figures / tables / equations / references_count（结构化元数据，由 MinerU 直接给出）|
| `figures_index.json` | captions（图/表 caption，table 带 `bbox` + `bbox_source: mineru:vlm`）、figures、page_renders 等列表 |
| `figures/`、`tables/` | MinerU 抽出的图 / 表实体与高清裁图 |
| `pages/page-NN.png` | pdftoppm 整页渲染，**默认 300 dpi 含 `-hide-annotations`**（去掉 PDF 自带 hyperlink 绿框）；`--dpi 200` 降载、`--dpi 400` 细公式 |

**完成判定**：`paper_meta.json` + `figures_index.json` 存在。

**已知不完美**：

- table / figure 的 `bbox` 偶把 `y` 起点压在子图标题 / 图注行上 → 第一刀会切到标题或卷入
  caption；按 [design-style.md](design-style.md) §3 在原框上对那一条边定向微调，别丢开原框重估。
- 个别论文 MinerU 抽 title / authors 仍可能不全 → 进 Stage 2 前**必跑** [schemas.md 末尾 4 项校核](schemas.md#你在-stage-2-进入前应做的修订)（title / authors / 同 kind 合并 / 缺关键 kind）核对 `paper_meta.json`；**校核结果不写回 `paper_meta.json`**，直接体现在 outline 里。

**何时重跑**：换论文、PDF 改了、想换 `--dpi`。

---

## Stage 2: Outline（论文元数据 → slide 大纲）

**无脚本**。这是你的工作。

**输入**：`workdir/paper_meta.json`（read-only）+ `workdir/figures_index.json`
+ `workdir/config.json`（read-only）

**输出**：`workdir/slide_outline.json`（schema 见 [schemas.md](schemas.md)）

**协议**：

1. 读 `paper_meta.json` 与 `figures_index.json`；读 `config.json/deck_length_target`
2. 跑 [schemas.md](schemas.md) 末尾的 4 项校核（title / authors / 同 kind 合并 / 缺失 kind）
3. 按 [outline-heuristics.md](outline-heuristics.md) 决定 slide 角色与顺序：
   `deck_length_target == null`（`自动`）时张数纯由叙事+版面定；非 `null`
   时把该区间当作**大纲粒度软目标**（调 method/result 拆分细度与可选角色含不含），
   **不**为凑数砍核心叙事角色，**不**改每页"空间驱动、无留白无溢出"
4. 为每张 slide 写 `title` / `bullets` / `figure_ref` / `speaker_notes` / `source_section_ids`
5. 把结果序列化到 `workdir/slide_outline.json`，必跑 `python -c "import json; json.load(open(...))"`
   验证 JSON 合法

**完成判定**：`slide_outline.json` 存在且 schema 合法。

**Stage 2 常见错误**：

- 直接复制论文 abstract 当 bullets（违反提炼原则——bullet 是要点不是搬运）
- 一张 method 把所有方法细节塞满
- bullets 缺主语 + 缺动词，全是名词短语
- speaker_notes 写成 bullet 的扩展（应该是讲者的口播草稿）

---

## Stage 3: Spec（slide 大纲 → 渲染规格）

**无脚本**。你工作。

**输入**：`workdir/slide_outline.json` + `workdir/figures_index.json` + 各种 PNG

**输出**：`workdir/slide_spec.json`（schema 见 [schemas.md](schemas.md)）

**协议**：

1. 读 `slide_outline.json`
2. 按 [design-style.md](design-style.md) 选 palette、font_header/body
3. 为每张 slide 选 `layout_kind`（避免连续相同的 layout）
4. 把 `title` / `bullets` / 配图 / 形状/线条 等翻译成 `elements` 数组；坐标用英寸
5. 对图：若 `figure_ref` 给出，先查 `figures_index.json/captions[].id == figure_ref`
   找到 page；再决定用 `embedded_images` 中某张，还是用 `page_renders` 整页（必要时
   `scripts/page_screenshot.py` 裁剪 bbox）
6. 序列化、JSON 校验

**关键约束**（这些是 Stage 3 最易翻车的点）：

- `slide.id` 与 `slide_outline.json` 保持一致
- 元素坐标 + 尺寸 ≤ slide 尺寸（10 × 5.625 for 16:9）
- 文本元素的 `text` 字段：**所有数字与术语必须在 paper_meta 或 figures_index 里有出处**
  （不要 hallucinate 论文里没有的数字）
- 配图路径：相对 workdir，且文件实际存在
- text 元素的 `margin: 0` 当对齐 shape/icon 时务必加（PptxGenJS 默认 margin 会偏移）

**完成判定**：`slide_spec.json` 存在且 schema 合法。

---

## Stage 4: Render（规格 → .pptx）

```bash
python -m scripts.render_pptx <slide_spec.json> <output.pptx>
```

**输入**：`workdir/slide_spec.json`

**输出**：`workdir/output.pptx`（先落 workdir），随后由调用方复制到最终 `output_path`

**机制**：`render_pptx.py` 把 `slide_spec.json` 翻译成 PptxGenJS `.js` 程序，
存到 `workdir/render/build.js`，然后 `node` 跑出 `.pptx`。

**前置依赖**：

- `node` 在 PATH 中
- `pptxgenjs` 已 `npm install -g`（或局部 `npm install` 后 `NODE_PATH` 指向）
- icon 元素另需 `npm install -g react-icons react react-dom sharp`（缺失时 icon warn+skip，不阻断渲染）

**完成判定**：`workdir/output.pptx` 存在且 ≥ N 张 slide（N == `slide_spec.json/slides.length`）。

**Stage 4 常见错误**：

- 字体名拼错（PptxGenJS 不报错，pptx 打开时回退默认字体）
- 图片路径相对 workdir 但 render_pptx.py 没正确解析（render_pptx.py 必须 `cd workdir`
  或用绝对路径喂给 PptxGenJS）
- shape 的 z 排序写错（背景 shape 跑到前景遮挡文字）

---

## Stage 5: QA

**直接套用官方 pptx skill 的 QA Loop**——不在本文件复述。读官方 pptx skill
`SKILL.md` 的 "QA (Required)" 一节（绝对路径与 `find ~/.claude` 兜底见
[SKILL.md](../SKILL.md#where-to-look-when-stuck)）。**先读 `config.json/visual_qa`**，按其流程：

### A. Content QA — 始终跑

1. `python -m markitdown <workdir>/output.pptx`，grep "lorem|xxxx|placeholder|TODO"
2. **追加项**（论文 deck 特别检查）：
   - 数字一致性：所有 stat callout 的数字在 paper_meta 或 figures_index 里有出处
   - bullet 不是论文 abstract 的复制粘贴
   - title slide 没有遗留的"YOUR TITLE HERE"

### B. Visual QA — 仅 `config.json/visual_qa == true` 时跑

3. `soffice --headless --convert-to pdf <workdir>/output.pptx --outdir <workdir>/qa/` →
   `pdftoppm -jpeg -r 150 <workdir>/qa/output.pdf <workdir>/qa/slide` → 派**单个**子代理
   批量审多页（对齐官方模板，非每页一个）用官方 prompt 视觉检查
   `<workdir>/qa/slide-*.jpg`（子代理 prompt + 复检轮范围详见 [design-style.md](design-style.md) 末尾）

> `visual_qa == false`则**整段 B 跳过**——不生成 PDF/JPG、不派子代理。
> 这是 Stage 0.5 用户基于"昂贵且边际有限"的显式选择，不是遗漏。`qa_log.json`
> 记 `"visual_qa": false`，**终态报告必须明确告知"视觉 QA 已按 config 跳过，
> 如需 `--from-stage configure` 改配置后 `--from-stage qa` 重跑"**。

**B 跑时所有中间产物（PDF + JPG）统一放 `<workdir>/qa/`**——不要写到
`<workdir>/render/`、`/tmp/` 或 `<workdir>` 根。该目录由 `workdir.py` 在
`ensure()` 时自动建好；绝对路径用 `python -m scripts.workdir resolve <paper.pdf>`
输出 JSON 的 `qa_dir` 字段。

4. **修问题**：在 `slide_spec.json` 里改对应字段，**不要直接改 .pptx**
5. 重跑 Stage 4（`--from-stage render` 全量重渲）→ 再 QA，直到无新发现。**复检轮按官方
   Verification Loop 收窄子代理范围**（第 1 轮全量；第 2 轮起只审 上轮 flagged ∪ 本轮
   spec 改动页；末轮全量 full pass 兜底），判定标准不变，细则见 [design-style.md](design-style.md) "QA 修问题原则" 第 5 步

**完成判定**：写一份 `qa_log.json`，结构：

```json
{
  "visual_qa": true,
  "rounds": [
    {"timestamp": "2026-04-26T15:00:00Z",
     "issues": ["..."], "fixed": ["..."], "pass": false},
    {"timestamp": "2026-04-26T15:15:00Z",
     "issues": [], "fixed": [], "pass": true}
  ]
}
```

最后一 round `pass: true` 视为流水线完成。把 `workdir/output.pptx` 复制（或重命名）
到 workspace 给出的最终 `output_path`。

---

## 错误恢复速查

| 症状 | 多半的根因 | 处理 |
|---|---|---|
| Stage 1 MinerU 解析失败 / 超时 | token 失效 / 网络 / PDF 过大 | 核对 `MINERU_API_TOKEN`、能访问 mineru.net；PDF ≤200MB/200 页；重跑 |
| `paper_meta.json` 章节数 < 5 | MinerU 章节切分不全 | 你在 Stage 2 校核时手动补 |
| `paper_meta.json` 章节数 > 15 | 子章节过细 | 检查 paper_meta.json/sections，由你合并 |
| Stage 3 引用了不存在的 figure | figure_ref 写错 | 查 figures_index.json/captions，改 figure_ref 或改用 page_renders |
| Stage 4 PptxGenJS 报 image not found | 路径相对 workdir 但 node 工作目录错 | render_pptx.py 内部 cd 到 workdir 或喂绝对路径 |
| Stage 5 视觉 QA 报"lorem ipsum 残留" | Stage 3 的你用了占位 | 修 slide_spec.json 对应文本，从 render 重跑 |
| Stage 5 报"table 底线被切" / "裁切带入下方正文" | bbox 太紧 / 你视觉估算偏差 | `page_screenshot.py` 默认已 +0.005 padding，仍丢手动加大 `--pad 0.01`；优先用 `figures_index.json/captions[i].bbox`（mineru 检出）|
| Stage 5 报"表/图里 `[N]` 引用出现绿色矩形框" | pdftoppm 默认渲染 PDF 自带的 hyperlink annotation | extract_paper.py 已默认 `-hide-annotations`；如仍出现，机器 poppler 太旧（< 0.69），升级或 `apt install -y poppler-utils` |
| Stage 5 报"figure/table 字模糊" | dpi 太低 | 默认已 300 dpi；论文超长降到 `--dpi 200` 时如不够清晰，恢复 300 或升 `--dpi 400` |
