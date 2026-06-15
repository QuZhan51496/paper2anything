---
name: paper2html
description: 将学术论文（PDF 或 MinerU 解析后的 Markdown）转换为可直接发布的、自包含的单页**项目主页**（self-contained index.html）——就是研究者常基于 GitHub Pages 做的那种论文宣传网页。当用户提到"把论文做成项目主页/网页"、"paper2html"、"生成论文 landing page / project page"、"把这篇 PDF 变成 HTML 网页"、"论文转网页"、"做一个论文主页"时触发。manifest 驱动、双闸门（确定性事实抽取 + 生成后 QA 自修复），支持 template / llm 两种渲染路径与 6 种设计语言 variant。
allowed-tools: Bash, Read, Write, Glob, Grep
---

# paper2html — 论文转单页项目主页

把一篇学术论文（PDF 或 MinerU 解析后的 Markdown）转换成一个**自包含、可直接发布的单页项目网站**——研究者常基于 GitHub Pages 做的那种论文主页。

本版本是 **v7** 线：以 manifest 为核心、由 **Claude Opus 4.8**（或所配 LLM）驱动的生成器，夹在两道闸门之间（确定性事实抽取 + 生成后 QA 校验），重点优化**跨论文泛化性**与**版式多样性**。

## 你的职责

当用户触发此 skill 时，你需要：

1. 引导用户完成环境准备（统一 conda 环境 + LLM/MinerU 凭据）
2. 确认输入（PDF 或已解析的 Markdown）与输出目录
3. 选择渲染路径（`template` 确定性模板 / `llm` 设计整页）与可选的设计语言 `--variant`
4. 执行生成命令，必要时用交互模式（`--interactive`）逐步走查
5. 查看 QA 报告，处理缺图/坏链等问题

---

## 双闸门架构 / 为什么这样设计

流水线把**可靠性**与**创造力**解耦：

```
PDF/MD ──▶ MinerU parse ──▶ extract_manifest ──▶ [renderer] ──▶ validate_site (QA) ──▶ index.html
                            (确定性事实)                          (安全闸门)
```

- **闸门 1 — `extract_manifest`**：从解析后的 Markdown 确定性地抽取 title / authors / abstract / links / claims / figures / tables / method components。LLM **只能**使用这些真实素材，因此无法瞎编数字、也无法引用不存在的图。附录 / 补充材料内容会被自动过滤掉。
- **闸门 2 — `validate_site`**：生成后检查 HTML 的缺图、坏链/空链、结构异常等。出错时把错误回灌 LLM 自修复（最多 2 次重试）。

两条渲染路径共享这两道闸门：

| Renderer | 说明 |
| --- | --- |
| `--renderer template` | 确定性 Python 模板。完全可复现、永不崩，但风格单一。 |
| `--renderer llm` | LLM 据已核实的 manifest 设计整页。丰富、贴合论文、版式多样。 |

---

## 第一步：定位 skill 目录与环境准备

paper2html 的代码是一个名为 `paper2html` 的 Python 包，位于本 skill 目录下的 `paper2html/` 子目录。运行 `python -m paper2html.agent` **必须 `cd` 到本 skill 目录**（即包目录 `paper2html/` 的上一级），把 `<paper2anything 包根>` 换成本仓库实际所在目录：

```bash
cd <paper2anything 包根>/paper2html
ls paper2html/agent.py 2>/dev/null && echo "目录正确" || echo "未找到 paper2html/agent.py"
```

> **统一环境**：本 skill 所有 `python` 命令都运行在 paper2anything 包的统一 conda 环境里（由顶层 `environment.yml` 创建），命令均以 `conda run -n paper2anything --no-capture-output` 为前缀；下面的 `pip install` 仅在统一环境缺依赖时兜底。

```bash
pip install requests openai Pillow
```

**统一凭据**：所有 key 集中在 paper2anything 包根的 `.env`（从 `.env.example` 复制填写，应 gitignore）。运行前在当前 shell 导出一次：

```bash
set -a; source <paper2anything 包根>/.env; set +a
```

本 skill 用到 `OPENAI_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（LLM 渲染）与 `MINERU_API_TOKEN`（PDF 解析）。LLM 渲染器自动识别 OpenAI 兼容与 Anthropic 原生两种网关；缺配置时自动回退 `template`。

---

## 第二步：执行生成

```bash
# 2a) 从已解析的 Markdown 生成（最快，不消耗 MinerU 额度）
#     <解析目录> 通常是上一次 PDF 运行的输出目录：<pdf目录>/.paper2anything/html/<paper>_agent
conda run -n paper2anything --no-capture-output python -m paper2html.agent <解析目录>/clean.md \
  --images <解析目录>/images \
  --renderer llm

# 2b) 或直接从 PDF 生成（会先跑 MinerU 解析）
conda run -n paper2anything --no-capture-output python -m paper2html.agent paper.pdf --renderer llm

# 默认输出落在输入文件旁：<输入文件目录>/.paper2anything/html/<输入名>_agent/
# 要自定义输出目录，加 -o <目录>
```

**交互式流程**按 Inspect → Ask → Sketch → Revise → Confirm → Build → QA 推进；确认后的意图存为 `project_brief.json`，可用 `--brief` 复用：

```bash
conda run -n paper2anything --no-capture-output python -m paper2html.agent --interactive
```

`briefs/` 内附深色 / 蓝色用户指南风格的现成 brief。

---

## CLI 命令行参数

| 参数 | 说明 |
| --- | --- |
| `input` | 输入 PDF 或 Markdown 文件 |
| `-o, --output DIR` | 输出目录 |
| `--images DIR` | 解析后的图片目录（Markdown 输入时） |
| `--renderer template\|llm` | 渲染方式，默认 `template`（`llm` = LLM 整页生成 + QA 自修复） |
| `--variant N` | 仅 LLM：切换设计语言（1–6）。不传则使用稳定可复现的布局 |
| `--mode showcase\|reader` | 页面模式，默认 `showcase` |
| `--table-mode auto\|image\|html` | 表格呈现策略，默认 `auto` |
| `--brief path.json` | 复用确认过的 `project_brief.json` |
| `--rotate "3:90,5:90"` | 顺时针旋转校正侧向图片（角度 90/180/270；编号取自交互模式的 `figures` 列表） |
| `--paper-url / --code-url` | 覆盖检测到的论文/代码链接 |
| `-i, --interactive` | 交互式终端流程 |
| `--lite` | 使用 MinerU 轻量解析 API |
| `--no-reuse-parsed` | 不复用已有的 `parsed/full.md` |
| `--no-copy-images` | 不把图片复制进输出目录 |

### 设计语言 variant（仅 `--renderer llm`）

LLM 渲染器被要求**先为这篇论文确立设计概念**（视觉范式 + 叙事主线）再布局，而不是套固定区块清单。用 `--variant N` 切换整体设计语言：

| Variant | Design language |
| --- | --- |
| `--variant 1` | Editorial / magazine 杂志风 |
| `--variant 2` | Product landing page 产品落地页 |
| `--variant 3` | Terminal / technical 终端极客风 |
| `--variant 4` | Academic poster 学术海报 |
| `--variant 5` | Minimal archive 极简档案 |
| `--variant 6` | Data dashboard 数据看板 |

不传 `--variant` 则使用模型为该论文挑选的稳定可复现布局。`examples/` 收录了同一篇论文（SKILL0）用 `--variant 1/2/3` 生成的三个页面，浏览器打开任一 `index.html` 即可查看其设计语言差异。

---

## 主要特性（v7）

1. **跨论文泛化**：无任何针对特定论文的硬编码（早期版本曾内置 Attention 论文的 claims/文案，v7 已全部移除）。在三篇不同领域论文（NLP / agentic-RL / GUI-agent）上验证，零跨论文串味。
2. **版式多样性**：LLM 先立设计概念再布局，`--variant N` 切换整体设计语言。
3. **附录过滤**：出现在 `Appendix` / `Supplementary` / `附录` 标题（或靠后的字母编号小节）之后的图、表、claims、方法组件不会进入页面。
4. **图片表格按宽高比自适应**：每张图/表截图都带真实像素 `width`/`height`/`aspect`/`orientation`，渲染器据此合理控制尺寸（超宽→全宽或横向滚动、竖图→限宽、方图→网格），并统一进同一套 `<figure>` 边框体系；结果表优先重建为页面同风格的原生 HTML 表而非截图。
5. **图片旋转校正**：部分解析出的图是侧向的。可在交互模式用 `figures` 列出、`rotate <编号> <角度>` 校正，或用 `--rotate "3:90,5:90"`（顺时针，90/180/270）。只改输出副本，不动源缓存。需安装 Pillow。
6. **交互与 brief 驱动**：交互模式按 Inspect → Ask → Sketch → Revise → Confirm → Build → QA 推进；确认后的意图存为 `project_brief.json`，可用 `--brief` 复用。

---

## 输出结构

```
<输入文件目录>/.paper2anything/html/<paper>_agent/
├── index.html          # 可直接打开/部署的页面
├── clean.md            # 清洗后的 Markdown
├── manifest.json       # 抽取的事实
├── site_plan.json      # theme / accent / primary figure
├── style_reference.json# 样式规则 + 实际使用的 renderer
├── project_brief.json  # （仅交互/brief 运行时）
├── validation.json     # 机器可读的 QA 结果
├── qa_report.md        # 人类可读的 QA 报告
└── images/             # 页面实际引用的图片
```

---

## 环境变量

| Variable | 说明 | Default |
| --- | --- | --- |
| `MINERU_API_TOKEN` | MinerU API token | — |
| `OPENAI_API_KEY` | LLM API key | — |
| `LLM_MODEL` | 模型名 | `azure_openai/gpt-5.4` |
| `LLM_BASE_URL` | OpenAI- 或 Anthropic-兼容的 base URL | `http://model.mify.ai.srv/v1` |
| `LLM_REQUEST_TIMEOUT` | 请求超时（秒） | `900` |

> **安全**：凭据统一在 paper2anything 包根的 `.env`（含真实密钥、应 gitignore，切勿提交）。用 `.env.example` 作模板，切勿提交真实 key。

---

## 旧版直通流程 / Legacy pipeline

原始的一次性 `PDF → MinerU → Markdown → LLM HTML` 路径仍然可用：

```bash
conda run -n paper2anything --no-capture-output python -m paper2html.pipeline paper.pdf -o ./out
```
