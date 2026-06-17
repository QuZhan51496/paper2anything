# index.html 撰写规范（硬约束 + 易错点）

## manifest 是唯一的事实来源

只用 `manifest.json` 里**已核实的素材**（title/authors/abstract/links/claims/figures/tables/
method_components/bibtex）。**不要编造**数字、作者、机构或论文里没有的链接。manifest 里抽空的
字段（如 authors=[]、abstract=""、links.paper=""）是确定性抽取的局限——**由你据 `clean.md`
全文补全**（这正是"Claude 兜底"：你才是主笔，抽取器只是脚手架）。附录/补充材料的图表已在闸门1
过滤，不会进 manifest。

## 自包含、可部署

- 产物是 `<workdir>/index.html` + 同级 `<workdir>/images/`，可直接丢 GitHub Pages。
- 图片用**相对路径** `images/<filename>`（文件名取自 `manifest.figures[].file` / `tables[].image`，
  stage1 已把它们复制进 `images/`）。**不要**写绝对路径或 `../` 跨目录引用。
- 每张 `<img>` 都要有**非空 `alt`**（用图注）。不要留 `href="#"` 空锚点。
- CSS/JS 尽量内联或用 CDN（如 MathJax），保证单文件打开即用。

## 项目主页版式建议

- 首屏 editorial 轻盈：标题、作者、机构、资源按钮（paper/code/project，取自 manifest.links；空的就不放）。
- 主图（架构/pipeline）作为一次性 teaser 大图展示，别当重复背景。
- 顺序参考：teaser → abstract → claims → method → results → 支撑图 → BibTeX（按论文气质调整，非强制）。
- 结果表**优先用论文裁出的表格截图**（`tables[].image`），因为抽取的 HTML 表常丢公式与对齐。
- 卡片只用在重复性内容（claims、story、表格、图集项）上，别滥用。
- 按角色定图大小：架构图给大可读舞台、方法图次要、图集封顶。

## figure CSS 易错点（边框贴图、绝不失真）

- **边框要贴住图片本身**，别框住空白：不要在固定宽度盒子上同时用 `width:100%` + `object-fit:contain`
  （图会缩在大框里、四周留白）。两种安全写法择一：
  - 填满栏宽：`display:block; width:100%; height:auto;` + border（边框贴图，图自带文字最大化）。
  - 限高居中：`display:inline-block; max-height:X; width:auto; height:auto;` + border，外层 `text-align:center`。
- **绝不为填空白强行设固定 `height`（或同时固定 `width`+`height`）**——会把图拉变形。最多设一个轴
  （`width:100%;height:auto` 或 `max-height:X;width:auto`），另一轴自适应。空白用**内容**填（多一条
  takeaway / 多一个 bullet）或重排栏宽，别靠拉伸图片。
- 渲染后自检：每个 `<img>` 的 `renderedW/renderedH` 应等于 `naturalW/naturalH`（±2%），否则就是失真。

## 表格策略

- `manifest.tables[]` 多为**图片表**（`image` 有值、`html` 为空）——直接 `<img src="images/...">` 展示。
- 若某表有 `html`（管道表重建），可在页面内渲成与全站同风格的原生 HTML 表；否则用截图。
