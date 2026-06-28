#!/usr/bin/env python3
"""html render self-check — quantifies the **visual** issues that validate.py (static text checks) can't catch, after rendering, for you to judge.

Usage:
    python render_check.py <index.html>          # default viewport width 1200
    python render_check.py <index.html> 1440      # custom viewport width

Checks (all require real rendering to see, so validate.py structurally can't catch them):
  1. Distorted figures: each <img>'s rendered aspect ratio differs from its natural aspect ratio by ≤ 0.02 (content-box,
     subtracting border/padding for the fraction; a good `width:100%;height:auto` figure always passes,
     while a real distortion from forced fixed width/height is still caught). This is exactly the "post-render self-check" rule from html-authoring.md, tooled here.
  2. Broken figures: naturalWidth==0 (wrong src path / missing file), rendered as a broken image.
  3. Horizontal overflow: documentElement.scrollWidth clearly exceeds the viewport width → some element pushes the page wide, causing horizontal scroll on mobile.
  4. Clipped content: a normal-flow child overflows the right edge inside an overflow-x:hidden/clip box → content is clipped and unscrollable (most common when a
     wide table/block is forced into a narrow container on mobile). Page-level scrollWidth can't catch it (the clipping is swallowed inside the hidden box); hence a separate check.
  5. MathJax render failure: leftover <mjx-merror> (a formula didn't parse) or unrendered `$…$`/`\\(…\\)`/`$$…$$` remaining in the body.
  6. Image upscaling (soft warning): rendered width > natural width ×1.5 → a small image blown up and blurry (html-authoring.md "don't upscale").

Outputs JSON (verdict + per-check values); exit code 0=pass, 1=fail. 1–5 are hard metrics, 6 is only a warning and doesn't cause FAIL.
This script only checks "render-layer defects"; layout/aesthetics/design language are still for you to judge.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

_JS = r"""
() => {
  const px = (v) => parseFloat(v) || 0;
  const imgs = [...document.querySelectorAll('img')].map((im) => {
    const r = im.getBoundingClientRect();
    const st = getComputedStyle(im);
    const cw = r.width  - px(st.borderLeftWidth) - px(st.borderRightWidth) - px(st.paddingLeft) - px(st.paddingRight);
    const ch = r.height - px(st.borderTopWidth)  - px(st.borderBottomWidth) - px(st.paddingTop) - px(st.paddingBottom);
    const broken = !im.naturalWidth || !im.naturalHeight;
    const ok = !broken && ch > 0;
    const nat = ok ? im.naturalWidth / im.naturalHeight : null;
    const ren = ok ? cw / ch : null;
    return {
      alt: (im.alt || '').slice(0, 40),
      src: (im.getAttribute('src') || '').slice(-50),
      natW: im.naturalWidth, natH: im.naturalHeight,
      renW: Math.round(cw), renH: Math.round(ch),
      broken,
      ratioErr: ok ? +Math.abs(ren - nat).toFixed(3) : null,
      upscale: ok && im.naturalWidth ? +(cw / im.naturalWidth).toFixed(2) : null,
    };
  });
  const de = document.documentElement;
  // MathJax v3 renders a parse failure as <mjx-merror>; if not loaded/failed, the body keeps the original delimiters.
  const merrors = document.querySelectorAll('mjx-merror, .mjx-merror').length;
  const bodyText = document.body ? document.body.innerText : '';
  // Leftover unrendered TeX: `\(…\)` / `\[…\]` and block-level `$$…$$` almost never appear in the body, so they can be judged directly — especially a bare `$$`:
  // currency uses a single `$` and never doubles, so a `$$` in the body means MathJax didn't consume that block-level formula (e.g. a bare `<`
  // inside the formula was treated as an HTML tag, splitting `$$` from the body and making MathJax skip it). A single `$…$` easily collides with currency ("$5 to $10"),
  // so it only counts when the delimiters contain a math signal (backslash command / ^ / _ / {), to avoid false positives on amounts.
  const rawTex = /\\\([^)]{1,}\\\)|\\\[[^\]]{1,}\\\]|\$[^$\n]*[\\^_{][^$\n]*\$/.test(bodyText)
                 || bodyText.includes('$$');
  // Element-level horizontal clipping: inside an overflow-x:hidden/clip box, a normal-flow child's right edge exceeding the box = content clipped and **unscrollable**
  // (most common when a wide table/block is forced into a narrow container on mobile). Page-level scrollWidth can't catch it — the clipping is swallowed inside the hidden box and doesn't widen the page.
  // Only checks explicit hidden/clip (auto/scroll can be scrolled to, not a defect); only looks at normal-flow children (skips position:absolute/fixed
  // decorations, and ::after glow etc. pseudo-elements aren't in children anyway), so purely decorative overflow doesn't false-positive.
  const clipped = [];
  for (const el of document.querySelectorAll('*')) {
    const st = getComputedStyle(el);
    if (st.overflowX !== 'hidden' && st.overflowX !== 'clip') continue;
    if (el.scrollWidth - el.clientWidth <= 4) continue;
    const right = el.getBoundingClientRect().right;
    for (const ch of el.children) {
      const cs = getComputedStyle(ch);
      if (cs.position === 'absolute' || cs.position === 'fixed') continue;
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      if (ch.getBoundingClientRect().right - right > 4) {
        clipped.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className && el.className.toString ? el.className.toString() : '').slice(0, 40),
          child: ch.tagName.toLowerCase(),
          clipped_px: el.scrollWidth - el.clientWidth,
        });
        break;
      }
    }
  }
  return {
    imgs,
    scrollW: de.scrollWidth, clientW: de.clientWidth,
    innerW: window.innerWidth,
    merrors, rawTex, clipped,
  };
}
"""


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: render_check.py <index.html> [viewport_width]", file=sys.stderr)
        return 2
    html = sys.argv[1]
    vw = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
    url = Path(html).resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": vw, "height": 900})
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(600)  # let MathJax / web fonts settle
        data = page.evaluate(_JS)
        browser.close()

    imgs = data["imgs"]
    distorted = [im for im in imgs if im["ratioErr"] is not None and im["ratioErr"] > 0.02]
    broken = [im for im in imgs if im["broken"]]
    upscaled = [im for im in imgs if im["upscale"] is not None and im["upscale"] > 1.5]
    h_overflow = data["scrollW"] - data["innerW"]
    h_overflow_fail = h_overflow > 2
    mathjax_fail = data["merrors"] > 0 or data["rawTex"]
    clipped = data.get("clipped", [])

    ok = not distorted and not broken and not h_overflow_fail and not mathjax_fail and not clipped
    out = {
        "verdict": "PASS" if ok else "FAIL",
        "viewport_width": vw,
        "n_images": len(imgs),
        "distorted_images": distorted,
        "broken_images": broken,
        "h_overflow_px": h_overflow, "h_overflow_fail": h_overflow_fail,
        "mathjax": {"merrors": data["merrors"], "raw_tex_left": data["rawTex"], "fail": mathjax_fail},
        "clipped_content": clipped,
        "upscaled_images_warn": upscaled,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
