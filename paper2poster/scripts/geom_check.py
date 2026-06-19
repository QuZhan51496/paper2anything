#!/usr/bin/env python3
"""poster 几何闸门自检 —— SKILL.md Step 5a 里**结构无关**的三项硬指标，量化好供你判断。

用法：
    python geom_check.py <poster.html> <width_px> <height_px>

检查（全部结构无关、不依赖你的版式类名）：
  1. 无溢出：内容右/下缘不超过画布（scrollWidth/Height 与真·内容前沿取大者）。
  2. 填充率 ≥ 0.95：内容前沿按**实际带文字的元素与 <img>** 的最低底边算（绝对坐标），
     不取某个容器盒——固定高度的 `.poster`/整页背景会把溢出或留白掩盖成"刚好填满"。
  3. 无图变形：每张 <img> 的 rendered 宽高比与 natural 宽高比之差 ≤ 0.02。

输出 JSON（verdict + 各项数值）；退出码 0=过、1=不过。

**per-panel 内部留白**（panel.bottom−lastChild、子元素间隙）依赖你自己的版式结构，
不在本脚本内——那部分按 Step 5a 看 poster.png 自己判断、对自己的面板选择器量。
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
  // 内容前沿：只看真正承载内容的元素（带直接文字的元素 + <img>），
  // 跳过纯布局容器 / 整页背景（它们没有直接文字、会一路撑到画布底误导填充率）。
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
  const imgs = [...document.querySelectorAll('img')].map((im) => {
    const r = im.getBoundingClientRect();
    const ok = im.naturalHeight && r.height;
    const nat = ok ? im.naturalWidth / im.naturalHeight : null;
    const ren = ok ? r.width / r.height : null;
    return {
      alt: (im.alt || '').slice(0, 40),
      natW: im.naturalWidth, natH: im.naturalHeight,
      renW: Math.round(r.width), renH: Math.round(r.height),
      ratioErr: ok ? +Math.abs(ren - nat).toFixed(3) : null,
    };
  });
  return {
    scrollH: Math.max(de.scrollHeight, Math.round(maxB)),
    scrollW: Math.max(de.scrollWidth, Math.round(maxR)),
    contentBottom: Math.round(maxB),
    contentRight: Math.round(maxR),
    imgs,
  };
}
"""


def main() -> int:
    if len(sys.argv) != 4:
        print("用法：geom_check.py <poster.html> <width_px> <height_px>", file=sys.stderr)
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
    overflow = overflow_y > 1 or overflow_x > 1
    underfill = fill < 0.95
    ok = not overflow and not underfill and not distorted

    out = {
        "verdict": "PASS" if ok else "FAIL",
        "canvas": {"w": W, "h": H},
        "overflow": {"x_px": overflow_x, "y_px": overflow_y, "fail": overflow},
        "fill_ratio": fill, "fill_fail": underfill,
        "n_images": len(data["imgs"]),
        "distorted_images": distorted,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
