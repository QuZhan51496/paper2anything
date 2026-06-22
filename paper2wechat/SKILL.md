---
name: paper2wechat
description: 把学术论文 PDF 转成微信公众号深度解读推文（长文 + 配图 + 封面）。你主导设计的协调式：机械活（MinerU 解析 PDF、生成封面、md2wechat 排版）交给 scripts/ 下的小工具，论文理解、文章结构、长文撰写由你亲自完成并在关键点与用户确认。当用户说“论文转公众号”、“paper2wechat”、“把论文写成公众号文章”、“论文转微信推文”、“PDF 转公众号”时触发。
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

# paper2wechat — 论文转公众号深度解读（你主导的协调式）

把一篇论文 PDF 写成**学术深度解读型**公众号长文。**你是主笔**：这份文件是配方，
不是全自动脚本——没有 `main.py`。机械步骤（解析 / 封面 / 排版）调用 `scripts/` 下的小工具；
**论文理解、文章结构、长文撰写由你亲自完成**，并在关键点用 `AskUserQuestion` 与用户确认。

目标读者：有 AI/ML 背景的研究者、工程师、学生——读得懂方法细节、关心贡献与局限。

```text
PDF
 → 解析            (parse_pdf.py：MinerU → parsed/ + figures/，含表格)
 → 你读懂论文       (读 parsed/ + 看 figures/) → understanding/paper_understanding.json   [确认切入角度]
 → 你写深度解读长文  (结构自由、配图、忠实准确) → wechat_article.md + .json          [确认]
 → 封面            (cover.py：默认 API 生图 gpt-image-2 横版 900×383；无 key/key 不可用回退本地合成复用原图)
 → md2wechat 排版   (publish.py：→ 公众号 HTML / 草稿)
 → 公众号推文
```

## How you run this skill

1. **一步步来**：机械步骤用 `Bash` 调脚本，创作步骤你自己用 `Read` / `Write` 做。
2. **每个 Bash 块开头就地算 `WORKDIR`**（各 Bash 调用是独立 shell、不共享变量）：
   ```bash
   WORKDIR="$(dirname "$pdf_path")/.paper2anything/wechat"
   ```
   `$pdf_path` 是用户给的论文 PDF（每块重设一次）。脚本在 `${SKILL_DIR}/scripts`——`SKILL_DIR`
   是**本 skill 的目录**（见本 skill 顶部注入的 "Base directory for this skill: …"）；各 Bash 块独立 shell，
   用到它的块开头按需 `export SKILL_DIR=<那个目录>` 一次（和 `WORKDIR` 一样每块现设）。
3. **两个决策点用 `AskUserQuestion` 暂停**：① 读懂论文后确认“切入角度/深度/篇幅”；② 长文成稿后确认。
4. **深度解读 = 读懂后用自己的话讲清楚**：可以加直觉解释、类比、背景、应用与局限，让有背景的读者快速吃透这篇论文——但**忠实于论文、不夸大、不编造数据**。

---

## Step 0：环境与凭据

> **统一环境**：所有 `python` 命令都在 paper2anything 的统一 conda 环境（顶层 `environment.yml`），以 `conda run -n paper2anything --no-capture-output` 为前缀。md2wechat 已含在该环境中。

凭据集中在包根 `.env`（从 `.env.example` 复制，已 gitignore），每个新 shell 先导出一次：

```bash
set -a; source <paper2anything 包根>/.env; set +a
```

本 skill 用到的 key（**理解与撰文由你亲自做，不调用任何 LLM API**）：
- `MINERU_API_TOKEN` — 解析 PDF（必填）
- `OPENAI_API_KEY`(+ `OPENAI_BASE_URL`) — 封面默认走它生图（gpt-image-2）；无 key 或 key 不可用时回退本地合成（复用论文原图）
- `MD2WECHAT_CMD` / `MD2WECHAT_THEME` — md2wechat 排版（不在 PATH 时填 CMD；主题默认 `default`）

依赖自检（缺啥按提示装；依赖统一在 `environment.yml`）：

```bash
conda run -n paper2anything --no-capture-output python -c "import requests, rich, dotenv" 2>&1
md2wechat --help >/dev/null 2>&1 && echo "md2wechat 就绪" || echo "md2wechat 未就绪（可后置；缺它 Step 5 会降级为输出 Markdown 供手动粘贴）"
```

---

## Step 1：解析 PDF（脚本）

```bash
pdf_path="/path/to/paper.pdf"          # ← 用户的论文 PDF
WORKDIR="$(dirname "$pdf_path")/.paper2anything/wechat"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/parse_pdf.py" "$pdf_path" --workdir "$WORKDIR"
```

产出（`$WORKDIR` 下）：`parsed/paper_meta.json`、`parsed/sections.json`、`parsed/figures_index.json`、`parsed/tables_index.json`（`[{table_id, caption, html, image_path, page}]`）、`parsed/references.json`，以及 `figures/*`（含表格图）。

解析完，`Read` `parsed/sections.json` 与 `parsed/paper_meta.json` 通读全文。

---

## Step 2：读懂论文 → 写 understanding（你来做）[确认]

深度解读的地基，**你自己做判断**：

1. `Read` `parsed/sections.json`（全文）+ `paper_meta.json`；`Read` `figures_index.json` / `tables_index.json` 的图注表注（个别 caption 可能为空，以实际看图为准），并**实际 `Read` 关键图**（`figures/` 下）判断哪些值得内嵌、哪张适合做横版封面。
2. 用 `Write` 落 `understanding/paper_understanding.json`：
   ```json
   {
     "paper_title": "...", "method_name": "方法简称",
     "one_sentence_summary": "一句话讲清贡献",
     "problem": "背景与要解决的问题", "method": "核心方法（技术要点，用文字不用公式）",
     "method_intuition": "直觉性解释/类比，帮读者吃透",
     "contributions": ["贡献1", "贡献2"],
     "comparison": "与主要 baseline 的关键差异",
     "experiment_results": ["关键数据（含具体数字）", "..."],
     "limitations": "论文承认的局限或潜在不足",
     "keywords": ["关键词", "..."],
     "cover_palette": {"bg": "#F4F5F7", "accent": "#2E86AB"},
     "important_figures": [
       {"figure_id": "fig_1", "image_path": "<figures_index.json 里的真实路径>",
        "suitable_for_cover": true, "importance_score": 0.9,
        "wechat_caption": "图1：……（≤50字中文图注）", "description": "图说明"}
     ]
   }
   ```
   - `important_figures` 必须含 `image_path`（取自 `figures_index.json`，真实存在）、`suitable_for_cover`、`importance_score`——封面默认走 API 生图（gpt-image-2），仅当 `OPENAI_API_KEY` 未配/不可用时回退本地合成、靠它选横版原图；漏了则回退时无图 → 封面 `skipped`。
   - `cover_palette`（可选）：本地合成回退路径的配色，按论文领域选 `bg`(浅色打底) + `accent`(强调色)，标题字色随底色深浅自动适配。参考浅色调：通用 `#F4F5F7`+`#2E86AB`、生物 `#EEF6F0`+`#2D8A5F`、物理数学 `#F1ECF8`+`#6A30C2`、工程 `#FBF0EC`+`#D85A3C`、社科 `#F4EEF2`+`#8A5A78`、化学 `#EAF4F8`+`#0E86C0`。
3. 用 `AskUserQuestion` 与用户确认**切入角度 / 深度 / 目标篇幅**（如：偏方法细节还是偏直觉科普、约 1500 还是 2500 字）。

---

## Step 3：写深度解读长文（你来做）[确认]

按公众号深度解读风格**亲自撰写**，用 `Write` 落 `wechat_article.md` 和 `wechat_article.json`。

**公众号深度解读规则（领域知识）：**
- **篇幅**约 1500–2500 字（按论文复杂度和 Step 2 的约定增减）。
- **结构自由、随论文走**——不强求固定四节。一个好用的骨架：
  1. 导语：这篇为什么值得读（1 段，抛出问题或亮点钩子）
  2. 背景与问题：现有方法的不足
  3. 核心方法：讲清思路，**配框架图**，可用类比/直觉解释
  4. 关键实验与结果：摆具体数字，**配结果图/表**
  5. 意义、应用与局限：能用在哪、有什么不足
  6. 结尾：一句话总结 + 延伸思考
- 用 H2（`## 小节标题`）分节；关键技术术语首次出现给中英文、可 `**加粗**`。
- **配图**：在合适位置插 `![图注](figures/<图片名>)`（md 与 figures/ 同在工作区根 `.paper2anything/wechat/` 下，故用 `figures/...`；`<图片名>` 直接取自 `figures_index.json` 的 `image_path` 文件名、**含其真实扩展名**（MinerU 多为 `.jpg`），勿臆改后缀）。
- **忠实准确**：实验数字照实引用，不夸大、不编造；可有解读和洞察，但区分“论文说的”与“你的点评”。

产物 —— `wechat_article.md`：第一行 `# {标题}`，然后正文（含配图）。
`wechat_article.json`（供排版脚本读 title/digest/word_count）：
```json
{"title": "最终标题", "digest": "公众号摘要，≤120字", "word_count": 2200}
```

写完用 `AskUserQuestion` 给用户看标题 + 摘要 + 小节结构，确认或按反馈修改（可直接改 .md/.json）。

---

## Step 4：生成封面（脚本，可选）

**封面主标题此刻由你现拟**（你已读透论文，比从 JSON 里捡更贴切），经 `--title` 传入：

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/wechat"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/cover.py" --workdir "$WORKDIR" \
  --title "你拟的封面主标题"
```

横版 900×383 JPG：**默认用 `OPENAI_IMAGE_MODEL`（默认 `gpt-image-2`）AI 生成横版图再裁剪**，主标题用你传入的 `--title`（留空才回退文章标题/`method_name`）；未配 `OPENAI_API_KEY` 或 key 不可用时回退本地合成——把 `understanding.important_figures` 里 `suitable_for_cover` 最高分的论文原图裁成封面（叠加 `--title`，配色取 `cover_palette`）；两者都不可用则 `skipped`。产出 `cover.jpg`。

---

## Step 5：md2wechat 排版与发布准备（脚本）

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/wechat"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/publish.py" --workdir "$WORKDIR"
```

读 `wechat_article.md`（+ `.json` 的 title/digest）+ `cover.jpg`，调 md2wechat 转成公众号 HTML 草稿；**md2wechat 不可用时自动降级**为“把 Markdown 手动粘贴到公众号编辑器”的指引（不报错）。脚本会打印发布步骤（mp.weixin.qq.com → 新建图文 → 粘贴 → 传封面 → 发布）。

---

## Step 6：把成品归集到 PDF 旁（与 slides 的 `.pptx` 同级）

成品默认埋在 `.paper2anything/wechat/` 里不好找。长文+配图+封面定稿后（无论是否走 Step 5 排版），把它们复制
一份到**与 PDF 同级**的 `<stem>_wechat/` 目录（`.paper2anything` 内副本保留不动），让用户在论文旁直接取用：

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/wechat"
DEST="${pdf_path%.*}_wechat"          # 与 PDF 同目录、同名 + _wechat 后缀
mkdir -p "$DEST"
cp "$WORKDIR/wechat_article.md" "$WORKDIR/wechat_article.json" "$DEST/"
[ -f "$WORKDIR/cover.jpg" ] && cp "$WORKDIR/cover.jpg" "$DEST/"                  # 封面可能 skipped，存在才复制
[ -f "$WORKDIR/wechat_article.html" ] && cp "$WORKDIR/wechat_article.html" "$DEST/"  # md2wechat 排版结果（若 Step 5 跑了）
cp -r "$WORKDIR/figures" "$DEST/"     # 正文以 figures/<name> 相对引用配图，须一并带上
```

`wechat_article.md` 以 `![图注](figures/<name>)` 相对引用配图，故长文与 `figures/` 整组放进 `<stem>_wechat/` 子目录、引用不破。

---

## 产物位置

中间产物落在论文旁 `<pdf目录>/.paper2anything/wechat/`，**最终成品另复制到 PDF 同级的 `<stem>_wechat/`**（Step 6）：

| 路径 | 内容 | 谁写 |
|---|---|---|
| `.paper2anything/wechat/parsed/` | MinerU PIR（meta/sections/figures_index/tables_index/references） | parse_pdf |
| `.paper2anything/wechat/figures/` | 论文插图 + 表格图实体 | parse_pdf |
| `.paper2anything/wechat/understanding/paper_understanding.json` | 论文理解 + important_figures | **你** |
| `.paper2anything/wechat/wechat_article.md` `.json` | 深度解读长文 + 元数据 | **你** |
| `.paper2anything/wechat/cover.jpg` | 横版封面 | cover |
| `.paper2anything/wechat/wechat_article.html` | md2wechat 排版结果 | publish |
| `.paper2anything/wechat/logs/` | 各脚本 `*_result.json` | 脚本 |
| **`<pdf目录>/<stem>_wechat/`** | **成品归集**：`wechat_article.md` + `.json` + `cover.jpg` + `figures/`，与 PDF 同级 | **你（Step 6）** |

重跑覆盖同一目录（无 task_id）。要留旧版本就先把工作区 `.paper2anything/wechat/` 改名备份。

---

## 排错

- **MinerU 解析失败**：核对 `MINERU_API_TOKEN`；PDF ≤200MB / ≤200 页；能访问 `mineru.net`。重跑 Step 1（覆盖）。
- **封面没生成（`skipped`）**：通常是既没配可用 `OPENAI_API_KEY`、又没有可复用的论文原图。配上 key 走 AI 生图，或确保 `understanding.important_figures` 有 `suitable_for_cover:true` 且 `image_path` 存在的**横版**图以供本地合成回退。
- **md2wechat 不可用**：Step 5 自动降级为输出 Markdown 供手动粘贴；要排版就装 md2wechat 或在 `.env` 配 `MD2WECHAT_CMD`。
- **理解/撰文不需要 API key**：这两步是你亲自做的，不调用任何 LLM API。
