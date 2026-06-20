---
name: paper2xhs
description: 把学术论文 PDF 转成小红书帖子（标题 + 正文 + 标签 + 封面）。你主导设计的协调式：机械活（MinerU 解析 PDF、生成封面、半自动发布）交给 scripts/ 下的小工具，论文理解、选题角度、文案撰写由你亲自完成并在关键点与用户确认。当用户说“论文转小红书”、“paper2xhs”、“把这篇论文发小红书”、“论文转社交媒体”、“PDF 转小红书帖子”时触发。
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

# paper2xhs — 论文转小红书（你主导的协调式）

把一篇论文 PDF 转成小红书帖子。**你是主笔**：这份文件是配方，不是全自动脚本——
没有 `main.py`。机械步骤（解析 / 封面 / 发布）调用 `scripts/` 下的小工具；**论文理解、
选题角度、文案撰写由你亲自完成**（用 Read 看材料、用 Write 落产物），并在关键点用
`AskUserQuestion` 与用户确认。

```text
PDF
 → 解析            (parse_pdf.py：MinerU → parsed/ + figures/)
 → 你读懂论文       (读 parsed/ + 看 figures/) → understanding/paper_understanding.json   [确认选题角度]
 → 你写小红书文案    (标题/正文/标签/封面文字) → xhs_post.json + xhs_post.md            [确认文案]
 → 封面            (cover.py：优先复用论文原图，否则 AI 生成)
 → 半自动发布       (publish.py，可选)
 → 小红书帖子
```

## How you run this skill

1. **一步步来**：机械步骤用 `Bash` 调脚本，创作步骤你自己用 `Read` / `Write` 做。不要试图一条命令跑完。
2. **每个 Bash 块开头就地算 `WORKDIR`**——各 Bash 调用是独立 shell、不共享变量，所以别指望 `export` 跨步存活：
   ```bash
   WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs"
   ```
   其中 `$pdf_path` 是用户给的论文 PDF 路径（每个块都重新设一次）。脚本在 `${SKILL_DIR}/scripts`——`SKILL_DIR`
   是**本 skill 的目录**（见本 skill 顶部注入的 "Base directory for this skill: …"）；各 Bash 块独立 shell，
   用到它的块开头按需 `export SKILL_DIR=<那个目录>` 一次（和 `WORKDIR` 一样每块现设）。
3. **在两个决策点用 `AskUserQuestion` 暂停**：① 读懂论文后确认“选题角度”；② 文案成稿后确认。用户想改，可直接改产物 JSON/MD 或告诉你改。
4. **小红书是“准确、不夸大的科普”**：忠实反映论文贡献，口语化、有钩子，但**绝不编造数据或夸大结论**。

---

## Step 0：环境与凭据

> **统一环境**：所有 `python` 命令都在 paper2anything 的统一 conda 环境里（顶层 `environment.yml` 创建），命令以 `conda run -n paper2anything --no-capture-output` 为前缀。

凭据集中在 paper2anything 包根的 `.env`（从 `.env.example` 复制，已 gitignore）。每个新 shell 先导出一次：

```bash
set -a; source <paper2anything 包根>/.env; set +a
```

本 skill 用到的 key（**理解与文案由你亲自做，不调用任何 LLM API**）：
- `MINERU_API_TOKEN` — 解析 PDF（必填）
- `OPENAI_API_KEY`(+ `OPENAI_BASE_URL`) — 仅封面 AI 生成；无则自动跳过封面
- `XHS_SKILLS_DIR` — 仅半自动发布（克隆 [xiaohongshu-skills](https://github.com/autoclaw-cc/xiaohongshu-skills)）；不发布可不配

依赖自检（缺啥按提示装；依赖统一在 `environment.yml`）：

```bash
conda run -n paper2anything --no-capture-output python -c "import requests, rich, dotenv" 2>&1
```

---

## Step 1：解析 PDF（脚本）

```bash
pdf_path="/path/to/paper.pdf"          # ← 用户的论文 PDF
WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/parse_pdf.py" "$pdf_path" --workdir "$WORKDIR"
```

产出（`$WORKDIR` 下）：
- `parsed/paper_meta.json`（title / authors / abstract）、`parsed/sections.json`（`[{title, content}]`）、`parsed/figures_index.json`（`[{figure_id, caption, image_path, page}]`，`image_path` 已指向 `figures/` 实体）、`parsed/references.json`
- `figures/*` 论文插图实体

解析完，先 `Read` `parsed/sections.json` 与 `parsed/paper_meta.json` 通读全文。

---

## Step 2：读懂论文 → 写 understanding（你来做）[确认]

这是创作的地基，**你自己做判断**，不要交给脚本：

1. `Read` `parsed/sections.json`（全文）+ `parsed/paper_meta.json`；`Read` `parsed/figures_index.json` 看图注（个别图 caption 可能为空，以实际看图为准），并**实际 `Read` 几张候选图片**（`figures/` 下）判断哪些清晰、适合做封面或配图——图注说“framework”的图在小图里未必好看，只有你的眼睛能判断。
2. 用 `Write` 落 `understanding/paper_understanding.json`，schema：
   ```json
   {
     "paper_title": "...", "method_name": "方法简称（如 AccKV）",
     "one_sentence_summary": "一句话讲清这篇做了什么",
     "problem": "解决什么问题", "method": "怎么做的",
     "highlights": ["有数据支撑的亮点1", "创新点2", "应用价值3"],
     "experiment_results": ["关键数据1（含数字）", "..."],
     "keywords": ["领域关键词", "..."],
     "important_figures": [
       {"figure_id": "fig_1", "image_path": "<figures_index.json 里的真实路径>",
        "suitable_for_cover": true, "importance_score": 0.9, "description": "图说明"}
     ]
   }
   ```
   - `important_figures` 必须含 `image_path`（取自 `parsed/figures_index.json`，指向真实存在的图）、`suitable_for_cover`、`importance_score`——**封面脚本（Step 4）靠这几个字段选原图**；漏了就只能 AI 生成。
3. 用 `AskUserQuestion` 与用户确认**选题角度**：这篇论文发小红书主打哪个亮点 / 用什么钩子 / 面向哪类读者。带着确认结果再写文案。

---

## Step 3：写小红书帖子（你来做）[确认]

按小红书风格**亲自撰写**，用 `Write` 落 `xhs_post.json` 和 `xhs_post.md`。

**小红书文案规则（领域知识）：**
- **标题** ≤20 字，吸睛：含核心价值、或数字、或对比、或悬念式提问。
- **正文 300–600 字**，结构：
  1. 开头 1–2 句钩子，抓住注意力
  2. 这篇论文是什么、解决什么问题（2–3 句）
  3. 3–5 个核心亮点，每点用 emoji 开头，简洁有力
  4. 1–3 个关键实验数据，要具体
  5. 对读者有什么用（1–2 句）
  6. 结尾引导互动（如“你觉得这方法能用在哪？”）
- **风格**：口语化、易读、不端学术腔，但**忠实准确、不夸大、不编数据**。
- **标签** 8–12 个，写在正文末尾；`hashtags` 字段同步放这些标签（发布脚本读 `hashtags`）。
- **封面文字** `cover_text` ≤15 字（封面大字用）。

产物 schema —— `xhs_post.json`：
```json
{"title": "...", "body": "含 emoji/换行，末尾带标签的完整正文",
 "hashtags": ["#标签1", "#标签2"], "cover_text": "≤15字封面词", "paper_title_zh": "论文中文标题"}
```
`xhs_post.md`：第一行 `# {title}`，然后正文；可在顶部放 `![封面](cover.png)` 占位（封面在 Step 4 生成）。

写完用 `AskUserQuestion` 给用户看标题 + 正文摘要，确认或按反馈修改（可直接改 JSON/MD）。

---

## Step 4：生成封面（脚本，可选）

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/cover.py" --workdir "$WORKDIR"
```

逻辑：优先复用 `understanding.important_figures` 里 `suitable_for_cover` 最高分的论文原图；没有合适原图且配了 `OPENAI_API_KEY` 时用 `OPENAI_IMAGE_MODEL`（默认 `gpt-image-1`）按 `cover_text` 生成竖版封面；都没有则 `skipped`（不阻断流程）。产出 `cover.png`。

---

## Step 5：半自动发布（脚本，可选）

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/publish.py" --workdir "$WORKDIR"
```

读 `xhs_post.json`（title/body/hashtags）+ `cover.png`，通过外部 `xiaohongshu-skills` 填到发布页，**用户在浏览器确认后**才点发布。需 `XHS_SKILLS_DIR` + Chrome 扩展；未配置就跳过这步，把产物路径告诉用户让其手动发。

---

## 产物位置

全部落在论文旁 `<pdf目录>/.paper2anything/xhs/`（成品与 parsed/ 等平级，无嵌套子目录）：

| 路径 | 内容 | 谁写 |
|---|---|---|
| `parsed/` | MinerU PIR（meta/sections/figures_index/references） | parse_pdf |
| `figures/` | 论文插图实体 | parse_pdf |
| `understanding/paper_understanding.json` | 论文理解 + important_figures | **你** |
| `xhs_post.json` `xhs_post.md` | 小红书文案 | **你** |
| `cover.png` | 封面 | cover |
| `logs/` | 各脚本 `*_result.json` | 脚本 |

重跑覆盖同一目录（无 task_id）。要保留旧版本就先把工作区 `.paper2anything/xhs/` 改名备份。

---

## 排错

- **MinerU 解析失败**：核对 `.env` 的 `MINERU_API_TOKEN`（在 https://mineru.net 申请）；PDF 应 ≤200MB / ≤200 页；能访问 `mineru.net`。重跑 Step 1 即可（覆盖）。
- **封面没生成**：没配 `OPENAI_API_KEY` 会自动跳过（正常）；想要 AI 封面就配上，或确保 `understanding.important_figures` 有 `suitable_for_cover:true` 且 `image_path` 存在的图以复用原图。
- **发布步骤报错**：多为 `XHS_SKILLS_DIR` 未配或 Chrome 扩展未装；不发布可跳过 Step 5，手动发产物。
- **理解/文案不需要 API key**：这两步是你亲自做的，不调用任何 LLM API。
