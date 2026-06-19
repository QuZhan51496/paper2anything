# Design Style

Stage 3 的你把 `slide_outline.json` 扩展成 `slide_spec.json` 时的视觉决策指南。**核心规则：本文件不复述官方 pptx skill 的设计指南，只补论文场景的特例与取舍**。

## 必读：官方 pptx skill 的设计指南

打开并通读官方 pptx skill 的 `SKILL.md`（绝对路径与 `find ~/.claude` 兜底见
[SKILL.md](../SKILL.md#where-to-look-when-stuck)），重点 "Design Ideas" 一节，包含：

- 10 套 palette（命名调色板，每个有 primary/secondary/accent）
- 字体配对（header + body）
- 6 种 layout 选项（two-column、icon rows、image-half-bleed、stat callout、grid 2x2、timeline）——官方 skill 的版式灵感；本 skill `slide_spec.json/layout_kind` 的合法值以 [schemas.md](schemas.md) 为准
- 间距、字号、对齐规则
- "Avoid (Common Mistakes)" 一节——尤其 **NEVER use accent lines under titles**
  这条，是 AI 生成 deck 的典型痕迹

PptxGenJS API、踩坑点与 **icon 生成**（react-icons → SVG → sharp → base64）见本仓库
副本 [pptxgenjs.md](pptxgenjs.md) —— 写 spec 配图标时翻它的 "Icons" 节（含学术高频 icon 名表）。

下面只补充**论文场景独有**的规则。

---

## Palette 与论文主题的匹配

**先读 `config.json/color_scheme`**（Stage 0.5 落盘）：

- `null`（用户选了"自动"）：按论文气质从下表 10 套里自选——本节默认路径。
- 非 `null`（用户的配色描述）：
  用户意图**优先**。描述直接点名某套 palette 就用那套；是色系/方向描述就从下表 10
  套里挑最契合的一套。仍遵守下方原则（与主图主色协调、不无脑堆蓝）与 §0 的视觉
  一致性硬规则。

下面 10 套 palette 仅作**灵感**，不是限定——可直接选用，也可据论文气质 /
用户的 `color_scheme` 描述自造一套协调配色。色号为 6 位 hex（写进 spec 的
`theme.*` 需带 `#`）：

| Palette | Primary | Secondary | Accent |
|---|---|---|---|
| **Midnight Executive** | `1E2761` navy | `CADCFC` ice blue | `FFFFFF` white |
| **Forest & Moss** | `2C5F2D` forest | `97BC62` moss | `F5F5F5` cream |
| **Coral Energy** | `F96167` coral | `F9E795` gold | `2F3C7E` navy |
| **Warm Terracotta** | `B85042` terracotta | `E7E8D1` sand | `A7BEAE` sage |
| **Ocean Gradient** | `065A82` deep blue | `1C7293` teal | `21295C` midnight |
| **Charcoal Minimal** | `36454F` charcoal | `F2F2F2` off-white | `212121` black |
| **Teal Trust** | `028090` teal | `00A896` seafoam | `02C39A` mint |
| **Berry & Cream** | `6D2E46` berry | `A26769` dusty rose | `ECE2D0` cream |
| **Sage Calm** | `84B59F` sage | `69A297` eucalyptus | `50808E` slate |
| **Cherry Bold** | `990011` cherry | `FCF6F5` off-white | `2F3C7E` navy |

**原则**：

- 论文主图的主色是 X？挑 palette 时让 primary 与 X **协调**（同色系或互补），而非冲突
- **不要每篇论文都选蓝色**。这是 AI 默认的懒惰行为；蓝色已经被 OpenAI/Anthropic/Google 等用烂

## 字体

字体配对仅作**灵感**，不是限定——按论文调性自选一组 header + body。下面是配对方案（可直接选用，也可自配）：

| Header | Body |
|---|---|
| Georgia | Calibri |
| Arial Black | Arial |
| Calibri | Calibri Light |
| Cambria | Calibri |
| Trebuchet MS | Calibri |
| Impact | Arial |
| Palatino | Garamond |
| Consolas | Calibri |

**禁忌**：不要用 Comic Sans、Papyrus、Brush Script 这种休闲字体；不要 header
和 body 都用同一字体（除非是极简风且严格用粗细区分）。

## layout_kind 混用

`layout_kind` 由 Stage 3 的你按 slide role + 内容形态自行决定，不预设强制配对。

**反复同一种 layout 是 AI 生成的另一典型痕迹**——一组 slide 至少要混用 4 种以上 layout_kind。

## 0. 视觉一致性硬规则（**先于所有其他规则**遵守）

下面 4 条是 Stage 3 写 spec 时**最优先**执行的硬约束。其他设计建议（palette、字体、版式选择）都是在满足这 4 条的前提下做的二阶选择。

### 0.1 小标题字号、字体、位置 deck 内一致

**所有非 title slide / 非 conclusion 类（含 qna） slide 的 `role: "title"` text element 必须用同一套样式**——`fontSize`、`fontFace`、`color`、`x`、`y`、`w`、`h`、`bold` 都相同。

**具体值由 Stage 3 的你根据论文 / theme / 标题平均长度自行选定**（fontSize 在 28-40pt 区间内、y 在 0.3-0.5 内皆可），**但选定后整 deck 严格一致**：s02 用什么，s03 / s04 / s05 / ... / s11 都用同一组值。

**实现要点**：写第一张非 title slide 的 subtitle 时定一个样式 dict（如 `{"fontFace": "Georgia", "fontSize": 32, "color": "<theme.primary>", "x": 0.5, "y": 0.4, "w": 9.0, "h": 0.9, "bold": true}`），后续每张非 title/conclusion slide 直接**复用同一个 dict 的字段**，不要每张单独估。

**唯一例外**：

- title slide（s01）的大标题：通常字号更大（44-48pt）、位置更居中——这是 title slide 这一类自己的样式
- conclusion / qna slide 的大标题：可以与 title slide 同款（暗色背景 + 大字），形成 sandwich 结构

每一类**内**都要 deck 内一致（不是每张都不同）。

### 0.2 标题孤词避免

PptxGenJS textbox 文字超长时自动换行；render_pptx.py 已自动给 `role: "title"` 的 text element 加 `autoFit: true`，多数情况会自动缩字号保持单行。即便如此，Stage 3 仍要主动避免孤词：

- 标题字数与 textbox 宽度的搭配应让"绝大多数"标题单行装下；只对极少数特长标题靠 autoFit 兜底
- **不要**为了某一张特长标题而专门改它的 `fontSize`——那会破坏 0.1 的一致性。长标题的处理是改写更短，或让 autoFit 自动缩
- title slide 的论文标题特别长（> 8 词）时，把主标题字号从默认大字号下调一档（例如 48 → 36）即可——但 title slide 这一类内的所有标题都用同一字号

### 0.3 图片等比缩放（永远不会变形）

`render_pptx.py` 在生成 `.pptx` 之前会**用 PIL 读每个 image 的真实尺寸**，把 spec 里给的 `(x, y, w, h)` 当作"最大框"，自动算出"按原图比例等比缩放后的实际占位 + 在原 box 内居中"，再喂给 PptxGenJS。这一步发生在渲染管线 Python 端，**与 PptxGenJS 的 sizing 字段无关**，所以**所有图永远不会被横向/纵向拉伸**——表格里的字母数字宽高比始终与原 PNG 一致。

Stage 3 分配 image 的 `(w, h)` 时仍要尽量贴近原图比例（让等比缩放后空白最少）：

1. **先看原图实际宽高比**：`Image.open(path).size` 或目测整页 PNG 中 figure/table 的相对比例
2. 选 layout 内可用 box（如 `image_half_bleed` 的右半区域、`grid_2x2` 的某格）
3. **让 box 宽高比尽量接近原图比例**——这样图填满框、留白最少，视觉饱满
4. 不知道原图比例时，**用方形 box** (`w == h`) 是最安全的——render 会自动按原比例缩放并居中，永远不会变形

注：spec 里**不需要**写 `sizing` 字段——render 端会忽略它（因为已经在 Python 端把 (w, h) 调成实际占位，不依赖 PptxGenJS 的 sizing）。写了也无害，会被自动 pop 掉。

### 0.4 元素整体均衡分布（**整页 + 子区域**都要检查）

**原则**：slide 是 10" × 5.625" 的画布；所有 element 应**尽量铺满整张画布**，**不留某个方向上的大块空白**——既不能上下偏，也不能左右偏，更**不能某子区域内偏**。

> **QA 阶段强制执行**：本节 0.4.a / 0.4.b / 0.4.c 列的任何一项被违反在 QA 阶段
> 都按 **hard issue** 处理——必须改 `slide_spec.json` 修掉，不允许标 soft / 略过。
> 子代理 prompt 已要求按 hard 报告（见本文件末"QA 时的视觉子代理 prompt"节），
> 你自己复审子代理报告时也不要把这些塞进 "soft" 桶——一句"看起来 OK / 略
> 空属软问题"就跳过的判断是本 skill **最常翻车的错误**。详见末节"QA 修问题原则"。

#### 0.4.a 整页 bbox 检查

- **垂直**：`max(y + h)` ≥ 4.0"（元素延伸到 slide 的 ~70% 高度以下）
- **水平**：`max(x + w)` ≥ 8.5" 且 `min(x)` ≤ 0.7"（元素触及左右两边）

#### 0.4.b 子区域均衡（**最容易翻车**的检查，用户视觉感受主要看这里）

整页 bbox 满了不代表视觉饱满 —— `two_column` / `image_half_bleed` 这种**双栏 layout** 必须额外检查左右两栏**各自**的垂直占位：

- **左右栏 max(y + h) 差 ≤ 0.6"**：例如左栏 4 条 bullets 只到 y=4.0，右栏图占到 y=5.0 → 差 1.0" 太大，左下方留半 inch+ 空白，视觉就"挤上半"
- **判断方法**：把 elements 按 x_center 分成左半（< 5"）和右半（≥ 5"），两组各自的 max(y+h) 应接近

**两栏不齐时的修复**：按末节"QA 修问题原则"的 **3 杠杆模型**（调文字量 > 调
bullet 间隔 > 调图片大小，可叠加）。不齐多因两栏内容量不平衡 → 优先给短栏加
实质内容（杠杆 1）并把其 bullet element 的 `y` 重新铺满该栏高度（杠杆 2），
仍不够再等比调图（杠杆 3）。

#### 0.4.c 单栏 / icon_rows / stat_callout 也要检查内部分布

- **bullet list**：bullets 默认已是独立 element；若它们只占 box 上半（典型 4 条只占 3.5" box 的 2"），按 3 杠杆模型调（加文字量 / 拉大 bullet 间隔铺满该区）
- **icon_rows**：3-4 个 icon + 文本块的 y 应**等距分布**到 box 全高，不要堆在中间或上方

#### 0.4.d 禁止

- 把 body bullet 字号改小到 < 16pt 强行铺满
- 把 element 拉宽到 > 10" 让 PptxGenJS 自动溢出（内容会被裁掉）
- bullet 内容只占 box 1/3——bullets 本应默认分开，按 3 杠杆模型调（加文字量 / 拉间隔），不靠缩 box 假装贴合

## 视觉丰富度建议

下面两条是**美观提示，不是硬规则**——不进 0 节硬检查、QA 不因此判 fail；但能把"正确但平淡"的页面抬到有专业感。

### A. Bullet 前给引导符（**强烈建议**）

body 列表项别留成无标记的纯文本行（像一堵文字墙）。每条 bullet 前应有
list-item 引导符——**用一个独立 `kind:"icon"` 元素**当引导符（语义化图标最佳；
只想要中性 marker 时用 `FaCircle` / `FaSquare` / `FaAngleRight` 这类几何小图标，
见 [pptxgenjs.md](pptxgenjs.md) "Icons"）。

- **禁用 PptxGenJS 默认 `bullet: true`**——它出的默认圆点太丑；自定义
  `bullet:{code}` 顶层布尔也不透传，这条路整体别走
- **禁**在 text 里手打 `"• "` / `"- "`（pptxgenjs.md 坑：会变双 bullet）

与 0.4.b / "QA 修问题原则"的**拆成多个独立 text element**兼容：拆开后**每个**
单行 element 各自配一个 marker icon，别拆完把引导符弄丢。

**引导符与文字必须垂直居中对齐（铁律）**：marker icon 的 box 矮（如 `h≈0.2`），
配对文字框高且常 `valign:"middle"`（`h≈0.5–0.66`）——两者视觉中心都是 `y+h/2`，
随手同 `y` 会让引导符整排偏上，"符号没对齐"肉眼可见（视觉 QA 子代理易漏报，
靠下面的量化自检兜住）。

- **公式**：`icon_y = text_y + (text_h − icon_h) / 2`（icon 垂直中心 == 文字框
  中心；多行 bullet 同理，icon 落在文字块中点）
- 水平：icon 右缘与文字左缘留 ~0.1" gap
- **收尾用脚本对每个 leader+text 配对批量自检** `icon.y+icon.h/2 ≈ text.y+text.h/2`
  （差 > 0.02" 即肉眼可见偏移），别靠目测

### B. 结构性组合下垫圆角矩形（建议）

非标题的"大字 + 小字"（如 KPI 数字 + 说明）或"icon + 短语"这类成组结构，
可在其下垫一个低调的圆角矩形（`ROUNDED_RECTANGLE` + `rectRadius`，浅色填充，`z` 置于内容之下）增加层次与卡片感。

- API 见 [pptxgenjs.md](pptxgenjs.md)；**注意其坑 #8**：圆角矩形别再叠矩形
  accent 边条（盖不住圆角），要描边用 ROUNDED_RECTANGLE 自身的 `line`

## 论文场景独有的设计取舍

### 1. 公式

PptxGenJS 不擅长渲染数学。**优先看 `paper_meta.json/equations[]`**（mineru 后端会自动填）：

```json
{"id": "eq_5", "page": 6,
 "bbox": [0.18, 0.34, 0.50, 0.04],
 "latex": "PE _ {(pos, 2 i)} = \\sin (pos / 1 0 0 0 0 ^ {2 i / d _ {\\mathrm {model}}})"}
```

#### 处理优先级（必须按顺序判断，**不要直接默认裁图**）

**第一步：判断 latex 是否"简单"**：清洗后的 latex 字符串里**没有任何**下面的关键字 → 简单：

```
\sum   \int   \prod   \begin{matrix}   \begin{cases}   \begin{align}   \\\\
```

**第二步：按下面两选一**（不允许"两个都做"）：

| 公式类型 | 处理 | 写到 spec 的形式 |
|---|---|---|
| **简单**（默认） | **Unicode rewrite** 写 text element | 一行字符串，fontFace 用 Cambria，例：`Attention(Q,K,V) = softmax(QK^T / √d_k) V` 或 `PE(pos, 2i) = sin(pos / 10000^(2i/d))` |
| **复杂** | `equations[i].bbox` + `page_screenshot.py` 裁原 PDF 行，作 image element | image element 指向裁出的 PNG |

**第三步**（独立于上面）：**永远**把原始 `latex` 字串写进 `speaker_notes` 兜底——后续修订或换渲染器时还能找回原内容。

#### 禁止双重展示（**最常见错误**）

**deck 上同一公式只表达一次（二选一）**：bullet 已写 Unicode → 不再加该公式的 image 元素，省下的空间用来放可视化；裁图 → bullet **不重复**写公式。

### 2. 论文 figure 的尺寸

论文里的图通常 4:3 或更接近正方形。`LAYOUT_16x9` 的 slide 是 10×5.625"，把图
塞进 `image_half_bleed` 时：

- 单图：宽 4.5–5"，高自适应（保持比例，不要拉伸）
- 多面板组合图（如论文 Figure 1 是 6 个子图组成）：考虑只截论文图的**一部分**
  作为 slide 元素（用 `page_screenshot.py` 给 bbox），slide 上塞 6 个会糊
- 裁剪 bbox 的来源与 QA 重裁规则**同下方 §3 表格**：以 mineru 原始框为基准定向微调，不凭空目测

### 3. 表格

论文 result table 通常列多 + 文字密。**不要用 PptxGenJS table 重建**（手写
50 行 cell，调对齐调到崩溃）。直接：

- 整页 PNG 裁剪 result table 区域 → 当 image 元素
- 旁边用一两句 bullet 高亮"我们的方法 +X.Y 优于 baseline"

**裁切 bbox（figure 与 table 同规则）：第一刀必须是 mineru 原框本身，QA 重裁也只在原框上动那一条边——全程不凭空目测整页**

> ⚠️ **本 skill 实测最常见的执行翻车**：Agent"自作主张"跳过下面第 1 步、在裁出
> 第一版前就去看 `pages/page-NN.png` 估框 → figure 切标题、table 卷 caption / 缺
> 关键行，重裁两三次还裁不准。规则早已写死，翻车几乎都因没按第 1 步抢跑。
> **铁律：`page_screenshot.py` 第一次调用的 bbox 必须逐值等于 `captions[i].bbox`，
> 不许先目测。** 觉得"原框肯定不准、先看页面再估更快"——这个念头本身就是翻车点，
> 原框第一刀 + 单边微调几乎总比重估快且准。

1. **第一刀＝原框原值（不准先目测）**：把 `figures_index.json/captions[i].bbox`（`mineru:vlm` 检出）的四元组**原封不动**传 `page_screenshot.py` 裁第一版，**裁出这一版之前不许看 `pages/page-NN.png`**。**`bbox_confidence == high` 不等于边缘干净**——实测 mineru 常把 `y` 起点压在子图标题 / 图注行上，导致切标题或卷入 caption；这是预期内的，靠第 2 步对那一条边的微调解决，**不是丢开原框重估的理由**。
2. **QA 发现裁不干净时——不要丢开原始框重新目测**。看 QA 渲染图判断**哪条边多了 / 少了**，只在原始 bbox 上对那条边做定向增量微调：
   - 顶部切了内容（子图标题、首行被切）→ `y` 调小、`h` 同步调大（向上扩）
   - 底部 / 某侧卷入 caption 或正文 → 对应 `h` / `w` 调小（向内收）
   - 一次只动一条边一个小量（≈0.01–0.03），重裁 → 再看，通常一两轮收敛。**原始框 x/w 与大致位置通常已对，错的只是某一条边**——改那条边，别整体重估
   - **表格须保留自身上下框线**（booktabs `\toprule` / `\bottomrule`）。向下收顶边去掉 caption 时**停在 `\toprule` 上沿**、别收过头把顶线裁没；少了上/下框线的表看着是"开口/破的"
3. 仅当 `bbox` 字段完全缺失（脚本与 mineru 都没定位，少见）才退到看 `pages/page-NN.png` 估框，仍**宁紧勿松**、`--pad 0.005` 兜底

**figure 与 table 同理**：本规则对论文 figure 的 `page_screenshot.py` 裁剪一并适用。

### 4. 文字量由空间决定（不设词数上限）

不设"每页 ≤ N 词 / 每 bullet ≤ N 词"这类硬限。文字量服务于一个目标：
**这页被内容填满、既不留白也不超框**。

- **下限（防留白）**：内容（视觉元素 + 文字）须撑满画布，满足 0.4 节的
  `max(y+h) ≥ 4.0"`、栏均衡、box≈内容高 等检查。文字太少导致留白时，**首选
  补充实质内容**（多一条要点 / 加一句 takeaway / 配 caption），不靠拉大字号
  或撑高 box 假装填满
- **上限（防溢出）**：文字不能超出 box / 画布。**字号下限是物理可读性红线**：
  title ≥ 36pt、body ≥ 16pt（≤ 14pt 后排看不见）。溢出按末节"QA 修问题原则"
  的 3 杠杆修（先精简文字量）；到红线还放不下 = 内容真太多 → 拆成两页，不靠缩字号硬塞
- **bullets 默认拆成独立 text element**：每条一个 element，`y` 在可用高度内
  分布（**近期实测分开排版稳定优于单 textbox 多行**，是默认做法，不是补救
  手段）。仅 ≤2 条的极短列表才用单 element 多行。默认分开后，留白 / 溢出可
  直接用 3 杠杆调（尤其杠杆 2 调 bullet 间隔），无需临时重排
- **每页必须有视觉元素**：图 / 表 / icon / chart / 有意义 shape 至少其一，
  无纯文字页（官方 pptx skill "Don't create text-only slides"）。先定视觉占
  多少，剩余空间用文字补到充实
- 仍守死的一条：**bullet 是提炼后的要点，不是论文摘要的搬运**——"短"由"是不是
  一个清晰单点"判断，不由数词判断

### 5. Sandwich 结构

dark 配色的 `title` 和 `conclusion`/`qna`，中间内容用 light 配色。这种"暗-亮-暗"
结构让听众心理上有"开头—主体—收尾"的节奏感。在 `theme` 里仍然单一 palette，但
title/conclusion slide 用 `shape` 全屏 fill 主色作为背景即可。

### 6. 不要的东西（论文 deck 特别警惕）

- ❌ 标题下面加水平线条装饰（典型 AI 痕迹，官方 pptx skill 已警告 "NEVER use accent lines under titles"）
- ❌ 每张 slide 都 footer 写论文标题（重复噪声；只在 title slide 写一次足够）
- ❌ 整页公式直接抄（看不清）
- ❌ "感谢聆听" 这种纯礼仪 slide（占空间，conclusion 已经收尾了）
- ❌ 所有 slide 都用同一个 layout_kind
- ❌ 默认 PowerPoint 模板配色（Office 蓝白）

## QA 时的视觉子代理 prompt

走 [pptx skill 的 QA 一节](../SKILL.md#qa) 时，**直接用官方 prompt 模板**，
不要自己改写。论文 deck 在官方模板之外**额外加两段**附加要求：

> prompt 里 "Read and analyze these images" 列**哪些 slide** 按下方
> "QA 修问题原则" 第 5 步的复检收窄规则定（第 1 轮全部、复检轮只列
> flagged ∪ 改动页、末轮全量），不是每轮都列全 deck。

**加段 A：内容准确性**

> 此外特别检查：所有数字（百分比、提升量、模型规模）是否在 caption 或 paper
> 原文里能找到对应？bullet 措辞是否与论文 abstract / contributions 一致（不要
> 自己编造）？

**加段 B：留白 / 栏均衡 / 引导符对齐（按本文件 0.4 节 + A 节对齐铁律，必须按 hard issue 报告）**

> 对每张 slide **逐项汇报以下五个数值或判断**，不要笼统说"看起来 OK"：
>
> 1. 整页 `max(y + h)` 是多少？是否 ≥ 4.0"？低于即页面上重下空——**hard issue**
> 2. 如果是 `two_column` / `image_half_bleed`：把所有 element 按 x_center 分成
>    左半（< 5"）与右半（≥ 5"），两组各自的 `max(y + h)` 差是多少？是否 ≤ 0.6"？
>    超过即一侧"挤上半"——**hard issue**
> 3. 对每个含 N 条 bullets 的 textbox：N × 0.5"（实际内容高度估算）与 `box.h` 的
>    差是多少？是否 ≤ 0.6"？超过即"内容上塞、box 下空"——**hard issue**
> 4. 对每个卡片（rect / rounded_rect 容器）：底部空白高度（卡片下边沿 −
>    最低 element 下边沿）是多少？是否 ≤ 1.0"？超过即"卡片下半空"——**hard issue**
> 5. 引导符 icon 是否与配对 bullet text **肉眼明显错位**（图标明显偏在文字上方/
>    下方）？**只报肉眼明显的错位**——你看的是渲染图、读不到坐标，**不要臆造
>    `icon.y+icon.h/2` 之类数值，也别把"图标居中于多行文字块"误判成偏上**。精确的
>    `icon.y+icon.h/2 ≈ text.y+text.h/2`（≤0.02"）由主代理用坐标脚本自检（"视觉
>    丰富度建议 A"），不归你。
>
> 第 1–4 项与第 5 项的肉眼明显错位 **当 hard issue 上报**，**禁止**写 "soft / 略 / 看着可接受 / 大致 OK"
> 等模糊措辞——这些用语会让你在复审时跳过修复。

## QA 修问题原则（重读 0.4 节）

子代理回报问题后：

1. **留白 / 不均衡 / 引导符错位问题禁止标 soft 跳过**——加段 B 列的 5 类都是
   hard issue，必须修 `slide_spec.json`。常见错误判断："底部留白属软问题" /
   "符号差一点点没关系"——**错**，按 0.4 节与 A 节对齐铁律它们就是要修的。
   看到子代理把这些标 soft 也要 reclassify 成 hard 再修。
2. 修 `slide_spec.json` 对应字段；不要去改 `slide_outline.json`（除非问题在更
   上游，如 outline 选错了 figure_ref）。
3. **修留白 / 溢出只用 3 个杠杆**（优先级递减，可叠加）。bullets 默认已是
   独立 text element（见 §4），杠杆都在其上操作：
   1. **调文字量（最优先，治本）**：太空 → 补实质内容（多一条要点 / 展开
      过度提炼的点 / 加一句 takeaway / 配 caption）；溢出 → 精简到清晰单点。
      呼应 §4 的下限 / 上限
   2. **调 bullet 间隔**：把各 bullet element 的 `y` 在可用高度内重新均匀
      分布（或调 `paraSpaceAfter`）——太空拉大间距铺满，溢出收紧
   3. **调图片大小（最低）**：等比放大 / 缩小图片占位去吃掉 / 让出空间
      （受 0.3 约束，图不会变形；别为填空把小图硬拉大到糊）

   **可叠加**：太空 → 杠杆 1（加文字量）+ 杠杆 2（拉间距）同时用；溢出 →
   杠杆 1（精简）+ 杠杆 2（收间距）。先动 1，不够再叠 2，最后才 3。
4. **`valign:"top"` + 远超内容的高 box** 仍是反模式（内容挤上半、下方留白）；
   bullets 既默认分开就不该再出现单个大 textbox，按上面 3 杠杆调，别靠 valign 救。
5. 修完 `--from-stage render` **全量重渲**（render 便宜且确定，裁剪 / spec 改动
   要传导到整副；收窄的是下面贵的子代理逐页视觉审，不是 render）→ **再 QA**，
   要求子代理重新报告加段 B 五项，验证留白真没了、引导符真对齐了。**不允许"修完就交"**。

   **复检轮范围按官方 pptx skill 的 Verification Loop 收窄**（[QA 一节](../SKILL.md#qa)，
   官方原话 "Re-verify affected slides … Repeat until a full pass reveals no
   new issues"）——多轮视觉 QA 最大的 token 浪费就是每轮都把没碰过的页重新逐页
   喂子代理：

   - **第 1 轮**：全 deck 逐页（单个子代理，"Read and analyze these images" 列全部 slide jpg）
   - **第 2 轮起（复检）**：子代理只看 = 上一轮 flagged 的页 ∪ 本轮 spec 实际
     改动的页；images 列表只列这些，没碰过的页**不重新喂**
   - **收敛前末轮**：必做一次全 deck full pass（单子代理过全部页）——"一处修复
     常引入新问题"，官方要求 a full pass 无新问题才算过
   - hard-issue 判定、加段 B 五项、禁标 soft——**全不变**，只收窄"每轮看哪些页"
