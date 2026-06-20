#!/usr/bin/env python3
"""html 渲染自检 —— validate.py（静态查文本）查不到的**视觉**问题，渲染后量化好供你判断。

用法：
    python render_check.py <index.html>          # 默认视口宽 1200
    python render_check.py <index.html> 1440      # 自定义视口宽

检查（都得真渲染才看得到，故 validate.py 结构上抓不到）：
  1. 图变形：每张 <img> 的 rendered 宽高比与 natural 宽高比之差 ≤ 0.02（content-box，
     减 border/padding 取小数——与 poster geom_check 同口径；`width:100%;height:auto` 的好图恒过，
     强行设死宽高的真形变仍抓）。html-authoring.md "渲染后自检" 一条说的正是这项，本脚本把它工具化。
  2. 图破损：naturalWidth==0（src 路径错/文件缺），渲染出来是裂图。
  3. 横向溢出：documentElement.scrollWidth 明显超视口宽 → 有元素把页面撑横，移动端横向滚动。
  4. MathJax 渲染失败：留有 <mjx-merror>（公式没解析成功）或正文残留未渲染的 `$…$`/`\\(…\\)`。
  5. 图上采样（软警告）：rendered 宽 > natural 宽 ×1.5 → 小图被放大显糊（html-authoring.md "勿上采样"）。

输出 JSON（verdict + 各项数值）；退出码 0=过、1=不过。1–4 为硬指标，5 仅警告不判 FAIL。
本脚本只查"渲染层硬伤"，版式/美观/设计语言仍由你看 _preview 截图自己判断。
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
  // MathJax v3 把解析失败渲成 <mjx-merror>；未加载/失败则正文留有原始定界符。
  const merrors = document.querySelectorAll('mjx-merror, .mjx-merror').length;
  const bodyText = document.body ? document.body.innerText : '';
  // 残留未渲染的 TeX：`\(…\)` / `\[…\]` 与块级 `$$…$$` 正文几乎不会有、可直接判——尤其裸 `$$`：
  // 货币只用单 `$`、绝不连用，故正文一旦出现 `$$` 即 MathJax 没吃掉该块级公式（如公式内含裸 `<`
  // 被浏览器当 HTML 标签、把 `$$` 与正文割裂致 MathJax 跳过）。单 `$…$` 易和货币（"$5 到 $10"）撞车，
  // 故只在定界符内含数学信号（反斜杠命令 / ^ / _ / {）时才算，避免误伤金额。
  const rawTex = /\\\([^)]{1,}\\\)|\\\[[^\]]{1,}\\\]|\$[^$\n]*[\\^_{][^$\n]*\$/.test(bodyText)
                 || bodyText.includes('$$');
  return {
    imgs,
    scrollW: de.scrollWidth, clientW: de.clientWidth,
    innerW: window.innerWidth,
    merrors, rawTex,
  };
}
"""


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：render_check.py <index.html> [viewport_width]", file=sys.stderr)
        return 2
    html = sys.argv[1]
    vw = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
    url = Path(html).resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": vw, "height": 900})
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(600)  # 给 MathJax / web font 收尾
        data = page.evaluate(_JS)
        browser.close()

    imgs = data["imgs"]
    distorted = [im for im in imgs if im["ratioErr"] is not None and im["ratioErr"] > 0.02]
    broken = [im for im in imgs if im["broken"]]
    upscaled = [im for im in imgs if im["upscale"] is not None and im["upscale"] > 1.5]
    h_overflow = data["scrollW"] - data["innerW"]
    h_overflow_fail = h_overflow > 2
    mathjax_fail = data["merrors"] > 0 or data["rawTex"]

    ok = not distorted and not broken and not h_overflow_fail and not mathjax_fail
    out = {
        "verdict": "PASS" if ok else "FAIL",
        "viewport_width": vw,
        "n_images": len(imgs),
        "distorted_images": distorted,
        "broken_images": broken,
        "h_overflow_px": h_overflow, "h_overflow_fail": h_overflow_fail,
        "mathjax": {"merrors": data["merrors"], "raw_tex_left": data["rawTex"], "fail": mathjax_fail},
        "upscaled_images_warn": upscaled,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
