---
name: paper2html
description: 将学术论文（PDF 或 MinerU 解析后的 Markdown）转换为可直接发布的、自包含的单页**项目主页**（self-contained index.html）——就是研究者常基于 GitHub Pages 做的那种论文宣传网页。当用户提到"把论文做成项目主页/网页"、"paper2html"、"生成论文 landing page / project page"、"把这篇 PDF 变成 HTML 网页"、"论文转网页"、"做一个论文主页"时触发。你主导的协调式：机械步骤（MinerU 解析 + 确定性事实抽取闸门1 + 生成后 QA 闸门2）调 scripts，**index.html 的设计与撰写由你亲手完成**（不调用任何 LLM API），可选多种设计语言。
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

# paper2html — 论文转单页项目主页（你主导的协调式）

把一篇论文 PDF 转成**自包含、可直接发布的单页项目网站**——研究者常基于 GitHub Pages 做的那种论文主页。
**你是主笔**：这份文件是配方，不是全自动脚本——没有 `main.py`、没有渲染器。机械步骤
（解析/抽取/QA）调用 `scripts/` 下的小工具；**论文理解、页面设计、index.html 撰写由你亲自完成**
（用 Read 看材料和图、用 Write 落 `index.html`），并在关键点用 `AskUserQuestion` 与用户确认。

```text
PDF
 → 解析+抽取        (parse_pdf.py：MinerU → clean.md + manifest.json + images/，闸门1)
 → 你读懂论文+定设计 (读 manifest + clean.md + 看图) → 选设计语言                 [确认设计方向]
 → 你亲手写主页      (按 references/ 设计语言与撰写规范) → index.html              [可选确认]
 → QA 校验          (validate.py：缺图/坏链/内容保真，闸门2) → 据报告修，循环
 → 单页项目主页 index.html（+ images/，可直接部署）
```

## How you run this skill

1. **一步步来**：机械步骤用 `Bash` 调脚本（绝对路径，无需 cd），设计与撰写你自己用 `Read`/`Write` 做。
2. **每个 Bash 块开头就地算 `WORKDIR`**（各 Bash 调用是独立 shell、不共享变量）：
   ```bash
   WORKDIR="$(dirname "$pdf_path")/.paper2anything/html"
   ```
   `$pdf_path` 是用户给的论文 PDF（每块重设一次）。脚本在 `${SKILL_DIR}/scripts`——`SKILL_DIR`
   是**本 skill 的目录**（见本 skill 顶部注入的 "Base directory for this skill: …"）；各 Bash 块独立 shell，
   用到它的块开头按需 `export SKILL_DIR=<那个目录>` 一次（和 `WORKDIR` 一样每块现设）。
3. **决策点用 `AskUserQuestion` 暂停**：读懂论文后确认**设计方向**（设计语言 / 主色 / 重点）；成稿后可再确认。
4. **忠实于 manifest，空缺由你兜底**：只用 `manifest.json` 的真实素材，不编造数字/作者/链接；manifest 抽空的字段
   （authors/abstract/links 等）据 `clean.md` 全文补全——你是主笔，确定性抽取只是脚手架。

---

## Step 0：环境与凭据

> **统一环境**：所有 `python` 命令都在 paper2anything 的统一 conda 环境（顶层 `environment.yml`），
> 以 `conda run -n paper2anything --no-capture-output` 为前缀。

凭据集中在包根 `.env`（从 `.env.example` 复制，已 gitignore），每个新 shell 先导出一次：

```bash
set -a; source <paper2anything 包根>/.env; set +a
```

本 skill **只需 `MINERU_API_TOKEN`**（解析 PDF）。**页面设计与撰写是你亲自做的，不调用任何 LLM API**，
故无需 OPENAI/LLM 等 key。

依赖自检：

```bash
conda run -n paper2anything --no-capture-output python -c "import requests, rich, dotenv, playwright" 2>&1
# render_check.py（Step 4 渲染自检）需 chromium 内核，首次跑前装一次：
#   conda run -n paper2anything --no-capture-output python -m playwright install chromium
```

---

## Step 1：解析 + 确定性抽取（脚本，闸门1）

```bash
pdf_path="/path/to/paper.pdf"          # ← 用户的论文 PDF
WORKDIR="$(dirname "$pdf_path")/.paper2anything/html"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/parse_pdf.py" "$pdf_path" --workdir "$WORKDIR"
```

产出（`$WORKDIR` 下）：
- `clean.md` —— normalize 后的全文 markdown（你通读用）
- `manifest.json` —— 确定性抽取的事实：title/authors/affiliations/abstract/links/claims/figures/tables/
  method_components/bibtex（附录已过滤；抽不到的字段留空，交你兜底）
- `images/` —— 页面引用的图实体（图 + 结果表截图），你以 `images/<name>` 引用
- `parsed/`（MinerU 原始解析，含 full.md 供重跑复用）、`logs/`

可选：知道论文规范链接时加 `--paper-url <URL>`（**不假设 arxiv**，不传则 `links.paper` 留空）；`--code-url` 同理。

解析完，`Read` `manifest.json` 与 `clean.md` 通读全文。

---

## Step 2：读懂论文 + 定设计方向（你来做）[确认]

1. `Read` `manifest.json`（已核实素材）+ `clean.md`（全文）；`Read` `images/` 下的关键图，**亲眼**判断哪张
   适合做主图（hero）、哪些适合内嵌、哪些是结果表截图。
2. 读 `references/design-languages.md`，为这篇论文**确立一个设计概念**（选一种设计语言或融合：杂志/产品页/
   终端/海报/极简/看板；定主色、结构、什么元素主导）。不同论文应长得不一样，别复用上一篇的风格。
3. 用 `AskUserQuestion` 与用户确认**设计方向**（设计语言 / 主色调 / 突出什么）。带着确认结果再写页面。

补全空缺：若 manifest 的 authors/abstract/links 为空，据 `clean.md` 全文自己补（这是你兜底）。

---

## Step 3：亲手写 index.html（你来做）[可选确认]

按确认的设计方向，**亲自用 `Write` 落 `$WORKDIR/index.html`**——一个自包含、可部署的单页网站。
**先读 `references/html-authoring.md`**（硬约束与易错点），要点：

- 自包含：图用相对路径 `images/<filename>`（取自 manifest 的 `figures[].file` / `tables[].image`，parse_pdf 已复制进
  `images/`）；CSS 内联或 CDN；每张 `<img>` 非空 `alt`；不留 `href="#"`。
- 首屏轻盈（标题/作者/机构/资源按钮），主图作 teaser 一次性大图，再 abstract → claims → method → results →
  支撑图 → BibTeX（按论文气质调整，非强制）。
- 结果表**优先用截图**（`tables[].image`）。
- **figure CSS 别让边框框住空白、绝不为填空白拉伸图片**（细则见 references/html-authoring.md）。
- 忠实 manifest，不编造；空缺据全文补。

写完用 `AskUserQuestion` 给用户看设计与结构（可选），按反馈直接改 `index.html`。

---

## Step 4：QA 校验与修订（脚本，闸门2）

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/html"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/validate.py" --workdir "$WORKDIR"
```

校验你写的 `index.html` → `validation.json` + `qa_report.md`。`Read` `qa_report.md`：
- **error 必须清零**（缺 doctype/`</html>`、引用的 `images/<x>` 缺失、空 `href="#"`）。
- **warning 按需修**（标题/图/表未出现在页面、claims<3、空 alt 等）。
修法见 `references/qa-checklist.md`。修完 `index.html` 后**重跑 validate**，循环至 error 清零、warning 可接受。

`validate.py` 只查静态文本，**查不到渲染层视觉问题**（图变形/破损、横向溢出、MathJax 没渲出来）。
再跑一遍渲染自检（把 html-authoring.md "渲染后自检" 那条工具化）：

```bash
# 桌面宽 + 移动宽都要过——移动端最容易暴露横向溢出 / 宽表被裁 / 长公式溢出
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/render_check.py" "$WORKDIR/index.html" 1200
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/render_check.py" "$WORKDIR/index.html" 390
```

退出码 0=过、1=不过；输出 JSON 列出 `distorted_images`（rendered 与 natural 宽高比差 >0.02）、
`broken_images`、`h_overflow_px`、`clipped_content`（overflow:hidden 里被裁且滚不到的宽表/块）、
`mathjax.fail`（含残留未渲染 `$…$`/`$$…$$`）、`upscaled_images_warn`。
**两个宽度的硬指标都要清零**（上采样是软警告，自己判），不过就改 `index.html` 重跑。

---

## Step 5：把成品归集到 PDF 旁（与 slides 的 `.pptx` 同级）

成品默认埋在 `.paper2anything/html/` 里不好找。定稿后把它复制一份到**与 PDF 同级**的
`<stem>_html/` 目录（`.paper2anything` 内副本保留不动），让用户在论文旁直接打开：

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/html"
DEST="${pdf_path%.*}_html"            # 与 PDF 同目录、同名 + _html 后缀
mkdir -p "$DEST"
cp "$WORKDIR/index.html" "$DEST/"
cp -r "$WORKDIR/images" "$DEST/"      # index.html 以 images/<file> 相对引用，须一并带上
```

`index.html` 是引用 `images/` 的单页站点，故整组放进 `<stem>_html/` 子目录、引用不破；
打开 `<stem>_html/index.html` 即最终主页。

---

## 产物位置

中间产物落在论文旁 `<pdf目录>/.paper2anything/html/`，**最终成品另复制到 PDF 同级的 `<stem>_html/`**（Step 5）：

| 路径 | 内容 | 谁写 |
|---|---|---|
| `.paper2anything/html/clean.md` | normalize 后的全文 markdown | parse_pdf |
| `.paper2anything/html/manifest.json` | 确定性抽取的事实（闸门1） | parse_pdf |
| `.paper2anything/html/images/` | 页面引用的图 + 结果表截图 | parse_pdf |
| `.paper2anything/html/index.html` | 自包含单页项目主页 | **你** |
| `.paper2anything/html/validation.json` `qa_report.md` | QA 结果（闸门2） | validate |
| `.paper2anything/html/parsed/` `logs/` | MinerU 原始解析 / 各步骤 *_result.json | 脚本 |
| **`<pdf目录>/<stem>_html/`** | **成品归集**：`index.html` + `images/`，与 PDF 同级、可直接打开 | **你（Step 5）** |

重跑覆盖同一目录（无 task_id）。要留旧版本就先把 `index.html` 改名备份。Step 1 重跑默认复用 `parsed/full.md`，跳过 MinerU 云端解析。

---

## 排错

- **MinerU 解析失败**：核对 `MINERU_API_TOKEN`；PDF ≤200MB / ≤200 页；能访问 `mineru.net`。重跑 Step 1（覆盖）。
- **manifest 字段空（authors/abstract/links）**：确定性抽取局限（如论文无 `## Abstract` 标题、非 arxiv 论文无链接）——
  **正常**，据 `clean.md` 全文由你补全；不是 bug。
- **QA 报缺图**：只引用 `images/` 下真实存在的文件，文件名照抄 manifest，别拼错哈希名。
- **设计/撰写不需要 API key**：这两步是你亲自做的，不调用任何 LLM API。

---

## references/

- `design-languages.md` —— 六种设计语言 + 先立概念再布局 + 真实学术主页范式。
- `html-authoring.md` —— 撰写硬约束、figure CSS 易错点、自包含/部署、表格策略。
- `qa-checklist.md` —— QA 各检查项的含义与修法。
