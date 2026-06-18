# JSON Schemas

paper2slides 各阶段产物的 schema 定义。所有 JSON 文件均带 `schema_version`
字段；本文件描述 `0.1` 版本。

## 通用约定

- 编码：UTF-8，缩进 2 空格
- 字段缺失策略：可选字段写成 `null` 或省略；必填字段缺失视为流水线错误
- 路径字段：相对 workdir（除非字段名带 `_absolute`）。例如 `embedded_path`
  形如 `figures/fig-001.png`，从 `<paper-dir>/.paper2anything/slides/<paper-stem>/`
  起算
- 阶段产物文件名固定（见 `scripts/workdir.py` 的 `STAGE_MARKERS`），不要改名

---

## config.json（Stage 0.5 产物，Stage 2 与 Stage 5 输入）

Stage 0.5 用 AskUserQuestion 与用户确认三项后由你写出。落在 workdir 根
（`config_path` 字段，见 `workdir.py` 的 `STAGE_MARKERS["configure"]`）。

```json
{
  "schema_version": "0.1",
  "deck_length": "标准",
  "deck_length_target": [13, 18],
  "visual_qa": true,
  "color_scheme": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|:-:|---|
| `schema_version` | string | 是 | 固定 `"0.1"` |
| `deck_length` | string | 是 | `精简` / `标准` / `详尽` / `自动` 之一 |
| `deck_length_target` | `[int,int]` \| null | 是 | 页数软目标区间。`精简`→`[8,12]`、`标准`→`[13,18]`、`详尽`→`[19,28]`、`自动`→`null`。下游只读这个；`null` = 不约束张数 |
| `visual_qa` | bool | 是 | `true`（默认）跑 Stage 5 的视觉 QA（soffice→jpg→子代理）；`false` 只跑 content QA |
| `color_scheme` | string \| null | 是 | `null`（默认，"自动"）= Stage 3 按论文气质自动选 palette；字符串 = 用户对配色的描述，Stage 3 据此映射/约束 palette 选择 |

**消费方**：

- **Stage 2** 读 `deck_length_target`：`null` 时张数纯由叙事+版面定；非 `null`
  时作大纲粒度软目标（详见 [outline-heuristics.md](outline-heuristics.md) 页数档节）。
  **不**作每页字数上限，**不**改每页"空间驱动"。
- **Stage 3** 读 `color_scheme`：`null` 按论文气质自动选 palette；非 `null` 时把
  用户描述当约束。选/自造 palette 细则见 [design-style.md](design-style.md)。
- **Stage 5** 读 `visual_qa`：`false` 跳过视觉 QA，`qa_log.json` 记
  `"visual_qa": false`。

> `schema_version` 保持 `"0.1"`：config.json 是独立的配置产物，与各阶段产物 schema 平行，
> workdir 无此文件时 Stage 0.5 会重新生成（等价于"未配置"，走默认）。

---

## paper_meta.json（Stage 1 产物，Stage 2-3 输入）

```json
{
  "schema_version": "0.1",
  "source_pdf": "absolute/path/to/paper.pdf",
  "title": "string",
  "authors": ["string", ...],
  "venue": "string|null",
  "year": "int|null",
  "abstract": "string",
  "sections": [
    {
      "id": "intro",
      "kind": "introduction",
      "title": "1 Introduction",
      "page_start": 1,
      "page_end": 2,
      "text": "section body, with PAGE separators stripped",
      "subsections": []
    }
  ],
  "figures": [
    {"id": "figure1", "kind": "figure", "num": 1, "page": 3, "caption": "..."}
  ],
  "tables": [
    {"id": "table1", "kind": "table",  "num": 1, "page": 6, "caption": "..."}
  ],
  "references_count": 42
}
```

字段细节：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | string | 是 | 当前固定 `"0.1"` |
| `source_pdf` | string | 是 | 源 PDF 的绝对路径 |
| `title` | string | 是 | 论文标题。脚本启发式抽取，**你在 Stage 2 必须校核**——首页常有 license/水印干扰 |
| `authors` | string[] | 否 | 启发式抽取，可能不全；你看到必要时补 |
| `venue` / `year` | string\|null / int\|null | 否 | 短期不抽取（脚本不可靠），由你从原文判断或留空 |
| `abstract` | string | 否 | 启发式抽到的 abstract 段，可能含连字符与换行污染 |
| `sections[]` | array | 是 | 启发式切分结果。**Stage 2 的你修订边界**：合并被误切的子节、剔除明显错误 |
| `sections[].kind` | enum | 是 | 见下方 `kind` 枚举 |
| `sections[].text` | string | 是 | 章节正文（已剔除 PAGE 分隔符）|
| `sections[].subsections` | array | 是 | 短期始终为空数组；中期可填子节 |
| `figures[]` / `tables[]` | array | 否 | 从 `figures_index.json` 的 `captions` 按 `kind` 过滤拷贝；当 caption 含 `bbox` / `bbox_source` / `bbox_confidence` 字段时一并继承 |
| `references_count` | int | 否 | 估算值（`[1] [2] ...` 或 `1. 2. ...` 数法）|

`sections[].kind` 枚举：

```
abstract | introduction | background | related | method | experiment |
result | discussion | conclusion | references | other
```

### 你在 Stage 2 进入前应做的修订

读完 `paper_meta.json` 后，**先**做以下校核（不要跳）：

1. `title` 是否合理？常见错误：抓到了 license 水印（"Provided proper attribution..."）
   或杂乱字符。如果不合理，从 `sections[0].text` 或 PDF 第一页文本里找真正的标题
2. `authors` 是否为空或明显错位？必要时从首页文本人工识别
3. 同 `kind` 多个章节（如两个 `method`）是表示真有多个独立方法节，还是一个被切碎了？
   合并被切碎的即可（保留 `id`/`title`，把 `text` 拼接、`page_end` 取后者）
4. 缺关键 kind？（多数论文至少要有 `method` + `experiment` + `conclusion`，不齐时
   去 `sections[].text` 找看是否被脚本漏掉了）

校核之后**不需要**写回 `paper_meta.json`，直接基于校核后的理解生成 `slide_outline.json`。

---

## slide_outline.json（Stage 2 产物，Stage 3 输入）

```json
{
  "schema_version": "0.1",
  "deck_title": "string",
  "audience": "researchers",
  "slides": [
    {
      "id": "s01",
      "role": "title",
      "title": "Attention Is All You Need",
      "bullets": [],
      "needs_figure": false,
      "figure_ref": null,
      "source_section_ids": [],
      "speaker_notes": "1-2 sentences a presenter would say"
    }
  ]
}
```

字段细节：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `deck_title` | string | 是 | 通常等于 paper title；可换更短的演讲版 |
| `audience` | enum | 是 | `researchers` / `general` / `mixed`，影响 bullet 详略与术语 |
| `slides[].id` | string | 是 | `s01`、`s02`、...（两位序号方便排序）|
| `slides[].role` | enum | 是 | 见下方 |
| `slides[].title` | string | 是 | 短句；不重复 deck_title |
| `slides[].bullets` | string[] | 是 | 提炼后的要点（非整段搬运）；条数与长度由版面填充决定，见 [outline-heuristics.md](outline-heuristics.md)；title slide 等可空 |
| `slides[].needs_figure` | bool | 是 | 是否需要论文 figure（method/result 通常 true）。**=false 不代表无视觉**——每页都须有视觉元素，Stage 3 用 icon/shape/chart 等承载 |
| `slides[].figure_ref` | string\|null | 是 | 引用 `paper_meta.json/figures[].id`（如 `"figure2"`），或 `null` |
| `slides[].source_section_ids` | string[] | 是 | 哪些 paper section 提供了内容（便于追溯）|
| `slides[].speaker_notes` | string | 是 | 1–3 句话，给讲者用 |

`slides[].role` 枚举（本文件只定义**合法值**）：

```
title | tldr | motivation | background | method | experiment |
result | discussion | conclusion | qna
```

> **角色的必含性、典型顺序、paper section→role 映射、每个角色的内容指南**都是
> Stage 2 启发式，**单一权威在 [outline-heuristics.md](outline-heuristics.md)**
> （"角色 → 必含性与顺序" / "论文 section → slide 角色映射" / "每个角色的内容
> 指南" 三节）。本文件不复述，避免与之漂移。

---

## slide_spec.json（Stage 3 产物，Stage 4 输入）

```json
{
  "schema_version": "0.1",
  "engine": "pptxgenjs",
  "template_path": null,
  "layout": "LAYOUT_16x9",
  "theme": {
    "palette_name": "Midnight Executive",
    "primary": "#1E2761",
    "secondary": "#CADCFC",
    "accent": "#FFFFFF",
    "background": "#FFFFFF",
    "font_header": "Georgia",
    "font_body": "Calibri"
  },
  "slides": [
    {
      "id": "s01",
      "layout_kind": "title",
      "elements": [
        {"kind": "text", "role": "title",
         "text": "Attention Is All You Need",
         "x": 0.5, "y": 2.0, "w": 9.0, "h": 1.2,
         "fontFace": "Georgia", "fontSize": 44, "bold": true,
         "color": "#FFFFFF", "align": "left", "valign": "middle"},
        {"kind": "shape", "shape": "rect",
         "x": 0, "y": 0, "w": 10, "h": 5.625,
         "fill": "#1E2761", "z": -1}
      ],
      "speaker_notes": "..."
    }
  ]
}
```

字段细节：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `engine` | enum | 是 | 短期固定 `"pptxgenjs"`；中期会出现 `"template"` |
| `template_path` | string\|null | 是 | `engine == "template"` 时才有意义；当前固定 `null` |
| `layout` | enum | 是 | `LAYOUT_16x9` / `LAYOUT_16x10` / `LAYOUT_4x3` / `LAYOUT_WIDE`，默认 `LAYOUT_16x9` |
| `theme.palette_name` | string | 是 | 引用官方 pptx skill 的命名调色板（如 `Midnight Executive`），见 [design-style.md](design-style.md) |
| `theme.primary/secondary/accent/background` | hex | 是 | 6 位 hex 色，配合 palette_name |
| `theme.font_header/font_body` | string | 是 | 见 [design-style.md](design-style.md) 的字体配对建议 |
| `slides[].layout_kind` | enum | 是 | 见下方 |
| `slides[].elements` | array | 是 | 每个元素一个对象；`text` / `image` / `shape` / `line` / `icon` 五类 |

`layout_kind` 枚举（对应官方 pptx skill 的版式 + 论文场景补充的 `title`）：

```
title | two_column | icon_rows | image_half_bleed | stat_callout | grid_2x2 | comparison_columns
```

### 元素子结构

**text**：

```json
{"kind": "text", "role": "title|body|caption|footer",
 "text": "string or rich-array",
 "x": 0.5, "y": 0.5, "w": 9, "h": 1,
 "fontFace": "Calibri", "fontSize": 24, "bold": false, "italic": false,
 "color": "#363636", "align": "left|center|right",
 "valign": "top|middle|bottom",
 "bullet": false, "margin": 0}
```

`text` 可以是字符串，也可以是 PptxGenJS rich-text 数组（多段不同样式）。
`bullet: true` 配 `breakLine` 在 PptxGenJS 调用时由渲染器自动处理，但
**论文 deck 不要用它**——PptxGenJS 默认圆点太丑，引导符改用独立 `kind:"icon"`
元素，见 [design-style.md](design-style.md) "视觉丰富度建议 A"。

**image**：

```json
{"kind": "image",
 "path": "figures/fig-04.png",   // 相对 workdir
 "x": 5, "y": 1.5, "w": 4.5, "h": 3.5,
 "sizing": {"type": "contain", "w": 4.5, "h": 3.5}}
```

`sizing` 可省略——render 端用 PIL 按原比例缩放居中（见 [design-style.md](design-style.md) §0.3），写不写都不会变形。

**shape**：

```json
{"kind": "shape", "shape": "rect|oval|line|rounded_rect",
 "x": 0, "y": 0, "w": 10, "h": 0.3,
 "fill": "#1E2761", "line_color": "#000000", "line_width": 0,
 "rectRadius": 0.1,
 "transparency": 0,
 "z": 0}
```

`z` 用来控制层叠（负值放底，正值放顶）。`render_pptx.py` 按 `z` 升序绘制。

**line**：

```json
{"kind": "line",
 "x": 1, "y": 3, "w": 5, "h": 0,
 "color": "#FF0000", "width": 3, "dashType": "solid|dash|dot"}
```

**icon**：

```json
{"kind": "icon",
 "icon": "FaChartLine",   // react-icons 导出名，PascalCase，含库前缀（Fa/Md/Hi/Bi）
 "lib": "fa",             // fa|md|hi|bi（缺省 fa）
 "color": "#1E2761",      // ⚠️ 必须带 #：CSS 色值直接进 react-icons；写 "1E2761" 会静默渲染成黑色
 "iconSize": 256,         // 可省；光栅分辨率，非显示尺寸（显示由 w/h 决定，建议 ≥256）
 "x": 1, "y": 1, "w": 0.5, "h": 0.5, "z": 0}
```

icon 在 Stage 4 由 react-icons → SVG → sharp 实时光栅成 PNG 嵌入，**不写磁盘**。
与 `image` 的区别：`image` 走磁盘 `path` 并被 `render_pptx.py` 等比缩放居中；
`icon` 本就是方形矢量光栅，不进 `_normalize_image_boxes`，`w/h` 直接生效（用等值如 `0.5×0.5`）。
依赖缺失 / `icon` 名拼错 / 光栅失败时该 icon 自动 warn+skip，不阻断整 deck。
合法 icon 名与命名规律见 [pptxgenjs.md](pptxgenjs.md) 的 "Icons" 节。

> **颜色格式（关键，最易踩）**：`icon.color` 与 shape/text/line 的 color 规则**相反**。
> shape/text/line 的色值经 `render_pptx.py` 的 `clean()` 去 `#`，带不带 `#` 都行；
> 但 `icon.color` **原样传给 react-icons 当 CSS 值**，**必须带 `#`**（如 `#1E2761`）。
> 漏 `#` 不报错——react-icons 回退**黑色**（深色背景上 = 不可见）。**口诀：shape/text/line 不带 `#`，icon 带 `#`。**
> 详见 [pptxgenjs.md](pptxgenjs.md) Common Pitfalls #1。

### 坐标与单位

- 单位：英寸（PptxGenJS 约定）
- `LAYOUT_16x9` 工作区：10" × 5.625"
- 安全边距：≥ 0.5"，避免内容贴边
- 元素间距：0.3–0.5"，统一间隔避免随机视觉

设计美学规范（避免 AI 痕迹的"标题下划线"等）见 [design-style.md](design-style.md)。

---

## figures_index.json（Stage 1 产物，本身不是阶段标志，但 Stage 2 与 Stage 3 都要读）

```json
{
  "schema_version": "0.1",
  "source_pdf": "absolute/path",
  "n_pages": 15,
  "captions": [
    {"id": "figure1", "kind": "figure|table", "num": 1,
     "page": 3, "caption": "string"},
    {"id": "table3", "kind": "table", "num": 3, "page": 9,
     "caption": "...",
     "bbox": [0.229, 0.164, 0.420, 0.321],
     "bbox_source": "mineru:vlm",
     "bbox_confidence": "high"}
  ],
  "page_renders": [
    {"page": 1, "path": "pages/page-1.png"}
  ]
}
```

> 图实体由 MinerU 写入 `figures/`。某 figure 在原文是矢量图、`figures/` 里没有清晰实体时，
> 回退用 `page_renders` 同页 PNG 裁剪（`scripts/page_screenshot.py` 提供）。

### `captions[].bbox`（仅 `kind == "table"`）

MinerU 解析时给检测到的表格区域附 bbox，匹配到 caption 的就把 bbox 写到该 caption 上：

| 字段 | 含义 |
|---|---|
| `bbox` | 4 元素数组 `[x, y, w, h]`，**相对页面 0..1，top-origin** —— 与 `page_screenshot.py` 接口一致 |
| `bbox_source` | `"mineru:vlm"` —— 来源标识 |
| `bbox_confidence` | `"high"` / `"medium"` 等 |

**字段缺失语义**：当某 table caption 没有 `bbox` 字段（即 `bbox not in caption`），表示
MinerU 未能定位该表。Stage 3 在这种情况下走视觉估算 fallback。**约定使用"字段省略"而非
`null`**，方便 `if "bbox" in c: ...` 形式的判断。

`schema_version` 保持 `"0.1"`。

### 顶层字段：`extract_backend` / `mineru_task_id`

`figures_index.json` 顶层还含以下两个字段，下游用 `.get(default)` 防御式读取：

**`figures_index.json` 顶层**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `extract_backend` | `"mineru"` | Stage 1 解析后端（固定为 `"mineru"`）|
| `mineru_task_id` | string \| null | MinerU 任务 ID（便于复跑诊断；写入 `run.log`）|

**`figures_index.json/captions[i]`**（mineru 后端时所有 caption 都带）：

| 字段 | 含义 |
|---|---|
| `bbox_source` | 枚举值如 `"mineru:vlm"`（VLM 模型识别，`bbox_confidence == "high"`）|
| `html` | 仅 `kind == "table"` 有；MinerU 把表识别成 HTML，可供 Stage 3 选择直接渲染或裁图 |
| `high_res_crop_path` | `"figures/<id>.png"`，`parse_pdf` 已用 PIL 从 300 dpi 整页 PNG 裁出高清版 |
| `subfigures` | `[{page, bbox}]` 子图列表（如论文 Figure 2 是两个并排子图，无编号 caption 的 image 会被归并到下一个有编号 figure）|

**`paper_meta.json` 顶层**还含：

```json
"equations": [
  {"id": "eq_1", "page": 4,
   "bbox": [0.18, 0.34, 0.50, 0.04],
   "latex": "\\operatorname {Attention} (Q, K, V) = ...",
   "latex_raw": "\\operatorname {A t t e n t i o n} (Q, K, V) = ...",
   "is_appendix": false}
]
```

`latex` 是 `clean_latex` 清洗后的字串（VLM 在字母间错插的空格已合并）；`latex_raw` 保留原始供调试。Stage 3 可三选一处理，详见 [design-style.md](design-style.md) 的 "Equations" 一节。

`paper_meta.json/figures[]` 与 `tables[]` 自动继承 captions 的这些字段（`html` / `high_res_crop_path` / `bbox` / `bbox_source` / `bbox_confidence` / `subfigures`）。

### `is_appendix` 标记（figures / tables / equations 通用）

每个 figure / table / equation 都附带 `is_appendix: bool`，由 Stage 1 解析计算：

- **判定规则**：找到 `sections[]` 中 `kind == "references"` 的章节，记其 `page_start` 为 `T`；该条目的 `page > T` 即视为附录。无 references 章节时 fallback 到"最后一个非 references section 的 page_end"。
- **目的**：保留全部识别结果（**Stage 1 不丢弃任何 figure/table**，附录数据可能在长 talk / 补充材料场景仍有用），但让 Stage 2 在选 `figure_ref` / `equation_ref` 时**默认只挑 `is_appendix == false`**。详见 [outline-heuristics.md](outline-heuristics.md)。
- **何时手工启用附录条目**：长篇 keynote、补充材料、reviewer presentation 等场景下，Stage 2 可显式挑选 `is_appendix == true` 的内容；这是个判断决定，不是规则。
