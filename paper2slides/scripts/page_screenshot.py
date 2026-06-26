"""
page_screenshot.py — crop a specified bbox region from a page's PNG

Suited to Stage 3's chart fallback path: when a figure's embedded image is fragmented or
absent, crop the region where the figure sits from the full-page PNG under pages/ and use
it as an image element.

The input bbox is expressed as a **relative ratio 0..1**, so you can give instructions even
without knowing the exact pixels. For example, if a figure occupies the middle band of the
full page (vertically 30%-65%), pass (x=0, y=0.30, w=1, h=0.35).

Design points:
  - default `pad=0.005` expands all four sides outward, clamped to [0, 1]: rescues the issue of a booktabs table's bottom rule being cut off by 1px
  - the filename is encoded as the first 8 SHA1 hex digits of `(page, x, y, w, h, pad)`: same bbox → same name → automatic idempotency,
    avoiding render/ accumulating orphan files when Stage 3 changes the bbox and re-crops
  - when a same-named file already exists, by default return directly (no rewrite); add `--replace` to overwrite

CLI:
    python -m scripts.page_screenshot <workdir> <page> <x> <y> <w> <h> [--pad P] [--out N] [--replace]
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

DEFAULT_PAD = 0.005


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _hash8(page: int, x: float, y: float, w: float, h: float, pad: float) -> str:
    payload = f"p{page}|{x:.4f}|{y:.4f}|{w:.4f}|{h:.4f}|pad{pad:.4f}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def crop_page(workdir: Path, page: int,
              x: float, y: float, w: float, h: float,
              out_name: str | None = None,
              pad: float = DEFAULT_PAD,
              replace: bool = False) -> Path:
    from PIL import Image
    pages_dir = workdir / "pages"
    candidates = list(pages_dir.glob(f"page-{page}.png")) + \
                 list(pages_dir.glob(f"page-{page:02d}.png")) + \
                 list(pages_dir.glob(f"page-{page:03d}.png"))
    if not candidates:
        raise SystemExit(f"page-{page} render not found in {pages_dir}")
    img_path = candidates[0]

    # apply pad outward expansion + clamp
    x_p = _clamp01(x - pad)
    y_p = _clamp01(y - pad)
    x2_p = _clamp01(x + w + pad)
    y2_p = _clamp01(y + h + pad)

    if out_name is None:
        out_name = f"crop-p{page:02d}-{_hash8(page, x, y, w, h, pad)}.png"
    out = workdir / "render" / out_name
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists() and not replace:
        return out

    with Image.open(img_path) as im:
        W, H = im.size
        box = (int(x_p * W), int(y_p * H), int(x2_p * W), int(y2_p * H))
        im.crop(box).save(out)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Crop a region from a page PNG")
    p.add_argument("workdir", type=Path)
    p.add_argument("page", type=int)
    p.add_argument("x", type=float, help="left, relative 0..1")
    p.add_argument("y", type=float, help="top, relative 0..1")
    p.add_argument("w", type=float, help="width, relative 0..1")
    p.add_argument("h", type=float, help="height, relative 0..1")
    p.add_argument("--pad", type=float, default=DEFAULT_PAD,
                   help=f"outward expansion ratio on all four sides (default {DEFAULT_PAD}), to rescue the 1-2px error of table bottom rules / bold font strokes")
    p.add_argument("--out", default=None,
                   help="output PNG filename (default crop-pNN-<hash8>.png, saved to workdir/render/)")
    p.add_argument("--replace", action="store_true",
                   help="force a rewrite even if a same-named crop already exists (default is idempotent: return the existing path directly)")
    args = p.parse_args()

    out_path = crop_page(args.workdir.resolve(), args.page,
                         args.x, args.y, args.w, args.h,
                         out_name=args.out, pad=args.pad,
                         replace=args.replace)
    print(out_path)


if __name__ == "__main__":
    main()
