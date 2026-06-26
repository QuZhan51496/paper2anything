#!/usr/bin/env python3
"""Poster geometry-gate self-check — the three **structure-agnostic** hard metrics from SKILL.md Step 5a, quantified for your judgment.

Usage:
    python geom_check.py <poster.html> <width_px> <height_px>

Checks (all structure-agnostic, independent of your layout class names):
  1. No overflow: the content's right/bottom edge does not exceed the canvas (the larger of scrollWidth/Height and the true content frontier).
  2. Fill ratio ≥ 0.95: the content frontier is computed from the lowest bottom edge of the **elements that actually carry text and the <img>s** (absolute coordinates),
     not from some container box — a fixed-height `.poster` / full-page background would mask overflow or whitespace as "just filled".
     (Vertical axis; on overflow this value goes >1, in which case the overflow field governs — verdict has already been judged FAIL from the overflow.)
  3. No distorted figures: each <img>'s rendered aspect ratio differs from its natural aspect ratio by ≤ 0.02.
  4. No clipping: a panel whose overflow is not visible has not had its content cut off (scrollHeight ≤ clientHeight).
     flex equal-height columns can shrink content and then have it cut by overflow:hidden, making overflow / fill ratio **falsely pass** —
     each panel's scrollHeight must be checked individually, otherwise a poster with clipped content would be misjudged as PASS.

Outputs JSON (verdict + each metric); exit code 0=pass, 1=fail.

**Per-panel internal whitespace** (panel.bottom−lastChild, gaps between children) depends on your own layout structure
and is not in this script — judge that part yourself per Step 5a by looking at poster.png and measuring against your own panel selectors.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

_JS = r"""
(canvas) => {
  const W = canvas.w, H = canvas.h;
  const de = document.documentElement;
  const hasDirectText = (el) => {
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) return true;
    }
    return false;
  };
  // Content frontier: only look at elements that truly carry content (elements with direct text + <img>),
  // skip pure layout containers / full-page backgrounds (they have no direct text and would stretch to the canvas bottom, misleading the fill ratio).
  let maxB = 0, maxR = 0;
  for (const el of document.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') continue;
    if (el.tagName !== 'IMG' && !hasDirectText(el)) continue;
    maxB = Math.max(maxB, r.bottom + window.scrollY);
    maxR = Math.max(maxR, r.right + window.scrollX);
  }
  // Distortion is measured on the image's **content box** (getBoundingClientRect minus border/padding, at fractional precision), not the
  // border-box — for a non-square image with a CSS border the border-box aspect ratio drifts from the real image ratio (the border takes a larger share on the narrow side),
  // making a good height:auto image be misjudged as distorted FAIL. Subtracting the border + using fractions (to avoid clientHeight's integer rounding error on very flat images)
  // keeps proportional images always passing while still catching real distortion (a hard-coded width+height).
  const px = (v) => parseFloat(v) || 0;
  const imgs = [...document.querySelectorAll('img')].map((im) => {
    const r = im.getBoundingClientRect();
    const st = getComputedStyle(im);
    const cw = r.width  - px(st.borderLeftWidth) - px(st.borderRightWidth) - px(st.paddingLeft) - px(st.paddingRight);
    const ch = r.height - px(st.borderTopWidth)  - px(st.borderBottomWidth) - px(st.paddingTop) - px(st.paddingBottom);
    const ok = im.naturalHeight && ch > 0;
    const nat = ok ? im.naturalWidth / im.naturalHeight : null;
    const ren = ok ? cw / ch : null;
    return {
      alt: (im.alt || '').slice(0, 40),
      natW: im.naturalWidth, natH: im.naturalHeight,
      renW: Math.round(cw), renH: Math.round(ch),
      ratioErr: ok ? +Math.abs(ren - nat).toFixed(3) : null,
    };
  });
  // Clip detection: for a panel whose overflow is not visible, if scrollHeight>clientHeight the content has been cut off.
  // getBoundingClientRect measures the clipped / compressed box, which would let overflow and fill ratio falsely pass — check it separately.
  const clipped = [];
  for (const el of document.querySelectorAll('*')) {
    if (el === document.body || el === document.documentElement) continue;
    const st = getComputedStyle(el);
    const dv = (st.overflowY !== 'visible' && el.scrollHeight - el.clientHeight > 2)
      ? el.scrollHeight - el.clientHeight : 0;
    const dh = (st.overflowX !== 'visible' && el.scrollWidth - el.clientWidth > 2)
      ? el.scrollWidth - el.clientWidth : 0;
    if (dv || dh) {
      clipped.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className && el.className.toString ? el.className.toString() : '').slice(0, 40),
        clippedY: dv, clippedX: dh,
        text: (el.textContent || '').trim().slice(0, 50),
      });
    }
  }
  return {
    scrollH: Math.max(de.scrollHeight, Math.round(maxB)),
    scrollW: Math.max(de.scrollWidth, Math.round(maxR)),
    contentBottom: Math.round(maxB),
    contentRight: Math.round(maxR),
    imgs, clipped,
  };
}
"""


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: geom_check.py <poster.html> <width_px> <height_px>", file=sys.stderr)
        return 2
    html, W, H = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    url = Path(html).resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(300)
        data = page.evaluate(_JS, {"w": W, "h": H})
        browser.close()

    overflow_y = data["scrollH"] - H
    overflow_x = data["scrollW"] - W
    fill = round(data["contentBottom"] / H, 3) if H else 0.0
    distorted = [im for im in data["imgs"] if im["ratioErr"] is not None and im["ratioErr"] > 0.02]
    clipped = data.get("clipped", [])
    overflow = overflow_y > 1 or overflow_x > 1
    underfill = fill < 0.95
    ok = not overflow and not underfill and not distorted and not clipped

    out = {
        "verdict": "PASS" if ok else "FAIL",
        "canvas": {"w": W, "h": H},
        "overflow": {"x_px": overflow_x, "y_px": overflow_y, "fail": overflow},
        "fill_ratio": fill, "fill_fail": underfill,
        "n_images": len(data["imgs"]),
        "distorted_images": distorted,
        "clipped_panels": clipped,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
