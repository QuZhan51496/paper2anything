<!-- 本仓库 README 有中英两版，请保持同步：改动内容时，README.md（英文，默认）和 README.zh-CN.md（中文）两份都要改。 -->
<div align="center">

<img src="assets/logo.png" alt="paper2anything logo" width="140" />

# paper2anything

[![Project Page](https://img.shields.io/badge/Project_Page-Live-2ea44f?logo=githubpages&logoColor=white)](https://quzhan51496.github.io/paper2anything/) [![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-blue?logo=anthropic&logoColor=white)](https://docs.anthropic.com/en/docs/claude-code) [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

[English](README.md) | **简体中文**

[效果展示](#效果展示) · [环境安装](#环境安装) · [怎么用](#怎么用) · [产物位置](#产物位置) · [目录结构](#目录结构) · [贡献者](#贡献者) · [致谢](#致谢)

</div>

<div align="center">
<img src="assets/marquee.webp" alt="paper2anything 真实产物走马灯——幻灯片、海报、项目主页、小红书与公众号封面" width="100%" />
</div>

把一篇学术论文 PDF 转成任意一种宣传产物的 skills 包，覆盖论文传播的主要形态：

| Skill | 把论文变成 | 产物 | 触发词（举例） |
| --- | --- | --- | --- |
| **paper2slides** | 演讲幻灯片 | `.pptx` | "把这篇论文做成 PPT"、"生成幻灯片"、"deck this paper" |
| **paper2poster** | 会议海报 | `poster.html` + `poster.png` | "make a poster from this paper"、"论文转海报" |
| **paper2html** | 单页项目主页 | `index.html` | "论文转网页"、"生成 project page / landing page" |
| **paper2xhs** | 小红书帖子 | `xhs_post.json/md` + 封面 | "把这篇论文发小红书"、"论文转小红书" |
| **paper2wechat** | 公众号推文 | `wechat_article.md/html` + 封面 | "把论文写成公众号文章"、"论文转公众号" |

每个子目录都是一个独立、可自动触发的 skill（各有 `SKILL.md`）。

---

## 效果展示

### paper2slides

**paper2slides** 产物示例——8 套 deck，覆盖不同研究领域（HCI / VR、计算机视觉、药物发现、安全与溯源、多模态智能体、量子计算、优化、机器学习理论）：

<div align="center">
<img src="assets/showcase/paper2slides/SHOWCASE_decks.png" alt="paper2slides 从论文 PDF 生成的 8 套幻灯片，覆盖不同研究领域" width="100%" />
</div>

### paper2poster

**paper2poster** 产物示例——9 张海报，覆盖 9 个研究领域（药物设计、图形学、人机交互、材料科学、X 射线检测、NLP / 大模型安全、光学与光子学、统计机器学习、计算机视觉）：

<div align="center">
<img src="assets/showcase/paper2poster/SHOWCASE_3x3.png" alt="paper2poster 从论文 PDF 生成的 9 张会议海报，覆盖 9 个研究领域" width="100%" />
</div>

### paper2html

**paper2html** 产物示例——8 个项目主页，覆盖不同研究领域（HCI / VR、药物发现、机器写作、机器人、安全、软件工程、智能体技能、金融交易）：

<div align="center">
<img src="assets/showcase/paper2html/SHOWCASE_pages.png" alt="paper2html 从论文 PDF 生成的 8 个项目主页，覆盖不同研究领域" width="100%" />
</div>

### paper2xhs

**paper2xhs** 产物示例——10 个项目主页，覆盖不同研究领域（AI、生物学、计算机视觉、多模态智能体、机器人、软件工程、AI for Science、优化、大语言模型）：

<div align="center">
<img src="assets/showcase/paper2xhs/SHOWCASE_tenpapers.png" alt="paper2xhs 从论文 PDF 生成的 10 篇小红书笔记，覆盖不同研究领域" width="100%" />
</div>

### paper2wechat

**paper2wechat** 产物示例——12 个项目主页，覆盖不同研究领域（AI、生物学、计算机视觉、多模态智能体、机器人、软件工程、AI for Science、优化、大语言模型）：

<div align="center">
<img src="assets/showcase/paper2wechat/SHOWCASE_cover.jpg" alt="paper2wechat 从论文 PDF 生成的 12 篇微信公众号封面，覆盖不同研究领域" width="100%" />
</div>


---

## 环境安装

**Claude Code一键安装（推荐）**：

```bash
bash tools/install-linux.sh --create-env --shell-init     # Linux
bash tools/install-macos.sh --create-env --shell-init     # macOS
```

安装脚本会：① 把 5 个 skill 符号链接进 `~/.claude/skills/`；② 没有 `.env` 时从 `.env.example` 引导一份；③ 检查 conda 环境、系统依赖与 `MINERU_API_TOKEN`（用于论文提取）。命令里两个 flag 的作用（不需要可省去）：

- `--create-env`： `conda env create`（已存在则按 `environment.yml` 更新）+ 装 playwright chromium + 跑 pip 自检；
- `--shell-init`：（可选）把 `.env` 自动导出写进 shell 启动文件，新开 shell 即加载凭据。

跑完照脚本提示再补两步：

1. **填 `.env` 里的 `MINERU_API_TOKEN`**（必需）；
2. **装上它指出的缺失系统级依赖**（脚本会逐项检测并给出安装命令）。

需要手动安装时（如只用某个特定 skill），下面是等价拆解。

<details>
<summary><b>手动安装</b></summary>

### 注册 skill

把你要用的 skill 软链接进 `~/.claude/skills/`，Claude Code 才能发现并自动触发它：

```bash
# 在 paper2anything 包根目录；按需复制你要的 skill 那行
mkdir -p ~/.claude/skills
ln -sfn "$(pwd)/paper2slides"  ~/.claude/skills/paper2slides
ln -sfn "$(pwd)/paper2poster"  ~/.claude/skills/paper2poster
ln -sfn "$(pwd)/paper2html"    ~/.claude/skills/paper2html
ln -sfn "$(pwd)/paper2xhs"     ~/.claude/skills/paper2xhs
ln -sfn "$(pwd)/paper2wechat"  ~/.claude/skills/paper2wechat
```

### conda 环境

5 个 skill 共用一个 conda 环境 `paper2anything`。

```bash
# 在 paper2anything 包根目录
conda env create -f environment.yml
conda activate paper2anything
```

### 系统级依赖

| 工具 | 用途 | 哪个 skill | 安装命令 |
| --- | --- | --- | --- |
| poppler-utils（`pdftoppm`） | PDF 渲染 | paper2slides | `sudo apt install poppler-utils`（Linux）/ `brew install poppler`（macOS） |
| libreoffice（`soffice`） | 视觉 QA | paper2slides | `sudo apt install libreoffice`（Linux）/ `brew install --cask libreoffice`（macOS） |
| Node.js | JS 运行时 | paper2slides | Linux 用 NodeSource（apt 自带过旧，见表下注）/ `brew install node`（macOS） |
| pptxgenjs + react-icons/react/react-dom/sharp | PPT 渲染 | paper2slides | `npm install -g pptxgenjs react-icons react react-dom sharp`（Linux 前加 `sudo`） |

**Node.js（Linux）**：sharp 要求 Node ≥20.9.0，用 NodeSource 装：

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs
```

### 凭据配置

所有 skill 的凭据集中在**包根一个 `.env`**（从 `.env.example` 复制填写）。复制后填入你的 key 即可：

```bash
cp .env.example .env          # 首次：复制后填入你的 key
```

可选：把 `.env` 导出写进 shell 启动文件。安装时可加 `--shell-init` 自动写入（见「环境安装」），或手动加这一行：

```bash
set -a; source <paper2anything 包根>/.env; set +a
```

</details>

---

## 怎么用

直接说出你的意图，对应 skill 会被自动触发，例如：

- "把 `path/to/paper.pdf` 做成 PPT" → **paper2slides**
- "用这篇论文做一张会议海报" → **paper2poster**
- "把这篇 PDF 变成项目主页" → **paper2html**
- "帮我把这篇论文发小红书" → **paper2xhs**
- "把这篇论文写成公众号推文" → **paper2wechat**

或直接用斜杠命令显式调用，跟上 PDF 路径：

```
/paper2slides path/to/paper.pdf
/paper2poster path/to/paper.pdf
/paper2html   path/to/paper.pdf
/paper2xhs    path/to/paper.pdf
/paper2wechat path/to/paper.pdf
```

---

## 产物位置

每个 skill 的最终成品都落在论文同目录下；全部中间产物保留在同目录的 `.paper2anything/<skill>/<论文名>/`：

| Skill | 最终成品 | 中间产物 |
| --- | --- | --- |
| paper2slides | `<论文名>_slides/`（`<论文名>.pptx`） | `.paper2anything/slides/<论文名>/` |
| paper2poster | `<论文名>_poster/`（`poster.png` + `poster.html` + `images/`） | `.paper2anything/poster/<论文名>/` |
| paper2html | `<论文名>_html/`（`index.html` + `images/`） | `.paper2anything/html/<论文名>/` |
| paper2xhs | `<论文名>_xhs/`（`xhs_post.md` + `.json` + `cover.png`） | `.paper2anything/xhs/<论文名>/` |
| paper2wechat | `<论文名>_wechat/`（`wechat_article.md` + `.json` + `cover.jpg` + `figures/`） | `.paper2anything/wechat/<论文名>/` |

---

## 目录结构

```
paper2anything/
├── environment.yml          # python 环境
├── .env.example             # 凭据模板（复制为 .env 填写）
├── .gitignore               # 忽略 .env / __pycache__ 等
├── LICENSE                  # Apache-2.0
├── README.md                # 英文版（默认）
├── README.zh-CN.md          # 中文版（本文件）
├── tools/                   # 安装脚本
├── assets/                  # 静态文件
│   └── showcase/            # 各 skill 产物样例（assets/showcase/<skill>/）
├── paper2slides/            # 论文 → slides
│   ├── SKILL.md
│   ├── references/          # 设计风格、大纲启发式、pipeline、schema、pptxgenjs
│   └── scripts/             # parse_pdf / render_pptx / page_screenshot / workdir + lib/
├── paper2poster/            # 论文 → 海报 HTML/PNG
│   ├── SKILL.md
│   ├── references/          # 海报示例、配色、版式指南
│   └── scripts/             # parse_pdf / auto_outline / geom_check / collect_figures / screenshot / check_env
├── paper2html/              # 论文 → 单页项目主页
│   ├── SKILL.md
│   ├── references/          # 设计语言、HTML 撰写规范、QA 清单
│   └── scripts/             # parse_pdf / validate / render_check 等 + lib/（解析/抽取/QA，无渲染器）
├── paper2xhs/               # 论文 → 小红书
│   ├── SKILL.md
│   ├── references/          # 发布指引
│   └── scripts/             # parse_pdf / cover / publish / xhs_login + utils
└── paper2wechat/            # 论文 → 公众号
    ├── SKILL.md
    └── scripts/             # parse_pdf / cover / publish + utils
```

---

## 贡献者

**[AI4GC Lab](https://ai4gc.org/)** 各 skill 主导设计:

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/melonthrower">
        <img src="https://github.com/melonthrower.png" width="80" alt="Honghui Sheng"/><br/>
        <sub><b>Honghui Sheng</b></sub>
      </a><br/>
      <sub>paper2poster</sub>
    </td>
    <td align="center">
      <a href="https://github.com/YuanDaoze">
        <img src="https://github.com/YuanDaoze.png" width="80" alt="Tao Xiong"/><br/>
        <sub><b>Tao Xiong</b></sub>
      </a><br/>
      <sub>paper2html</sub>
    </td>
    <td align="center">
      <a href="https://github.com/b7277">
        <img src="https://github.com/b7277.png" width="80" alt="Xinchen Xu"/><br/>
        <sub><b>Xinchen Xu</b></sub>
      </a><br/>
      <sub>paper2xhs &amp; paper2wechat</sub>
    </td>
  </tr>
</table>

---

## 致谢

paper2anything 由浙江大学 **[AI4GC Lab](https://ai4gc.org/)** 开发。

- 论文 PDF 解析能力由 **[MinerU](https://github.com/opendatalab/MinerU)** 提供。
- 小红书发布能力由 **[xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)** 提供。
- 公众号发布与排版能力由 **[md2wechat](https://pypi.org/project/md2wechat/)** 提供。
