#!/usr/bin/env python3
"""Gather the local images referenced by poster.html into a sibling images/ directory and rewrite each src to images/<name>,
producing a directory-style distributable poster (poster.html + images/) that doesn't bloat a single file even with many / large images.

Usage:
    python collect_figures.py <in.html> [out.html]   # omit out = overwrite in.html in place

While iterating, write poster.html with relative-path srcs (e.g. src="parsed/figures/x.jpg") — screenshot.py /
geom_check.py both resolve them via file://, and the file stays small and easy to edit. Once finalized, run this script once: each local image is copied to
images/<basename> next to out.html, and its src is rewritten to images/<basename>. A src that is already data: / http(s): / images/
is kept as-is; same-named images from different sources are auto-numbered to avoid overwriting each other.
"""
import re
import shutil
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: collect_figures.py <in.html> [out.html]", file=sys.stderr)
        return 2
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src
    html = src.read_text(encoding="utf-8")
    src_base = src.parent                 # relative srcs are resolved against the input html's directory
    images_dir = dst.parent / "images"
    by_source: dict[str, str] = {}        # source absolute path → images/<name>, each image copied only once
    used: set[str] = set()
    n = [0]

    def repl(m: re.Match) -> str:
        url = m.group(2)
        if url.startswith(("data:", "http:", "https:", "//", "images/")):
            return m.group(0)
        p = (src_base / url).resolve()
        if not p.exists():
            print(f"⚠ image not found, keeping as-is: {url}", file=sys.stderr)
            return m.group(0)
        key = str(p)
        if key not in by_source:
            name = p.name
            i = 2
            while name in used:           # same name, different source → add a sequence number
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
    print(f"gathered {n[0]} images → {images_dir}/; srcs rewritten to images/<name> → {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
