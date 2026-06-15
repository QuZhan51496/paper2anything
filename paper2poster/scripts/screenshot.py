"""Screenshot a self-contained HTML file to a PNG at exact pixel size.

This is a pure instrument for the hand-authored poster path: Claude writes
`poster.html` with the Write tool, then calls this to get a `poster.png` it can
Read and judge by eye. It renders whatever HTML you give it — it does NOT pick
a template, parse an outline, or make any design decision. Use the poster's
intended pixel size (e.g. 20x15 in at 96 dpi -> --width 1920 --height 1440).

    python scripts/screenshot.py poster.html poster.png --width 1920 --height 1440
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def screenshot_html(html_path: Path, png_path: Path, width: int, height: int) -> None:
    from playwright.sync_api import sync_playwright

    png_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        page.goto(html_path.resolve().as_uri())
        page.screenshot(path=str(png_path), full_page=False)
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Screenshot an HTML file to a PNG at exact pixel size."
    )
    parser.add_argument("html", type=Path, help="Path to the self-contained HTML file.")
    parser.add_argument("png", type=Path, help="Output PNG path.")
    parser.add_argument("--width", type=int, default=1920, help="Viewport width in px.")
    parser.add_argument("--height", type=int, default=1440, help="Viewport height in px.")
    args = parser.parse_args()

    if not args.html.is_file():
        print(f"[screenshot] HTML not found: {args.html}", file=sys.stderr)
        return 1
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        print(
            "[screenshot] Playwright is not installed. Run:\n"
            "  pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    screenshot_html(args.html, args.png, args.width, args.height)
    print(f"[screenshot] wrote {args.png} ({args.width}x{args.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
