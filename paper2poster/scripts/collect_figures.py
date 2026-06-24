#!/usr/bin/env python3
"""把 poster.html 引用的本地图片收拢进同级 images/ 目录，并把 src 改写为 images/<名>，
产出目录式可分发海报（poster.html + images/），图多 / 图大也不撑爆单文件。

用法：
    python collect_figures.py <in.html> [out.html]   # out 省略＝原地覆盖 in.html

迭代期用相对路径 src（如 src="parsed/figures/x.jpg"）写 poster.html——screenshot.py /
geom_check.py 都能经 file:// 解析、文件小好改。定稿后跑本脚本一次：每张本地图复制到 out.html
同级的 images/<basename>，src 改写为 images/<basename>。已是 data: / http(s): / images/ 的 src
原样保留；同名不同源的图自动加序号避免互相覆盖。
"""
import re
import shutil
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：collect_figures.py <in.html> [out.html]", file=sys.stderr)
        return 2
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src
    html = src.read_text(encoding="utf-8")
    src_base = src.parent                 # 相对 src 按输入 html 所在目录解析
    images_dir = dst.parent / "images"
    by_source: dict[str, str] = {}        # 源绝对路径 → images/<名>，同图只复制一次
    used: set[str] = set()
    n = [0]

    def repl(m: re.Match) -> str:
        url = m.group(2)
        if url.startswith(("data:", "http:", "https:", "//", "images/")):
            return m.group(0)
        p = (src_base / url).resolve()
        if not p.exists():
            print(f"⚠ 找不到图片，原样保留：{url}", file=sys.stderr)
            return m.group(0)
        key = str(p)
        if key not in by_source:
            name = p.name
            i = 2
            while name in used:           # 同名不同源 → 加序号
                name = f"{p.stem}_{i}{p.suffix}"
                i += 1
            used.add(name)
            images_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, images_dir / name)
            by_source[key] = f"images/{name}"
            n[0] += 1
        return f"{m.group(1)}{by_source[key]}{m.group(3)}"

    out = re.sub(r'(\bsrc\s*=\s*")([^"]+)(")', repl, html)
    out = re.sub(r"(\bsrc\s*=\s*')([^']+)(')", repl, out)
    dst.write_text(out, encoding="utf-8")
    print(f"收拢 {n[0]} 张图 → {images_dir}/；src 改写为 images/<名> → {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
