"""
render_pptx.py — Stage 5: slide_spec.json → output.pptx 桥

把结构化的 spec 翻译成 PptxGenJS 程序（`build.js`），用 node 跑出 .pptx。
为什么不直接用 python-pptx？官方 pptx skill 的"从零生成"路径就是 PptxGenJS，
所有视觉设计踩坑文档都基于它；本 skill 走 PptxGenJS 等于直接复用那些经验。

依赖：
  - node 在 PATH
  - pptxgenjs 在 NODE_PATH 或全局：`npm install -g pptxgenjs`
  - icon 元素另需 `npm install -g react-icons react react-dom sharp`
    （缺失时仅 icon 元素 warn+skip，不影响整 deck 渲染）

CLI:
    python -m scripts.render_pptx <slide_spec.json> <out.pptx> [--dry-run]

`--dry-run` 只生成 build.js 不调 node，方便调试。
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# JS 模板：参数化的 PptxGenJS 程序，spec 通过 require() 注入
JS_TEMPLATE = r"""
const path = require("path");
const pptxgen = require("pptxgenjs");

const specPath = process.argv[2];
const workdir  = process.argv[3];
const outPath  = process.argv[4];
const spec = require(path.resolve(specPath));

const pres = new pptxgen();
pres.layout = spec.layout || "LAYOUT_16x9";
pres.author = "paper2slides";
pres.title  = spec.deck_title || "Untitled";

const SHAPE_MAP = {
  rect:         pres.shapes.RECTANGLE,
  oval:         pres.shapes.OVAL,
  line:         pres.shapes.LINE,
  rounded_rect: pres.shapes.ROUNDED_RECTANGLE,
};

function clean(c) {
  if (!c) return undefined;
  return String(c).replace(/^#/, "");
}

function normalizeText(text, useBullet) {
  // 字符串 → 直接传
  if (typeof text === "string") return text;
  // 数组 → PptxGenJS rich-text，配合 breakLine 自动换行；可选每行 bullet
  if (Array.isArray(text)) {
    return text.map((item, idx) => {
      const isLast = idx === text.length - 1;
      const baseOpts = useBullet ? { bullet: true } : {};
      if (typeof item === "string") {
        return {
          text: item,
          options: Object.assign({}, baseOpts, { breakLine: !isLast }),
        };
      }
      return {
        text: item.text || "",
        options: Object.assign(
          {},
          baseOpts,
          item.options || {},
          { breakLine: !isLast },
        ),
      };
    });
  }
  return String(text || "");
}

// icon 元素：react-icons → react-dom/server SVG → sharp 光栅 PNG → base64 data URI。
// 依赖 lazy require（react/react-dom/sharp/react-icons 缺失不影响无 icon 的 deck）。
// 任一步失败都 warn + 返回 null，渲染时该 icon 跳过，不阻断整 deck。
async function iconToDataUri(lib, name, color, size) {
  let React, ReactDOMServer, sharp, mod;
  try {
    React = require("react");
    ReactDOMServer = require("react-dom/server");
    sharp = require("sharp");
  } catch (e) {
    console.error("[warn] icon deps missing (react/react-dom/sharp), skipped");
    return null;
  }
  try {
    mod = require("react-icons/" + (lib || "fa"));
  } catch (e) {
    console.error("[warn] icon lib not found: " + lib + ", skipped");
    return null;
  }
  const Ic = mod[name];
  if (typeof Ic !== "function") {
    console.error("[warn] unknown icon: " + lib + "/" + name + ", skipped");
    return null;
  }
  try {
    const svg = ReactDOMServer.renderToStaticMarkup(
      React.createElement(Ic, { color: color || "#000000", size: String(size || 256) }));
    const png = await sharp(Buffer.from(svg)).png().toBuffer();
    return "image/png;base64," + png.toString("base64");
  } catch (e) {
    console.error("[warn] icon render failed " + lib + "/" + name + ": "
      + (e && e.message) + ", skipped");
    return null;
  }
}

const iconCache = new Map();
function iconKey(el) {
  return [el.lib || "fa", el.icon, el.color || "", el.iconSize || 256].join("|");
}
// 预扫描所有 icon 元素，去重后并发光栅，结果存进 iconCache；
// 无 icon 时 jobs=[]，Promise.all([]) 立即 resolve —— 与旧行为严格等价。
function buildIconCache() {
  const jobs = [];
  for (const sd of (spec.slides || [])) {
    for (const el of (sd.elements || [])) {
      if (el.kind === "icon") {
        const k = iconKey(el);
        if (!iconCache.has(k)) {
          iconCache.set(k, null);
          jobs.push(
            iconToDataUri(el.lib, el.icon, el.color, el.iconSize)
              .then((d) => iconCache.set(k, d)));
        }
      }
    }
  }
  return Promise.all(jobs);
}

function renderSlides() {
for (const slideDef of (spec.slides || [])) {
  const slide = pres.addSlide();

  const elements = [...(slideDef.elements || [])].sort(
    (a, b) => (a.z || 0) - (b.z || 0),
  );

  for (const el of elements) {
    if (el.kind === "text") {
      const opts = {
        x: el.x, y: el.y, w: el.w, h: el.h,
        fontFace: el.fontFace || "Calibri",
        fontSize: el.fontSize || 14,
        bold:     !!el.bold,
        italic:   !!el.italic,
        color:    clean(el.color) || "363636",
        align:    el.align  || "left",
        valign:   el.valign || "top",
        margin:   el.margin === undefined ? 0 : el.margin,
      };
      // role='title' 自动 autoFit：长标题自动缩字号保持单行，避免孤词换行
      if (el.role === "title") {
        opts.autoFit = true;
        opts.wrap = true;
      }
      const useBullet = !!el.bullet;
      slide.addText(normalizeText(el.text, useBullet), opts);
    } else if (el.kind === "image") {
      const imgPath = path.isAbsolute(el.path)
        ? el.path
        : path.join(workdir, el.path);
      const opts = { path: imgPath, x: el.x, y: el.y, w: el.w, h: el.h };
      // 强制等比缩放（contain）—— spec 给的 (w, h) 视作"最大框"，图按原比例放入
      // 框内剩余空间留白；不会变形拉伸。spec 显式给了 sizing 时尊重之
      opts.sizing = el.sizing || { type: "contain", w: el.w, h: el.h };
      slide.addImage(opts);
    } else if (el.kind === "shape") {
      const shape = SHAPE_MAP[el.shape];
      if (!shape) {
        console.error("[warn] unknown shape: " + el.shape + ", skipped");
        continue;
      }
      const opts = { x: el.x, y: el.y, w: el.w, h: el.h };
      if (el.fill)         opts.fill = { color: clean(el.fill) };
      if (el.line_color)   opts.line = {
        color: clean(el.line_color),
        width: el.line_width || 1,
      };
      if (el.transparency !== undefined) opts.transparency = el.transparency;
      if (el.shape === "rounded_rect" && el.rectRadius)
        opts.rectRadius = el.rectRadius;
      slide.addShape(shape, opts);
    } else if (el.kind === "line") {
      slide.addShape(pres.shapes.LINE, {
        x: el.x, y: el.y, w: el.w, h: el.h,
        line: {
          color:    clean(el.color)  || "000000",
          width:    el.width || 1,
          dashType: el.dashType || "solid",
        },
      });
    } else if (el.kind === "icon") {
      const data = iconCache.get(iconKey(el));
      if (!data) continue;  // 降级：取不到 data URI（依赖缺失/名错/光栅失败）跳过此 icon
      slide.addImage({ data: data, x: el.x, y: el.y, w: el.w, h: el.h });
    } else {
      console.error("[warn] unknown element kind: " + el.kind + ", skipped");
    }
  }

  if (slideDef.speaker_notes) slide.addNotes(slideDef.speaker_notes);
}
}

buildIconCache()
  .then(() => { renderSlides(); return pres.writeFile({ fileName: outPath }); })
  .then(() => {
    process.stdout.write(JSON.stringify({
      ok: true, output: outPath, slides: (spec.slides || []).length,
    }) + "\n");
  })
  .catch((err) => {
    process.stderr.write("[error] " + (err && err.stack || err) + "\n");
    process.exit(1);
  });
"""


def _need_node() -> None:
    if shutil.which("node") is None:
        raise SystemExit(
            "node not found in PATH. Install Node.js 20+ and "
            "`sudo npm install -g pptxgenjs react-icons react react-dom sharp` "
            "first (后四个仅 icon 元素需要)。")


def _resolve_node_path() -> str | None:
    """让 node 能 require('pptxgenjs')。优先全局 npm root，然后 NODE_PATH 环境变量。"""
    try:
        out = subprocess.run(["npm", "root", "-g"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return os.environ.get("NODE_PATH")


def _normalize_image_boxes(spec: dict, workdir: Path) -> None:
    """对每个 image element 用 PIL 读原图实际尺寸，把 (x, y, w, h) 调成"按原图比例
    等比缩放后居中放进原 box"的最终值。

    PptxGenJS 的 sizing.contain 在某些版本/比例上不可靠（实测在 attention 论文 s11
    表格上图被纵向拉长——尽管 spec 已显式设了 contain）。改为 Python 端先算好实际
    占位，PptxGenJS 直接拿到正确 (w, h) 渲染，与 sizing 字段无关，永远不变形。
    """
    try:
        from PIL import Image
    except ImportError:
        return
    for slide in spec.get("slides", []):
        for el in slide.get("elements", []):
            if el.get("kind") != "image":
                continue
            img_path = el.get("path", "")
            if not img_path:
                continue
            full = (Path(img_path) if Path(img_path).is_absolute()
                    else workdir / img_path)
            try:
                with Image.open(full) as im:
                    iw, ih = im.size
            except Exception:
                continue
            box_w = float(el.get("w") or 0)
            box_h = float(el.get("h") or 0)
            if box_w <= 0 or box_h <= 0 or iw <= 0 or ih <= 0:
                continue
            scale = min(box_w / iw, box_h / ih)
            new_w = iw * scale
            new_h = ih * scale
            # 在原 box 内居中，调整 x/y 让等比缩放后的图在原 box 中央
            offset_x = (box_w - new_w) / 2
            offset_y = (box_h - new_h) / 2
            el["x"] = round(float(el.get("x") or 0) + offset_x, 3)
            el["y"] = round(float(el.get("y") or 0) + offset_y, 3)
            el["w"] = round(new_w, 3)
            el["h"] = round(new_h, 3)
            # 既然 (w, h) 已是按原比例的实际占位，PptxGenJS 不再需要 sizing
            el.pop("sizing", None)


def render(spec_path: Path, out_path: Path,
           dry_run: bool = False) -> Path:
    spec_path = spec_path.resolve()
    out_path = out_path.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    workdir = spec_path.parent

    # render 前规范化所有 image 的 (x, y, w, h) 为按原图比例等比缩放居中（不依赖
    # PptxGenJS 的 sizing.contain，那个实测不稳）。会回写一份 normalized spec 到
    # render/build_spec.json，作为给 PptxGenJS 的最终输入
    _normalize_image_boxes(spec, workdir)

    render_dir = workdir / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    build_spec = render_dir / "build_spec.json"
    build_spec.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    build_js = render_dir / "build.js"
    build_js.write_text(JS_TEMPLATE.lstrip("\n"), encoding="utf-8")

    if dry_run:
        return build_js

    _need_node()
    env = os.environ.copy()
    np = _resolve_node_path()
    if np:
        env["NODE_PATH"] = np

    proc = subprocess.run(
        ["node", str(build_js), str(build_spec), str(workdir), str(out_path)],
        capture_output=True, text=True, env=env,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "node failed:\n--- stdout ---\n" + proc.stdout +
            "\n--- stderr ---\n" + proc.stderr)
    # 成功时也透传 node 的 stderr：icon 降级 / unknown shape|kind 等 [warn] 是
    # Stage 6 QA 与 smoke 断言要依赖的诊断信号，不能因 rc==0 被吞。
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    sys.stdout.write(proc.stdout)
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="paper2slides Stage 5: render pptx")
    p.add_argument("spec", type=Path, help="slide_spec.json 路径")
    p.add_argument("output", type=Path, help="输出 .pptx 路径")
    p.add_argument("--dry-run", action="store_true",
                   help="只生成 build.js 不调 node，便于调试")
    args = p.parse_args()
    out = render(args.spec, args.output, dry_run=args.dry_run)
    print(out)


if __name__ == "__main__":
    main()
