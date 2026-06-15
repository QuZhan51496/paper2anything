---
name: paper2wechat
description: 将学术论文 PDF 转换为微信公众号推文草稿的完整流水线工具。当用户提到"论文转公众号"、"paper2wechat"、"把论文发到公众号"、"论文转微信推文"、"PDF 转公众号"、"帮我把这篇论文写成公众号文章"时触发。包含 7 个阶段：PDF 上传验证、MinerU 解析、论文深度理解（学术专业版）、公众号大纲结构化、长文生成、封面生成（可选）、md2wechat 格式化发布。
allowed-tools: Bash, Read, Write, Glob, Grep
---

# paper2wechat — 论文转微信公众号流水线

## 工具简介

paper2wechat 是一个将学术论文 PDF 转换为**学术深度解读型**微信公众号推文的 7 阶段流水线工具。

目标读者定位：有一定 AI/ML 背景的研究者、工程师、在读学生——读得懂公式描述、关心方法细节、希望快速理解一篇新论文的贡献与局限。

## 你的职责

当用户触发此 skill 时，你需要：
1. 引导用户完成环境准备（重点：md2wechat 安装）
2. 确认 PDF 文件路径
3. 执行流水线命令
4. 在每个关键阶段展示预览并等待用户确认
5. 处理错误和异常情况

---

## 第一步：定位脚本目录

所有 stage 脚本位于 `scripts/`（在 paper2wechat skill 目录下），**必须 `cd` 到该目录运行**（把下面路径替换成你的实际部署路径）：

```bash
cd <paper2anything 包根>/paper2wechat/scripts
ls main.py 2>/dev/null && echo "脚本目录正确" || echo "未找到 main.py"
```

---

## 第二步：环境检查

> **统一环境**：本 skill 所有 `python` 命令都运行在 paper2anything 包的统一 conda 环境里（由顶层 `environment.yml` 创建），命令均以 `conda run -n paper2anything --no-capture-output` 为前缀；下面的 `pip install` 仅在统一环境缺依赖时兜底。md2wechat 也已包含在统一环境中。

**检查 Python 依赖：**
```bash
conda run -n paper2anything --no-capture-output python -c "import anthropic, click, rich, dotenv" 2>&1
```

如果缺少依赖（依赖统一在顶层 `environment.yml`，各 skill 不再保留 requirements.txt）：
```bash
pip install anthropic click rich python-dotenv openai Pillow md2wechat
```

**检查 md2wechat（Stage 7 核心依赖）：**

md2wechat 用于将生成的 Markdown 转换为微信公众号兼容的 HTML 格式并辅助发布。

```bash
md2wechat --version 2>&1 || echo "未安装"
```

如果未安装，按以下步骤安装：
```bash
# 方式一：pip 安装
pip install md2wechat

# 方式二：从源码安装（推荐，功能更完整）
git clone https://github.com/geekjourneyx/md2wechat-skill.git ~/tools/md2wechat-skill
cd ~/tools/md2wechat-skill
pip install -e .
```

安装后验证：
```bash
md2wechat --help
```

在 `.env` 中配置 md2wechat 路径（如果不在 PATH 中）：
```
MD2WECHAT_CMD=/path/to/md2wechat
```

**统一凭据**：所有 key 集中在 paper2anything 包根的 `.env`（从 `.env.example` 复制填写，应 gitignore）。运行前在当前 shell 导出一次：
```bash
set -a; source <paper2anything 包根>/.env; set +a
```

本 skill 用到：
- `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL`（必填）
- `OPENAI_API_KEY`（仅封面 AI 生成时需要，可用 `--skip-cover` 跳过）
- `MINERU_API_TOKEN`（Stage 2 PDF 解析，必填）
- `WECHAT_APPID` / `WECHAT_APP_SECRET`、`MD2WECHAT_THEME` / `MD2WECHAT_CMD`（Stage 7）

> main.py 的 `load_dotenv()` 也会自动向上找到包根 `.env`。

**检查 MinerU API token：**
```bash
grep -q '^MINERU_API_TOKEN=..' <paper2anything 包根>/.env && echo "已配置" || echo "缺 token，请在 https://mineru.net 申请后填入 .env"
```

---

## 第三步：确认 PDF 路径

```bash
test -f "<用户提供的路径>" && echo "文件存在" || echo "文件不存在"
```

---

## 第四步：执行流水线

**标准运行（含人工确认，推荐）：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径>
```

**跳过封面生成：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --skip-cover
```

**跳过 md2wechat 格式化（仅生成 Markdown）：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --skip-publish
```

**全自动运行：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --no-confirm
```

**从指定阶段继续：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --resume <task_id> --from-stage <阶段编号>
```

---

## 流水线阶段说明

| 阶段 | 名称 | 关键输出 |
|------|------|----------|
| 1 | PDF 上传验证 | `raw/paper.pdf` |
| 2 | MinerU 解析 | `parsed/paper_meta.json` 等 |
| 3 | 论文深度理解（技术细节 + 相关工作对比） | `understanding/paper_understanding.json` |
| 4 | 公众号大纲结构化 | `assets/article_outline.json` |
| 5 | 公众号长文生成（2000-3500 字） | `wechat/wechat_article.md` |
| 6 | 封面生成（横版 900×383，可选） | `wechat/cover.jpg` |
| 7 | md2wechat 格式化 | `wechat/wechat_article.html` |

---

## Stage 3 阶段说明（重点）

Stage 3 使用 Claude Sonnet 进行**深度学术理解**，提取以下内容：

1. **技术细节提取**：详细描述方法的关键技术步骤、核心算法思路（用文字而非公式）
2. **相关工作对比**：明确列出与哪些 baseline 相比、具体差异在哪里
3. **图表角色分析**：每张图分析其在文章中的角色（architecture/result_table/comparison/ablation/other），标注是否适合在公众号文章中内嵌展示

Stage 3 输出的 `paper_understanding.json` 新增字段：
```json
{
  "technical_details": "方法的详细技术描述（3-5句，保留关键技术词汇）",
  "related_work_comparison": "与主要 baseline 的核心差异（2-3条对比）",
  "method_intuition": "方法的直觉性解释（类比或比喻，帮助读者理解）",
  "limitations": "论文承认的局限性或潜在不足"
}
```

---

## Stage 4 阶段说明（重点）

Stage 4 生成**公众号文章大纲**（而不是 XHS 的碎片化素材），输出 `article_outline.json`：

```json
{
  "title_candidates": ["标题1（含核心贡献词）", "标题2（问题切入）", "标题3（对比切入）"],
  "digest": "文章摘要，用于公众号列表页，概括核心贡献（100-120字）",
  "article_outline": [
    {
      "section_id": 1,
      "section_title": "研究背景与动机",
      "key_points": ["要点1", "要点2"],
      "writing_hints": "这一节重点说清楚问题是什么、为什么现有方法不够好",
      "suggested_figures": []
    },
    {
      "section_id": 2,
      "section_title": "方法介绍：XXX",
      "key_points": ["核心思路", "关键组件"],
      "writing_hints": "围绕架构图展开，用类比帮助读者理解",
      "suggested_figures": ["fig1"]
    }
  ],
  "cover_figure_id": "fig1",
  "inline_figures": [
    {
      "figure_id": "fig1",
      "insert_after_section": 2,
      "wechat_caption": "图1：XXX 方法整体框架",
      "role": "architecture"
    }
  ]
}
```

---

## Stage 5 阶段说明（重点）

Stage 5 基于 Stage 4 大纲生成完整的**学术深度解读型**公众号文章：

文章风格要求：
- 长度：2000-3500 字（正文）
- 结构：有 H2 级标题分节，逻辑清晰
- 语气：专业但不晦涩——保留关键技术术语，用文字描述核心公式
- 数字：关键实验数字必须保留（如"在 XX 数据集上提升了 3.2 个点"）
- 图表：在正文中用 `![图注](figure_path)` 引用关键图
- 结尾：包含"延伸阅读/思考"或对工作局限性的讨论

输出 `wechat_article.json`：
```json
{
  "title": "最终使用的标题",
  "digest": "100-120字摘要",
  "body_markdown": "完整正文（Markdown 格式）",
  "cover_figure_path": "figures/fig1.jpg",
  "word_count": 2500
}
```

---

## Stage 7 阶段说明

Stage 7 调用 md2wechat 将 Markdown 转换为微信公众号兼容 HTML，并准备草稿发布：

```bash
# md2wechat 将 Markdown → 微信格式 HTML
md2wechat --input wechat_article.md --output wechat_article.html --theme academic

# 生成的 HTML 可以：
# 1. 直接复制到微信公众号编辑器
# 2. 或通过微信 MP API 上传草稿
```

Stage 7 完成后，会在终端输出：
- HTML 文件路径（可复制到公众号编辑器）
- 文章标题、摘要、字数统计

---

## 查看生成结果

```bash
cat <论文目录>/.paper2anything/wechat/<task_id>/wechat/wechat_article.json
cat <论文目录>/.paper2anything/wechat/<task_id>/wechat/wechat_article.md
```

---

## 恢复中断的任务

```bash
ls <论文目录>/.paper2anything/wechat/
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --resume <task_id> --from-stage <阶段编号>
```

---

## 常见问题处理

**MinerU 解析失败：**
- 检查 `MINERU_API_TOKEN` 是否有效
- 重试：`conda run -n paper2anything --no-capture-output python main.py <pdf路径> --resume <task_id> --from-stage 2`

**Stage 5 生成文章质量不满意：**
- 可以直接编辑 `<论文目录>/.paper2anything/wechat/<task_id>/wechat/wechat_article.md` 后继续
- 或重新从 Stage 5 开始：`conda run -n paper2anything --no-capture-output python main.py <pdf路径> --resume <task_id> --from-stage 5`

**md2wechat 命令找不到：**
- 检查 `.env` 中 `MD2WECHAT_CMD` 是否正确配置
- 或者确认 `md2wechat` 已加入 PATH

**封面生成失败（非致命）：**
- 使用 `--skip-cover` 跳过，封面可手动选择论文图
