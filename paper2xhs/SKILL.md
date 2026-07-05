---
name: paper2xhs
description: 把学术论文 PDF 转成小红书多图帖（标题 + 正文 + 标签 + 封面 + 论文主图/主实验结果配图）。你主导设计的协调式：机械活（MinerU 解析 PDF、生成封面与配图、半自动发布）交给 scripts/ 下的小工具，论文理解、选题角度、文案撰写由你亲自完成并在关键点与用户确认。当用户说“论文转小红书”、“paper2xhs”、“把这篇论文发小红书”、“论文转社交媒体”、“PDF 转小红书帖子”时触发。
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion, SendUserFile
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
 → 封面+配图        (cover.py 封面：默认 API 生图 gpt-image-2、无 key 回退本地合成；
                    post_images.py 配图：把你选的论文主图/主实验图按序复制成图集，原图直出)
 → 半自动发布       (publish.py：封面+配图多图帖，可选)
 → 小红书帖子
```

## 运行方式

1. **一步步来**：机械步骤用 `Bash` 调脚本，创作步骤你自己用 `Read` / `Write` 做。不要试图一条命令跑完。
2. **每个 Bash 块开头就地算 `WORKDIR`**——各 Bash 调用是独立 shell、不共享变量，所以别指望 `export` 跨步存活：
   ```bash
   WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs/$(basename "${pdf_path%.*}")"
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
- `OPENAI_API_KEY`(+ `OPENAI_BASE_URL`) — 封面默认走它生图（gpt-image-2）；无 key 或 key 不可用时回退本地合成（复用论文原图）
- `XHS_MCP_BIN` — 可选：自定义 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 二进制位置；**不设则发布时 skill 自动按平台下载**到 `~/.paper2anything/xhs/`。另可选 `XHS_MCP_URL`（自定义服务地址/端口，默认 `http://localhost:18060`）。

依赖自检（缺啥按提示装；依赖统一在 `environment.yml`）：

```bash
conda run -n paper2anything --no-capture-output python -c "import requests, rich, dotenv" 2>&1
```

---

## Step 1：解析 PDF（脚本）

```bash
pdf_path="/path/to/paper.pdf"          # ← 用户的论文 PDF
WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs/$(basename "${pdf_path%.*}")"
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

1. `Read` `parsed/sections.json`（全文）+ `parsed/paper_meta.json`；`Read` `parsed/figures_index.json` 看图注（个别图 caption 可能为空；多面板大图可能被解析器拆成两半、完整图注只挂在其中一半上，且拆缝处图例/轴标签可能被裁——一律以实际看图为准），并**实际 `Read` 几张候选图片**（`figures/` 下）判断哪些清晰、适合做封面或配图——图注说“framework”的图在小图里未必好看，只有你的眼睛能判断。
2. 用 `Write` 落 `understanding/paper_understanding.json`，schema：
   ```json
   {
     "paper_title": "...", "method_name": "方法简称（如 AccKV）",
     "one_sentence_summary": "一句话讲清这篇做了什么",
     "problem": "解决什么问题", "method": "怎么做的",
     "highlights": ["有数据支撑的亮点1", "创新点2", "应用价值3"],
     "experiment_results": ["关键数据1（含数字）", "..."],
     "keywords": ["领域关键词", "..."],
     "cover_palette": {"bg": "#F4F5F7", "accent": "#2E86AB"},
     "important_figures": [
       {"figure_id": "fig_1", "image_path": "<figures_index.json 里的真实路径>",
        "suitable_for_cover": true, "importance_score": 0.9, "description": "图说明"}
     ],
     "post_figures": [
       {"image_path": "<figures_index.json 里的真实路径>"}
     ]
   }
   ```
   - `important_figures` 必须含 `image_path`（取自 `parsed/figures_index.json`，指向真实存在的图）、`suitable_for_cover`、`importance_score`——封面默认走 API 生图（gpt-image-2），仅当 `OPENAI_API_KEY` 未配/不可用时回退本地合成、靠这几个字段复用原图；漏了则回退时无图 → 封面 `skipped`。
   - `post_figures`（多图帖正文配图，建议 2~4 张、按展示顺序排）：**第一张放论文主图**（框架/方法总览），
     其后放**主实验结果图**；只放你亲眼 `Read` 过、缩到手机宽度仍清晰可读的图。配图**原图直出、
     不做任何加工**。发布时图集 = 封面 + 这些配图。
   - `cover_palette`（可选）：本地合成回退路径的配色，按论文领域选 `bg`(浅色打底) + `accent`(强调色)，标题字色会随底色深浅自动适配。参考浅色调：通用 `#F4F5F7`+`#2E86AB`、生物 `#EEF6F0`+`#2D8A5F`、物理数学 `#F1ECF8`+`#6A30C2`、工程 `#FBF0EC`+`#D85A3C`、社科 `#F4EEF2`+`#8A5A78`、化学 `#EAF4F8`+`#0E86C0`。
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

## Step 4：生成封面与配图（脚本，可选）

**封面主/副标题此刻由你现拟**（你已读透论文，比从 JSON 里捡更贴切），经 `--title`（主标题大字）/ `--subtitle`（副标题小字）传入：

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs/$(basename "${pdf_path%.*}")"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/cover.py" --workdir "$WORKDIR" \
  --title "你拟的封面主标题大字" --subtitle "你拟的副标题小字"
```

逻辑：**默认用 `OPENAI_IMAGE_MODEL`（默认 `gpt-image-2`）生成竖版封面**，主标题大字用你传入的 `--title`、副标题小字用 `--subtitle`（留空才分别回退 `xhs_post.cover_text` / 论文标题）；未配 `OPENAI_API_KEY` 或 key 不可用时回退本地合成——复用 `understanding.important_figures` 里 `suitable_for_cover` 最高分的论文原图（叠加 `--title`，配色取 `cover_palette`）；两者都不可用则 `skipped`（不阻断流程）。产出 `cover.png`。
**生图 API 单次可能要好几分钟（经中转可达 6~7 分钟）**——本命令的 Bash 超时设 ≥10 分钟（600000ms），别用默认 2 分钟，超时被杀时 `logs/` 不会留 cover_result.json。

**再生成正文配图**（多图帖的第 2~N 张，纯本地排版、不调 API）：

```bash
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/post_images.py" --workdir "$WORKDIR"
```

逻辑：读 `understanding.post_figures`，把选中的论文原图**按序直接复制**为
`post_images/p1.png|jpg…`（原图直出、不加工，后缀随原图）；
`understanding` 没写 `post_figures` 时回退 `important_figures` 按分前 3；
一张可用图都没有则 `skipped`（不阻断）。生成后**逐张 `Read` 亲眼确认**——图缩到手机宽度后糊、
文字不可读，就回去调 `post_figures`（换图/删图）重跑本命令（重跑会清掉旧 `p*`）。

---

## Step 5：发布到小红书（脚本 + 你协调，可选）

发布走开源的 **[xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)**（自带无头 Chromium 的单二进制 + REST API）。**登录一次后 cookies 持久、之后免登录**。二进制由 ① 自动备好（`XHS_MCP_BIN` 仅自定义位置时配，见 Step 0）。**首次配置/登录的分环境完整步骤见 `references/publish-guide.md`**——先 `Read` 它。不发布就跳过本步，把产物路径告诉用户手动发。

**① 确保 mcp 二进制就位并在固定持久目录运行**（二进制不存在会自动下载；cookies 落这里、跨论文复用）：
```bash
export XHS_MCP_DIR="$HOME/.paper2anything/xhs"; mkdir -p "$XHS_MCP_DIR"
# 解析二进制：优先 .env 的 XHS_MCP_BIN；否则用持久目录里的；都没有就按平台自动下载
if [ -n "$XHS_MCP_BIN" ] && [ -x "$XHS_MCP_BIN" ]; then BIN="$XHS_MCP_BIN"; else
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64)  ASSET=xiaohongshu-mcp-linux-amd64 ;;
    Darwin-arm64)  ASSET=xiaohongshu-mcp-darwin-arm64 ;;
    Darwin-x86_64) ASSET=xiaohongshu-mcp-darwin-amd64 ;;
    *) ASSET= ; echo "未知平台，请手动下载 xiaohongshu-mcp 并在 .env 设 XHS_MCP_BIN" ;;
  esac
  BIN="$XHS_MCP_DIR/$ASSET"
  if [ -n "$ASSET" ] && [ ! -x "$BIN" ]; then
    echo "未找到 mcp 二进制，自动下载 $ASSET …"
    curl -fL -o "$XHS_MCP_DIR/$ASSET.tar.gz" "https://github.com/xpzouying/xiaohongshu-mcp/releases/latest/download/$ASSET.tar.gz" \
      && tar xzf "$XHS_MCP_DIR/$ASSET.tar.gz" -C "$XHS_MCP_DIR" && chmod +x "$BIN"
  fi
fi
# 起服务（已在跑就跳过；BIN 不可用则报错、不硬起）
if ! curl -sf http://localhost:18060/api/v1/login/status >/dev/null 2>&1; then
  if [ ! -x "$BIN" ]; then
    echo "mcp 二进制不可用（$BIN）——下载失败或平台不支持，无法发布；手动下载并设 XHS_MCP_BIN，见 references/publish-guide.md"
  else
    ( cd "$XHS_MCP_DIR" && nohup "$BIN" -port=:18060 > mcp.log 2>&1 & )
    for i in $(seq 1 30); do curl -sf http://localhost:18060/api/v1/login/status >/dev/null 2>&1 && break; sleep 2; done
  fi
fi
```
（首次会下载 mcp 二进制 + 其 Chromium（约 150MB），可能要等；日志见 `$XHS_MCP_DIR/mcp.log`。macOS 若被 Gatekeeper 拦：`xattr -c "$BIN"`。）

**② 查登录态**：
```bash
conda run -n paper2anything --no-capture-output python "${SKILL_DIR}/scripts/publish.py" --check-only
```
`已登录` → 跳到 ④。`未登录` → 走 ③。

**③ 登录（仅首次或会话失效时）**：登录要换带界面/monitor 的方式起 mcp，**先停掉 ① 起的那个**（按进程名精确停，别用 `pkill -f`，会误杀自身）：
```bash
pkill -x xiaohongshu-mcp; sleep 1
```
再照 `references/publish-guide.md` 按环境操作。无头服务器要点：带 `-rod "monitor=:9273"` 重起 mcp（保持默认无头）→ `xhs_login.py` 取码 → `SendUserFile` 把 `qr.png` 发用户、提醒**首次可能要先在 monitor 端口(:9273)的浏览器界面里扫一道「新设备验证」码** → `AskUserQuestion` 等用户确认扫完 → 监测 cookies 写出 → 成功后**再 `pkill -x xiaohongshu-mcp` 停掉、回 ① 重启**（去掉 monitor、加载 cookies）。
```bash
conda run -n paper2anything --no-capture-output python "${SKILL_DIR}/scripts/xhs_login.py" \
  --out "$XHS_MCP_DIR/qr.png" --cookies "$XHS_MCP_DIR/cookies.json" --wait
```

**④ 发布前给用户过目**：`Read` `xhs_post.json` 把**标题 + 正文**发给用户看，`SendUserFile` 发 `cover.png` 与 `post_images/` 下全部配图；用 `AskUserQuestion` 让用户**确认发布并选可见性**（选项默认「公开可见」，另有「仅自己可见」「仅互关好友可见」）。

**⑤ 发布**（传入用户选的可见性）：
```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs/$(basename "${pdf_path%.*}")"
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/publish.py" --workdir "$WORKDIR" --visibility "公开可见"
```
图集自动取**封面 + `post_images/` 下配图**（按 p1、p2… 排序，含封面最多 18 张）。返回「发布成功」即完成。

---

## Step 6：把成品归集到 PDF 旁

成品默认埋在 `.paper2anything/xhs/<stem>/` 里不好找。文案+封面定稿后（无论是否走 Step 5 发布），把它们复制一份
到**与 PDF 同级**的 `<stem>_xhs/` 目录（`.paper2anything` 内副本保留不动），让用户在论文旁直接取用：

```bash
pdf_path="/path/to/paper.pdf"
WORKDIR="$(dirname "$pdf_path")/.paper2anything/xhs/$(basename "${pdf_path%.*}")"
DEST="${pdf_path%.*}_xhs"             # 与 PDF 同目录、同名 + _xhs 后缀
i=2; while [ -e "$DEST" ]; do DEST="${pdf_path%.*}_xhs_v$i"; i=$((i+1)); done   # 重名则追加 _v2、_v3
mkdir -p "$DEST"
cp "$WORKDIR/xhs_post.md" "$WORKDIR/xhs_post.json" "$DEST/"
[ -f "$WORKDIR/cover.png" ] && cp "$WORKDIR/cover.png" "$DEST/"   # 封面可能 skipped，存在才复制
[ -d "$WORKDIR/post_images" ] && cp -r "$WORKDIR/post_images" "$DEST/"   # 配图同理，存在才复制
```

`xhs_post.md` 以 `![封面](cover.png)` 相对引用封面，故文案、封面与配图整组放进 `<stem>_xhs/` 子目录、引用不破。

---

## 产物位置

中间产物落在论文旁 `<pdf目录>/.paper2anything/xhs/<stem>/`（同目录多篇论文按 `<stem>` 分篇、互不覆盖），**最终成品另复制到 PDF 同级的 `<stem>_xhs/`**（Step 6）：

| 路径 | 内容 | 谁写 |
|---|---|---|
| `.paper2anything/xhs/<stem>/parsed/` | MinerU PIR（meta/sections/figures_index/references） | parse_pdf |
| `.paper2anything/xhs/<stem>/figures/` | 论文插图实体 | parse_pdf |
| `.paper2anything/xhs/<stem>/understanding/paper_understanding.json` | 论文理解 + important_figures | **你** |
| `.paper2anything/xhs/<stem>/xhs_post.json` `xhs_post.md` | 小红书文案 | **你** |
| `.paper2anything/xhs/<stem>/cover.png` | 封面 | cover |
| `.paper2anything/xhs/<stem>/post_images/` | 正文配图（论文原图直出 p1.png|jpg…） | post_images |
| `.paper2anything/xhs/<stem>/logs/` | 各脚本 `*_result.json` | 脚本 |
| **`<pdf目录>/<stem>_xhs/`** | **成品归集**：`xhs_post.md` + `.json` + `cover.png` + `post_images/`，与 PDF 同级 | **你（Step 6）** |

重跑覆盖工作区 `.paper2anything/xhs/<stem>/`（中间产物）；归集步骤遇同名 `<stem>_xhs/` 会另存为 `_v2`、`_v3`，不覆盖旧成品。

---

## 排错

- **MinerU 解析失败**：核对 `.env` 的 `MINERU_API_TOKEN`（在 https://mineru.net 申请）；PDF 应 ≤200MB / ≤200 页；能访问 `mineru.net`。重跑 Step 1 即可（覆盖）。
- **封面没生成（`skipped`）**：通常是既没配可用 `OPENAI_API_KEY`、又没有可复用的论文原图。配上 key 走 AI 生图，或确保 `understanding.important_figures` 有 `suitable_for_cover:true` 且 `image_path` 存在的图以供本地合成回退。
- **配图没生成 / 张数不对**：`post_figures[].image_path` 必须取自 `parsed/figures_index.json` 且文件真实存在（路径错会逐张跳过）；`understanding` 没写 `post_figures` 时回退 `important_figures` 按分前 3；全无可用图则 `skipped`。发布只认 `post_images/` 下的 `p<序号>.*` 文件。
- **发布步骤报错**：`未登录` → 按 `references/publish-guide.md` 完成登录（首次注意「新设备验证」）；`连不上 mcp` → 看 ① 是否成功起服务（二进制下载/启动失败查 `$XHS_MCP_DIR/mcp.log`）。**登录成功后须重启 mcp 才会加载 cookies**。不发布可跳过 Step 5、手动发产物。publish.py 非零退出（2=未登录、3=连不上）时 `conda run` 会附带打印一行 `ERROR conda.cli.main_run`——那只是退出码传播，不是脚本崩溃。
- **理解/文案不需要 API key**：这两步是你亲自做的，不调用任何 LLM API。
