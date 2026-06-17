"""
page_screenshot.py — 从某页 PNG 裁剪指定 bbox 区域

适合 Stage 4 的图表回退路径：当 figure 的嵌入图碎片化或不存在时，从 pages/
里的整页 PNG 裁出图所在区域当 image 元素用。

输入 bbox 以**相对比例 0..1** 表达，便于你在不知道具体像素时也能下指令。
比如某图占据整页中段（垂直 30%-65%），传 (x=0, y=0.30, w=1, h=0.35)。

设计要点：
  - 默认 `pad=0.005` 四边外扩，clamp 到 [0, 1]：救 booktabs 表底线被 1px 切掉的问题
  - 文件名按 `(page, x, y, w, h, pad)` 的 SHA1 前 8 位编码：同 bbox → 同名 → 自动幂等，
    避免 Stage 4 改 bbox 重裁时 render/ 累积孤儿文件
  - 同名已存在时，默认直接返回（不重写），加 `--replace` 才覆盖

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

    # 应用 pad 外扩 + clamp
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
                   help=f"四边外扩比例（默认 {DEFAULT_PAD}），用于救表格底线/字体粗描边的 1-2px 误差")
    p.add_argument("--out", default=None,
                   help="输出 PNG 文件名（默认 crop-pNN-<hash8>.png，存到 workdir/render/）")
    p.add_argument("--replace", action="store_true",
                   help="即使同名 crop 已存在也强制重写（默认幂等：直接返回已有路径）")
    args = p.parse_args()

    out_path = crop_page(args.workdir.resolve(), args.page,
                         args.x, args.y, args.w, args.h,
                         out_name=args.out, pad=args.pad,
                         replace=args.replace)
    print(out_path)


if __name__ == "__main__":
    main()
