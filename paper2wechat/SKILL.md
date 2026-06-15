---
name: paper2wechat
description: 把学术论文 PDF 转成微信公众号深度解读推文（长文 + 配图 + 封面）。Claude 主导设计的协调式：机械活（MinerU 解析 PDF、生成封面、md2wechat 排版）交给 scripts/ 下的小工具，论文理解、文章结构、长文撰写由 Claude 亲自完成并在关键点与用户确认。当用户说“论文转公众号”、“paper2wechat”、“把论文写成公众号文章”、“论文转微信推文”、“PDF 转公众号”时触发。
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

# paper2wechat — 论文转公众号深度解读（Claude 主导的协调式）

把一篇论文 PDF 写成**学术深度解读型**公众号长文。**Claude（你）是主笔**：这份文件是配方，
不是全自动脚本——没有 `main.py`。机械步骤（解析 / 封面 / 排版）调用 `scripts/` 下的小工具；
**论文理解、文章结构、长文撰写由你亲自完成**，并在关键点用 `AskUserQuestion` 与用户确认。

目标读者：有 AI/ML 背景的研究者、工程师、学生——读得懂方法细节、关心贡献与局限。

```text
PDF
 → 解析            (stage2_parse.py：MinerU → parsed/ + figures/，含表格)
 → 你读懂论文       (读 parsed/ + 看 figures/) → understanding/paper_understanding.json   [确认切入角度]
 → 你写深度解读长文  (结构自由、配图、忠实准确) → wechat/wechat_article.md + .json          [确认]
 → 封面            (stage6_cover.py：横版 900×383，优先复用论文原图)
 → md2wechat 排版   (stage7_publish.py：→ 公众号 HTML / 草稿)
 → 公众号推文
```

## How Claude runs this skill

1. **一步步来**：机械步骤用 `Bash` 调脚本，创作步骤你自己用 `Read` / `Write` 做。
2. **每个 Bash 块开头就地算 `WORKDIR`**（各 Bash 调用是独立 shell、不共享变量）：
   ```bash
   WORKDIR="$(dirname "$pdf_path")/.paper2anything/wechat"
   ```
   `$pdf_path` 是用户给的论文 PDF（每块重设一次）。脚本在 `${CLAUDE_SKILL_DIR}/scripts`。
3. **两个决策点用 `AskUserQuestion` 暂停**：① 读懂论文后确认“切入角度/深度/篇幅”；② 长文成稿后确认。
4. **深度解读 = 读懂后用自己的话讲清楚**：可以加直觉解释、类比、背景、应用与局限，让有背景的读者快速吃透这篇论文——但**忠实于论文、不夸大、不编造数据**。

---

## Step 0：环境与凭据

> **统一环境**：所有 `python` 命令都在 paper2anything 的统一 conda 环境（顶层 `environment.yml`），以 `conda run -n paper2anything --no-capture-output` 为前缀。md2wechat 已含在该环境中。

凭据集中在包根 `.env`（从 `.env.example` 复制，已 gitignore），每个新 shell 先导出一次：

```bash
set -a; source <paper2anything 包根>/.env; set +a
```

本 skill 用到的 key（**理解与撰文由你 Claude 亲自做，不调用 Anthropic API，故无需 `ANTHROPIC_API_KEY`**）：
- `MINERU_API_TOKEN` — 解析 PDF（必填）
- `OPENAI_API_KEY`(+ `OPENAI_BASE_URL`) — 仅封面 AI 生成；无则自动跳过封面
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
  python "${CLAUDE_SKILL_DIR}/scripts/stage2_parse.py" "$pdf_path" --workdir "$WORKDIR"
```

产出（`$WORKDIR` 下）：`parsed/paper_meta.json`、`parsed/sections.json`、`parsed/figures_index.json`、`parsed/tables_index.json`（`[{table_id, caption, html, image_path, page}]`）、`parsed/references.json`，以及 `figures/*`（含表格图）。

解析完，`Read` `parsed/sections.json` 与 `parsed/paper_meta.json` 通读全文。

---

## Step 2：读懂论文 → 写 understanding（你来做）[确认]

深度解读的地基，**你自己做判断**：

1. `Read` `parsed/sections.json`（全文）+ `paper_meta.json`；`Read` `figures_index.json` / `tables_index.json` 的图注表注，并**实际 `Read` 关键图**（`figures/` 下）判断哪些值得内嵌、哪张适合做横版封面。
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
     "important_figures": [
       {"figure_id": "fig_1", "image_path": "<figures_index.json 里的真实路径>",
        "suitable_for_cover": true, "importance_score": 0.9,
        "wechat_caption": "图1：……（≤50字中文图注）", "description": "图说明"}
     ]
   }
   ```
   - `important_figures` 必须含 `image_path`（取自 `figures_index.json`，真实存在）、`suitable_for_cover`、`importance_score`——**封面脚本（Step 4）靠它选横版原图**；漏了就只能 AI 生成。
3. 用 `AskUserQuestion` 与用户确认**切入角度 / 深度 / 目标篇幅**（如：偏方法细节还是偏直觉科普、约 1500 还是 2500 字）。

---

## Step 3：写深度解读长文（你来做）[确认]

按公众号深度解读风格**亲自撰写**，用 `Write` 落 `wechat/wechat_article.md` 和 `wechat/wechat_article.json`。

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
- **配图**：在合适位置插 `![图注](../figures/<图片名>.png)`（路径相对 `wechat/` 目录，故用 `../figures/...`；图片名取自 `figures_index.json` 的 `image_path` 文件名）。
- **忠实准确**：实验数字照实引用，不夸大、不编造；可有解读和洞察，但区分“论文说的”与“你的点评”。

产物 —— `wechat/wechat_article.md`：第一行 `# {标题}`，然后正文（含配图）。
`wechat/wechat_article.json`（供排版脚本读 title/digest/word_count）：
```json
{"title": "最终标题", "digest": "公众号摘要，≤120字", "word_count": 2200}
```

写完用 `AskUserQuestion` 给用户看标题 + 摘要 + 小节结构，确认或按反馈修改（可直接改 .md/.json）。

---

## Step 4：生成封面（脚本，可选）

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/wechat"
conda run -n paper2anything --no-capture-output \
  python "${CLAUDE_SKILL_DIR}/scripts/stage6_cover.py" --workdir "$WORKDIR"
```

横版 900×383 JPG：优先把 `understanding.important_figures` 里 `suitable_for_cover` 最高分的论文原图裁成封面；否则（配了 `OPENAI_API_KEY` 时）AI 生成横版图再裁剪；都没有则 `skipped`。产出 `wechat/cover.jpg`。

---

## Step 5：md2wechat 排版与发布准备（脚本）

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/wechat"
conda run -n paper2anything --no-capture-output \
  python "${CLAUDE_SKILL_DIR}/scripts/stage7_publish.py" --workdir "$WORKDIR"
```

读 `wechat/wechat_article.md`（+ `.json` 的 title/digest）+ `cover.jpg`，调 md2wechat 转成公众号 HTML 草稿；**md2wechat 不可用时自动降级**为“把 Markdown 手动粘贴到公众号编辑器”的指引（不报错）。脚本会打印发布步骤（mp.weixin.qq.com → 新建图文 → 粘贴 → 传封面 → 发布）。

---

## 产物位置

全部落在论文旁 `<pdf目录>/.paper2anything/wechat/`：

| 子目录 | 内容 | 谁写 |
|---|---|---|
| `parsed/` | MinerU PIR（meta/sections/figures_index/tables_index/references） | stage2_parse |
| `figures/` | 论文插图 + 表格图实体 | stage2_parse |
| `understanding/paper_understanding.json` | 论文理解 + important_figures | **你（Claude）** |
| `wechat/wechat_article.md` `.json` | 深度解读长文 + 元数据 | **你（Claude）** |
| `wechat/cover.jpg` | 横版封面 | stage6_cover |
| `wechat/wechat_article.html` | md2wechat 排版结果 | stage7_publish |
| `logs/` | 各脚本 `*_result.json` | 脚本 |

重跑覆盖同一目录（无 task_id）。要留旧版本就先把 `wechat/` 改名备份。

---

## 排错

- **MinerU 解析失败**：核对 `MINERU_API_TOKEN`；PDF ≤200MB / ≤200 页；能访问 `mineru.net`。重跑 Step 1（覆盖）。
- **封面没生成**：没配 `OPENAI_API_KEY` 会自动跳过（正常）；想复用原图，确保 `understanding.important_figures` 有 `suitable_for_cover:true` 且 `image_path` 存在的**横版**图。
- **md2wechat 不可用**：Step 5 自动降级为输出 Markdown 供手动粘贴；要排版就装 md2wechat 或在 `.env` 配 `MD2WECHAT_CMD`。
- **理解/撰文不需要 API key**：这两步是你（Claude）亲自做的，不调用 Anthropic API。
