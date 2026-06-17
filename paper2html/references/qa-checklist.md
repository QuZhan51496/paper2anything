# QA 检查项与修复（stage2_validate 产出 → 你据此修 index.html）

`stage2_validate.py` 校验你写的 `index.html`，产出 `validation.json` + `qa_report.md`。
**error 必须清零**才算过；**warning 看情况修**（多数该修，少数可接受）。

## error（结构性，必修）

| 报告 | 原因 | 修法 |
|---|---|---|
| `HTML does not start with <!DOCTYPE html>` | 缺文档类型声明 | 文件首行写 `<!DOCTYPE html>` |
| `HTML is missing </html>` | 结构不完整 | 补 `</html>` 闭合 |
| `Missing image files: images/x` | 引用了不存在的图 | 核对文件名（取自 `manifest.figures[].file`/`tables[].image`）；只引用 stage1 复制进 `images/` 的图；别拼错哈希名 |
| `Found N empty href="#" links` | 空锚点 | 给真实链接或去掉该 `<a>` |

## warning（按需修）

| 报告 | 含义 | 处理 |
|---|---|---|
| `Paper title not found in the page` | 标题前 40 字没出现在页面 | 确保 hero 用 manifest 的真实标题原文 |
| `None of the extracted figures are referenced` | 一张抽出的图都没用 | 至少展示主图（架构/pipeline） |
| `None of the extracted result tables are referenced` | 结果表全没用 | 把结果表截图放进 results 区 |
| `Repeated image references` | 同一图被引多次 | 一般去重；除非刻意（teaser+gallery） |
| `Fewer than three impact claims were extracted` | manifest.claims<3 | 抽取局限，不必强凑；可据 abstract/results 在文案里自然写关键数字 |
| `No paper link was detected` | links.paper 空（不假设 arxiv） | 知道规范链接就重跑 stage1 加 `--paper-url`；否则接受留空 |
| `non-decorative images with empty alt` | 有图 `alt=""` | 补图注作 alt；纯装饰图加 `aria-hidden="true"` |

## 循环

修完 `index.html` → 重跑 `stage2_validate.py --workdir <...>` → 直到 error 清零、warning 可接受。
QA 不改你的 HTML，只报告——主笔始终是你。
