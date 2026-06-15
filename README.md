# paper2anything

把一篇学术论文 PDF 一键转成**任意一种**对外产物的 skills 包。一个包，五个 skill，覆盖论文对外传播的主要形态：

| Skill | 把论文变成 | 产物 | 触发词（举例） |
| --- | --- | --- | --- |
| **paper2slides** | 演讲幻灯片 | `.pptx` | "把这篇论文做成 PPT"、"生成幻灯片"、"deck this paper" |
| **paper2poster** | 会议海报 | `poster.html` + `poster.png` | "make a poster from this paper"、"论文转海报" |
| **paper2html** | 单页项目主页 | `index.html`（自包含） | "论文转网页"、"生成 project page / landing page" |
| **paper2xhs** | 小红书帖子 | `xhs_post.json/md` + 封面 | "把这篇论文发小红书"、"论文转小红书" |
| **paper2wechat** | 公众号推文 | `wechat_article.md/html` + 封面 | "把论文写成公众号文章"、"论文转公众号" |

每个子目录都是一个独立、可被 Claude 自动触发的 skill（各有 `SKILL.md`）。它们共享同一个 conda 环境，但各自的工作流、产物与凭据相互独立。

---

## 目录结构

```
paper2anything/
├── environment.yml          # 统一 conda 环境定义（覆盖全部 5 个 skill）
├── .env.example             # 统一凭据模板（复制为 .env 填写）
├── .gitignore               # 忽略 .env / 各 skill 产出目录 / __pycache__ 等
├── README.md                # 本文件
├── paper2slides/            # 论文 → .pptx
│   ├── SKILL.md
│   ├── references/          # 设计风格、大纲启发式、pipeline、schema、pptxgenjs
│   └── scripts/             # extract_paper / render_pptx / page_screenshot / workdir + lib/
├── paper2poster/            # 论文 → 海报 HTML/PNG
│   ├── SKILL.md
│   ├── references/          # 海报示例、模板、配色、版式指南
│   ├── scripts/             # parse_pdf / auto_outline / score_poster_visual / paper_quiz / ...
│   └── assets/
├── paper2html/              # 论文 → 单页项目主页
│   ├── SKILL.md
│   ├── paper2html/          # Python 包（agent/pipeline/html_generator/mineru_client/config + prompts/）
│   └── briefs/  examples/
├── paper2xhs/               # 论文 → 小红书
│   ├── SKILL.md
│   ├── scripts/             # main + stage1..7 + utils
│   └── examples/
└── paper2wechat/            # 论文 → 公众号
    ├── SKILL.md
    └── scripts/             # main + stage1..7 + utils
```

---

## 统一环境安装

5 个 skill 共用一个 conda 环境 `paper2anything`，所有 `python` 命令都以
`conda run -n paper2anything --no-capture-output` 为前缀（或先 `conda activate paper2anything`）。

```bash
# 在 paper2anything 包根目录
conda env create -f environment.yml
conda activate paper2anything
```

`environment.yml` 已合并 5 个 skill 的全部 Python 依赖（pdfplumber / pypdf / PyMuPDF /
Pillow / markitdown / requests / openai / anthropic / playwright / rich / click /
python-dotenv / md2wechat …）。

### 系统级依赖（不在 conda 内，需另装）

| 工具 | 用途 | 哪个 skill |
| --- | --- | --- |
| poppler-utils（`pdfimages` / `pdftoppm`） | PDF 取图 | paper2slides |
| libreoffice（`soffice`） | pptx → pdf（视觉 QA） | paper2slides |
| Node.js + pptxgenjs（+ react-icons/react/react-dom/sharp） | PPT 渲染（icon 光栅仅 icon 元素需要） | paper2slides |
| `playwright install chromium` | 浏览器渲染/截图 | paper2poster、paper2xhs |
| md2wechat（已在 conda 内 pip 装；源码版见 paper2wechat/SKILL.md） | Markdown → 公众号 HTML | paper2wechat |
| 可选 tesseract-ocr | 扫描版论文 OCR | paper2slides |

---

## 凭据配置（统一）

所有 skill 的凭据集中在**包根一个 `.env`**（从 `.env.example` 复制填写，应 gitignore）。
每个新 shell 运行任何 skill 前，导出一次到环境变量——之后所有
`conda run -n paper2anything ... python ...` 都能读到：

```bash
cp .env.example .env          # 首次：复制后填入你的 key
set -a; source .env; set +a   # 每个新 shell 一次（或写进 ~/.bashrc 一劳永逸）
```

各 skill 实际用到的 key（不用的留空即可）：

| Skill | 用到的 key |
| --- | --- |
| paper2slides | `MINERU_API_TOKEN`（云解析；`--backend local` 时不需要） |
| paper2poster | `MINERU_API_TOKEN`、`DASHSCOPE_API_KEY`(或 `API_KEY`) |
| paper2html | `MINERU_API_TOKEN`、`OPENAI_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` |
| paper2xhs | `ANTHROPIC_API_KEY`、`MINERU_API_TOKEN`（封面另需 `OPENAI_API_KEY`） |
| paper2wechat | `ANTHROPIC_API_KEY`、`MINERU_API_TOKEN`、`WECHAT_APPID`/`WECHAT_APP_SECRET`（封面另需 `OPENAI_API_KEY`） |

> 5 个 skill 统一用 `MINERU_API_TOKEN`。各脚本最终都从 `os.environ` 读取，故只需这一个
> `.env` + 一次 `source`，无需各 skill 的局部配置文件；脚本启动时也会自动 `load_dotenv`
> 包根 `.env`（忘了 `source` 也能跑，但已 export 的环境变量优先）。

---

## 产物位置（统一）

5 个 skill 的产物都落在**论文同目录**下的 `.paper2anything/<skill>/`，跟着论文走、互不干扰：

| Skill | 产物位置（相对论文目录） |
| --- | --- |
| paper2slides | `<论文名>.pptx`（直接在论文目录，重名 `-v2/-v3`）；中间产物 `.paper2anything/slides/<论文名>/` |
| paper2poster | `.paper2anything/poster/`（`poster.html` / `poster.png` + 全部中间产物） |
| paper2html | `.paper2anything/html/<输入名>_agent/`（`index.html` 等；`-o` 可覆盖） |
| paper2xhs | `.paper2anything/xhs/<task_id>/`（`xhs/xhs_post.json\|md`、封面） |
| paper2wechat | `.paper2anything/wechat/<task_id>/`（`wechat/wechat_article.md\|html`、封面） |

> 论文目录只读时，slides 回退到 `~/.cache/paper2anything/slides/`。这些产物目录已在包根 `.gitignore` 忽略。

---

## 怎么用

直接对 Claude 说出你的意图，对应 skill 会被自动触发，例如：

- "把 `~/paper.pdf` 做成 PPT" → **paper2slides**
- "用这篇论文做一张会议海报" → **paper2poster**
- "把这篇 PDF 变成项目主页" → **paper2html**
- "帮我把这篇论文发小红书" → **paper2xhs**
- "把这篇论文写成公众号推文" → **paper2wechat**

每个 skill 的完整流水线、阶段协议、产物 schema 与排错见各自的 `SKILL.md`。
