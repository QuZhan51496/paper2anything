---
name: paper2xhs
description: 将学术论文 PDF 转换为小红书帖子草稿的完整流水线工具。当用户提到"论文转小红书"、"paper2xhs"、"把论文发到小红书"、"论文转社交媒体"、"PDF 转帖子"、"帮我把这篇论文发小红书"、"帮我把这篇论文转成小红书"时触发。包含 7 个阶段：PDF 上传验证、MinerU 解析、Claude 论文理解、内容结构化、小红书生成、封面生成（可选）、半自动发布。
allowed-tools: Bash, Read, Write, Glob, Grep
---

# paper2xhs — 论文转小红书流水线

## 工具简介

paper2xhs 是一个将学术论文 PDF 转换为小红书帖子草稿的 7 阶段确定性流水线工具。

设计理念：
- 稳定性优先于自主性
- 结构化输出优先于自由生成
- 流水线优先于多智能体编排
- 人工介入优先于全自动化

## 你的职责

当用户触发此 skill 时，你需要：

1. 引导用户完成环境准备
2. 确认 PDF 文件路径
3. 执行流水线命令
4. 在每个关键阶段展示预览并等待用户确认
5. 处理错误和异常情况

---

## 第一步：定位脚本目录

所有 stage 脚本位于 `scripts/`，且使用扁平模块导入（`import stage1_upload` 等），**必须 `cd` 到该目录运行**：

```bash
cd <paper2anything 包根>/paper2xhs/scripts
ls main.py 2>/dev/null && echo "脚本目录正确" || echo "未找到 main.py"
```

---

## 第二步：环境检查

> **统一环境**：本 skill 所有 `python` 命令都运行在 paper2anything 包的统一 conda 环境里（由顶层 `environment.yml` 创建），命令均以 `conda run -n paper2anything --no-capture-output` 为前缀；下面的 `pip install` 仅在统一环境缺依赖时兜底。

依次检查以下内容，如有问题立即告知用户并给出修复命令：

**检查 Python 依赖：**
```bash
conda run -n paper2anything --no-capture-output python -c "import anthropic, click, rich, dotenv" 2>&1
```

如果缺少依赖（依赖统一在顶层 `environment.yml`，各 skill 不再保留 requirements.txt）：
```bash
pip install anthropic openai playwright requests Pillow rich click python-dotenv
```

**检查 MinerU API token：**

Stage 2 通过 MinerU 云端 API（`https://mineru.net/api/v4`）解析 PDF，**不需要本地安装 `magic-pdf`**；MinerU token 与其它凭据统一放在 paper2anything 包根的 `.env`（变量名 `MINERU_API_TOKEN`）。

**统一凭据**：所有 key 集中在 paper2anything 包根的 `.env`（从 `.env.example` 复制填写，应 gitignore）。运行前在当前 shell 导出一次：

```bash
set -a; source <paper2anything 包根>/.env; set +a
```

本 skill 用到：
- `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL`（必填，stages 3/4/5）
- `MINERU_API_TOKEN`（Stage 2 解析，必填）
- `OPENAI_API_KEY` + `OPENAI_BASE_URL`（仅封面生成，可用 `--skip-cover` 跳过）

如果用的是第三方代理（如 openai-hk），把对应 BASE_URL 改成代理地址即可，无需改代码——Anthropic / OpenAI SDK 都会自动读 `*_BASE_URL` 环境变量。

> main.py 的 `load_dotenv()` 也会自动向上找到包根 `.env`，所以即使忘了 source，xhs 自身仍能读到；但建议统一执行上面那行，其它 skill 依赖它。

检查 token 是否就绪：
```bash
grep -q '^MINERU_API_TOKEN=..' <paper2anything 包根>/.env && echo "已配置" || echo "缺 token"
```

**检查 Playwright（发布功能需要）：**
```bash
conda run -n paper2anything --no-capture-output python -c "import playwright" 2>&1
```

如果未安装：
```bash
pip install playwright && playwright install chromium
```

---

## 第三步：确认 PDF 路径

如果用户已经提供了 PDF 路径，直接使用。

如果没有提供，询问用户：
> 请提供论文 PDF 的本地路径（例如：`/path/to/paper.pdf` 或 `./paper.pdf`）

确认文件存在：
```bash
test -f "<用户提供的路径>" && echo "文件存在" || echo "文件不存在"
```

---

## 第四步：执行流水线

根据用户需求选择合适的命令：

**标准运行（含人工确认，推荐）：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径>
```

**跳过封面生成：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --skip-cover
```

**跳过发布：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --skip-publish
```

**全自动运行（不需要人工确认）：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --no-confirm
```

**从指定阶段继续（恢复中断的任务）：**
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --resume <task_id> --from-stage <阶段编号>
```

---

## 流水线阶段说明

| 阶段 | 名称 | 关键输出文件 |
|------|------|-------------|
| 1 | PDF 上传验证 | `<论文目录>/.paper2anything/xhs/{task_id}/raw/paper.pdf` |
| 2 | MinerU 解析 | `parsed/paper_meta.json`、`sections.json`、`figures_index.json` |
| 3 | 论文理解 | `understanding/paper_understanding.json` |
| 4 | 内容结构化 | `assets/content_assets.json` |
| 5 | 小红书生成 | `xhs/xhs_post.json` |
| 6 | 封面生成（可选） | `xhs/cover.png` |
<!-- | 7 | 半自动发布 | Playwright 自动填写，用户手动点发布 | -->

每个阶段都会：
- 验证输出是否合法
- 将结果持久化到磁盘
- 在验证失败时停止流水线

---

## 阶段间人工确认

流水线默认在每个阶段完成后暂停，展示预览并询问是否继续。

你需要在每次暂停时：
1. 向用户展示当前阶段的输出摘要
2. 询问用户是否满意，是否继续
3. 如果用户想修改，告知他们可以直接编辑对应的 JSON 文件后再继续

---

## 查看生成结果

流水线完成后，帮助用户查看生成的帖子：

```bash
cat <论文目录>/.paper2anything/xhs/<task_id>/xhs/xhs_post.json
cat <论文目录>/.paper2anything/xhs/<task_id>/xhs/xhs_post.md
```

输出格式：
```json
{
  "title": "帖子标题（≤20字）",
  "body": "帖子正文（含 emoji 和标签）",
  "hashtags": ["#标签1", "#标签2"],
  "cover_text": "封面文字",
  "paper_title_zh": "论文中文标题"
}
```

---

## 恢复中断的任务

如果流水线中途中断，可以从任意阶段恢复：

1. 找到任务 ID（论文旁 `<论文目录>/.paper2anything/xhs/` 目录下的子目录名）：
```bash
ls <论文目录>/.paper2anything/xhs/
```

2. 从指定阶段继续：
```bash
conda run -n paper2anything --no-capture-output python main.py <pdf路径> --resume <task_id> --from-stage <阶段编号>
```

---

## 常见问题处理

**MinerU 解析失败：**
- 检查 `.env` 中的 `MINERU_API_TOKEN` 是否有效（在 https://mineru.net 申请）
- 检查 PDF 文件是否 ≤200MB、≤200 页
- 检查网络能否访问 `mineru.net` 及上传 OSS 域名
- 重试：`conda run -n paper2anything --no-capture-output python main.py <pdf路径> --resume <task_id> --from-stage 2`

**Claude API 调用失败：**
- 检查 `.env` 中的 `ANTHROPIC_API_KEY` 是否正确
- 检查网络连接

**封面生成失败（非致命）：**
- 检查 `.env` 中的 `OPENAI_API_KEY` 是否设置
- 封面生成失败不会阻止后续流程，可以跳过：`--skip-cover`

<!-- **小红书发布页需要登录：**
- Stage 7 会打开浏览器，首次使用需要手动登录
- 登录状态保存在 `~/.paper2xhs/browser_data/`，后续无需重复登录 -->

<!-- **Playwright 找不到元素：**
- 小红书页面结构可能已更新
- 此时正文内容会自动复制到剪贴板（macOS），请手动粘贴 -->
