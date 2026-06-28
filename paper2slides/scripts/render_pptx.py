"""
render_pptx.py — Stage 4: slide_spec.json → output.pptx bridge

Translate the structured spec into a PptxGenJS program (`build.js`) and run it with node to produce the .pptx.
Why PptxGenJS rather than python-pptx? PptxGenJS is the more capable from-scratch generation path for rich
visual decks, and this skill's pitfall/design docs (references/pptxgenjs.md) are written against it.

Dependencies:
  - node on PATH
  - pptxgenjs on NODE_PATH or global: `npm install -g pptxgenjs`
  - icon elements additionally need `npm install -g react-icons react react-dom sharp`
    (when missing, only icon elements warn+skip, without affecting the whole-deck render)

CLI:
    python -m scripts.render_pptx <slide_spec.json> <out.pptx> [--dry-run]

`--dry-run` only generates build.js without calling node, for easy debugging.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# JS template: a parameterized PptxGenJS program; the spec is injected via require()
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
  // string → pass through directly
  if (typeof text === "string") return text;
  // array → PptxGenJS rich-text, using breakLine for automatic line-wrapping; optional per-line bullet
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

// icon element: react-icons → react-dom/server SVG → sharp raster PNG → base64 data URI.
// Relies on lazy require (missing react/react-dom/sharp/react-icons does not affect a deck without icons).
// Any failed step warns + returns null; at render time that icon is skipped, without blocking the whole deck.
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
// Pre-scan all icon elements, dedup then rasterize concurrently, storing the results into iconCache;
// when there are no icons jobs=[], and Promise.all([]) resolves immediately.
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
      // role='title' gets automatic autoFit: long titles auto-shrink the font size to keep a single line, avoiding orphan-word wrapping
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
      // Force proportional scaling (contain) — the (w, h) given by the spec is treated as the "max box"; the image is placed in by its original ratio
      // and the remaining space inside the box is left blank; no distortion-stretching. When the spec explicitly gives sizing, respect it
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
      if (!data) continue;  // degraded path: when the data URI can't be obtained (deps missing / wrong name / raster failure), skip this icon
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
            "first (the latter four are only needed for icon elements).")


def _resolve_node_path() -> str | None:
    """Let node be able to require('pptxgenjs'). Prefer the global npm root, then the NODE_PATH environment variable."""
    try:
        out = subprocess.run(["npm", "root", "-g"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return os.environ.get("NODE_PATH")


def _normalize_image_boxes(spec: dict, workdir: Path) -> None:
    """For each image element, read the original image's actual dimensions with PIL, and
    adjust (x, y, w, h) to the final values of "proportionally scaled by the original
    image's ratio, then centered into the original box".

    PptxGenJS's sizing.contain is unreliable on some versions/ratios (measured: on the
    attention paper s11 table the image got stretched vertically — even though the spec
    already explicitly set contain). This function therefore computes the actual placement on the
    Python side, so PptxGenJS directly gets the correct (w, h) to render,
    independent of the sizing field, and never distorts.
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
            # center within the original box; adjust x/y so the proportionally scaled image sits at the box's center
            offset_x = (box_w - new_w) / 2
            offset_y = (box_h - new_h) / 2
            el["x"] = round(float(el.get("x") or 0) + offset_x, 3)
            el["y"] = round(float(el.get("y") or 0) + offset_y, 3)
            el["w"] = round(new_w, 3)
            el["h"] = round(new_h, 3)
            # since (w, h) is already the actual placement by the original ratio, PptxGenJS needs no sizing
            el.pop("sizing", None)


def render(spec_path: Path, out_path: Path,
           dry_run: bool = False) -> Path:
    spec_path = spec_path.resolve()
    out_path = out_path.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    workdir = spec_path.parent

    # before render, normalize every image's (x, y, w, h) to be proportionally scaled by
    # the original image's ratio and centered (not relying on PptxGenJS's sizing.contain,
    # which is measured to be unstable). Writes back a normalized spec to
    # render/build_spec.json as the final input given to PptxGenJS
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
    # on success, also pass through node's stderr: [warn]s like icon degraded path /
    # unknown shape|kind are diagnostic signals that Stage 5 QA and smoke assertions
    # depend on, and must not be swallowed just because rc==0.
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    sys.stdout.write(proc.stdout)
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="paper2slides Stage 4: render pptx")
    p.add_argument("spec", type=Path, help="slide_spec.json path")
    p.add_argument("output", type=Path, help="output .pptx path")
    p.add_argument("--dry-run", action="store_true",
                   help="only generate build.js without calling node, for easy debugging")
    args = p.parse_args()
    out = render(args.spec, args.output, dry_run=args.dry_run)
    print(out)


if __name__ == "__main__":
    main()
