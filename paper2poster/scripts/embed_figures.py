#!/usr/bin/env python3
"""把 poster.html 里引用本地图片的 <img src="..."> 内联成 base64 data URI，产出自包含 HTML。

用法：
    python embed_figures.py <in.html> [out.html]   # out 省略＝原地覆盖 in.html

为什么需要它：迭代期请用**相对路径** src（如 `src="parsed/figures/x.jpg"`）写 poster.html
——screenshot.py / geom_check.py 都能经 file:// 解析，且文件小、Edit 改起来快。定稿后跑本
脚本一次，把图内联成可独立分发的 poster.html。已是 data: / http(s): 的 src 原样保留。
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：embed_figures.py <in.html> [out.html]", file=sys.stderr)
        return 2
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src
    html = src.read_text(encoding="utf-8")
    base = src.parent
    n = [0]

    def repl(m: re.Match) -> str:
        url = m.group(2)
        if url.startswith(("data:", "http:", "https:", "//")):
            return m.group(0)
        p = (base / url).resolve()
        if not p.exists():
            print(f"⚠ 找不到图片，原样保留：{url}", file=sys.stderr)
            return m.group(0)
        mime = mimetypes.guess_type(str(p))[0] or "image/png"
        b64 = base64.b64encode(p.read_bytes()).decode()
        n[0] += 1
        return f"{m.group(1)}data:{mime};base64,{b64}{m.group(3)}"

    out = re.sub(r'(\bsrc\s*=\s*")([^"]+)(")', repl, html)
    out = re.sub(r"(\bsrc\s*=\s*')([^']+)(')", repl, out)
    dst.write_text(out, encoding="utf-8")
    print(f"内联 {n[0]} 张图 → {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
