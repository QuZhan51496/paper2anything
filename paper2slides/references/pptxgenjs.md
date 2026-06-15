# PptxGenJS Tutorial

> paper2slides 精简副本：只保留 `render_pptx.py` 实际产出的元素（text / shape /
> line / image / icon）相关内容与踩坑点。官方完整 API（Tables / Charts / Slide
> Masters / Backgrounds 等）本 skill 不用，已删除——需要时查 PptxGenJS 官方文档。

---

## Text & Formatting

```javascript
// Basic text
slide.addText("Simple Text", {
  x: 1, y: 1, w: 8, h: 2, fontSize: 24, fontFace: "Arial",
  color: "363636", bold: true, align: "center", valign: "middle"
});

// Character spacing (use charSpacing, not letterSpacing which is silently ignored)
slide.addText("SPACED TEXT", { x: 1, y: 1, w: 8, h: 1, charSpacing: 6 });

// Rich text arrays
slide.addText([
  { text: "Bold ", options: { bold: true } },
  { text: "Italic ", options: { italic: true } }
], { x: 1, y: 3, w: 8, h: 1 });

// Multi-line text (requires breakLine: true)
slide.addText([
  { text: "Line 1", options: { breakLine: true } },
  { text: "Line 2", options: { breakLine: true } },
  { text: "Line 3" }  // Last item doesn't need breakLine
], { x: 0.5, y: 0.5, w: 8, h: 2 });

// Text box margin (internal padding)
slide.addText("Title", {
  x: 0.5, y: 0.3, w: 9, h: 0.6,
  margin: 0  // Use 0 when aligning text with other elements like shapes or icons
});
```

**Tip:** Text boxes have internal margin by default. Set `margin: 0` when you need text to align precisely with shapes, lines, or icons at the same x-position.

---

## Lists & Bullets

```javascript
// ✅ CORRECT: Multiple bullets
slide.addText([
  { text: "First item", options: { bullet: true, breakLine: true } },
  { text: "Second item", options: { bullet: true, breakLine: true } },
  { text: "Third item", options: { bullet: true } }
], { x: 0.5, y: 0.5, w: 8, h: 3 });

// ❌ WRONG: Never use unicode bullets
slide.addText("• First item", { ... });  // Creates double bullets

// Sub-items and numbered lists
{ text: "Sub-item", options: { bullet: true, indentLevel: 1 } }
{ text: "First", options: { bullet: { type: "number" }, breakLine: true } }
```

---

## Shapes

```javascript
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.5, y: 0.8, w: 1.5, h: 3.0,
  fill: { color: "FF0000" }, line: { color: "000000", width: 2 }
});

slide.addShape(pres.shapes.OVAL, { x: 4, y: 1, w: 2, h: 2, fill: { color: "0000FF" } });

slide.addShape(pres.shapes.LINE, {
  x: 1, y: 3, w: 5, h: 0, line: { color: "FF0000", width: 3, dashType: "dash" }
});

// With transparency
slide.addShape(pres.shapes.RECTANGLE, {
  x: 1, y: 1, w: 3, h: 2,
  fill: { color: "0088CC", transparency: 50 }
});

// Rounded rectangle (rectRadius only works with ROUNDED_RECTANGLE, not RECTANGLE)
// ⚠️ Don't pair with rectangular accent overlays — they won't cover rounded corners. Use RECTANGLE instead.
slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 1, y: 1, w: 3, h: 2,
  fill: { color: "FFFFFF" }, rectRadius: 0.1
});
```

---

## Icons

Use react-icons to generate SVG icons, then rasterize to PNG for universal compatibility.

> **⚠️ Color format (paper2slides spec):** the `icon` element's `color` is a **CSS
> color handed to react-icons** — it **must include the leading `#`** (`"#1E2761"`),
> the opposite of shape/text/line color fields. `"1E2761"` (no `#`) is invalid CSS and
> silently rasterizes **black** (invisible on dark backgrounds, no error). See
> Common Pitfalls #1.

### Setup

```javascript
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const { FaCheckCircle, FaChartLine } = require("react-icons/fa");

function renderIconSvg(IconComponent, color = "#000000", size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
}

async function iconToBase64Png(IconComponent, color, size = 256) {
  const svg = renderIconSvg(IconComponent, color, size);
  const pngBuffer = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + pngBuffer.toString("base64");
}
```

### Add Icon to Slide

```javascript
const iconData = await iconToBase64Png(FaCheckCircle, "#4472C4", 256);

slide.addImage({
  data: iconData,
  x: 1, y: 1, w: 0.5, h: 0.5  // Size in inches
});
```

**Note**: Use size 256 or higher for crisp icons. The size parameter controls the rasterization resolution, not the display size on the slide (which is set by `w` and `h` in inches).

### Icon Libraries

Install: `npm install -g react-icons react react-dom sharp`

Popular icon sets in react-icons:
- `react-icons/fa` - Font Awesome
- `react-icons/md` - Material Design
- `react-icons/hi` - Heroicons
- `react-icons/bi` - Bootstrap Icons

### Naming & academic picks (paper2slides)

**命名规律**：导出名 = 库前缀（`Fa`/`Md`/`Hi`/`Bi`）+ PascalCase 英文语义词。
不确定名字时按语义猜一个常见词即可——名错不会让渲染崩，`render_pptx.py`
会 warn+skip 该 icon（Stage 6 视觉 QA 会发现"图标缺失"再改名重渲）。

学术 deck 高频可用名（均为 `lib:"fa"`，已验证存在）：

| 语义角色 | icon 名 |
|---|---|
| 结果 / 趋势上升 | `FaChartLine` |
| 柱状对比 / benchmark | `FaChartBar` |
| 数据集 | `FaDatabase` |
| 方法 / 实验 | `FaFlask` |
| 模型 / AI | `FaBrain` |
| 系统 / pipeline | `FaCogs` |
| 贡献 / takeaway | `FaCheckCircle` |
| motivation / idea | `FaLightbulb` |
| baseline 对比 / ablation | `FaBalanceScale` |
| 架构图 / 流程 | `FaProjectDiagram` |
| 性能 / 加速 | `FaBolt` |
| SOTA / 突破 | `FaRocket` |

---

## Common Pitfalls

⚠️ These issues cause file corruption, visual bugs, or broken output. Avoid them.
（编号保持官方原编号，调用方按 "#N" 引用——故 #2/#4/#5/#6/#7 是本 skill 用不到
已删，留 #1 / #3 / #8 间隙是有意为之。）

1. **NEVER use "#" with hex colors in PptxGenJS color fields** - causes file corruption
   ```javascript
   color: "FF0000"      // ✅ CORRECT  (shape/text/line: fill, color, line_color)
   color: "#FF0000"     // ❌ WRONG — corrupts the .pptx
   ```
   **⚠️ Exception — `icon` elements are the opposite.** An icon's `color` is NOT a
   PptxGenJS field: it is passed straight to **react-icons as a CSS color**, so it
   **MUST keep the leading `#`** (`"#1E2761"`). Writing `"1E2761"` is invalid CSS →
   the SVG **silently rasterizes to black** (black-on-dark = invisible icon, no error
   raised). In paper2slides specs `render_pptx.py`'s `clean()` strips `#` for
   shape/text/line (so either form works there) but does **not** touch `icon.color`.
   **Rule of thumb: shape / text / line → no `#`; `icon` → keep `#`.**

3. **Use `bullet: true`** - NEVER unicode symbols like "•" (creates double bullets)

8. **Don't use `ROUNDED_RECTANGLE` with accent borders** - rectangular overlay bars won't cover rounded corners. Use `RECTANGLE` instead.
   ```javascript
   // ❌ WRONG: Accent bar doesn't cover rounded corners
   slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 1, y: 1, w: 3, h: 1.5, fill: { color: "FFFFFF" } });
   slide.addShape(pres.shapes.RECTANGLE, { x: 1, y: 1, w: 0.08, h: 1.5, fill: { color: "0891B2" } });

   // ✅ CORRECT: Use RECTANGLE for clean alignment
   slide.addShape(pres.shapes.RECTANGLE, { x: 1, y: 1, w: 3, h: 1.5, fill: { color: "FFFFFF" } });
   slide.addShape(pres.shapes.RECTANGLE, { x: 1, y: 1, w: 0.08, h: 1.5, fill: { color: "0891B2" } });
   ```
