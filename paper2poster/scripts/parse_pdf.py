"""
Parse an academic PDF via the MinerU Cloud API: extract Markdown text,
metadata, figures, and tables.

Usage:
    python parse_pdf.py <pdf_path> --output-dir <output_dir>

Environment variables:
    MINERU_API_TOKEN  — Bearer token from https://mineru.net/apiManage/token
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import zipfile
import io

import _env  # noqa: F401  # load the package-root .env (credentials)


# ================================================================
# MinerU Cloud API
# ================================================================

MINERU_API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net")
MINERU_SUBMIT_URL = f"{MINERU_API_BASE}/api/v4/extract/task"
MINERU_RESULT_URL = f"{MINERU_API_BASE}/api/v4/extract/task"  # + /{task_id}
MINERU_POLL_INTERVAL = 3  # seconds
MINERU_MAX_WAIT = 300  # 5 minutes max


def extract_with_mineru(pdf_path: str, output_dir: str, token: str = None):
    """Use MinerU Cloud API for high-quality PDF parsing.

    Flow: request presigned URL → PUT upload file → poll batch result → download zip.
    """
    import requests

    # Force a proxy-free direct connection to mineru.net / Aliyun OSS. An ALL_PROXY=socks5h in the
    # env would make requests go through SOCKS (which errors without pysocks); and
    # proxies={"http":None} gets stripped as a None key by requests' merge_setting and fails to
    # suppress all_proxy — only a Session with trust_env=False truly bypasses it.
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": None, "https": None}

    token = token or os.environ.get("MINERU_API_TOKEN", "")
    if not token:
        raise RuntimeError(
            "MinerU API token not set. Get one at https://mineru.net/apiManage/token\n"
            "Then: export MINERU_API_TOKEN=<your_token>"
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    file_size = os.path.getsize(pdf_path)
    file_name = os.path.basename(pdf_path)
    print(f"  File: {file_name} ({file_size // 1024} KB)")

    # Step 1: Request presigned upload URL via batch endpoint
    batch_url = f"{MINERU_API_BASE}/api/v4/file-urls/batch"
    batch_payload = {
        "files": [{"name": file_name, "is_ocr": False}],
        "enable_formula": True,
        "enable_table": True,
        "model_version": "vlm",
    }
    resp = session.post(batch_url, headers=headers, json=batch_payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Batch request failed ({resp.status_code}): {resp.text[:500]}")

    batch_data = resp.json()
    if batch_data.get("code") != 0:
        raise RuntimeError(f"Batch error: {batch_data.get('msg', batch_data)}")

    batch_id = batch_data["data"]["batch_id"]
    file_urls = batch_data["data"].get("file_urls", [])
    if not file_urls:
        raise RuntimeError(f"No upload URL returned: {batch_data}")

    upload_url = file_urls[0]
    print(f"  Batch ID: {batch_id}")
    print(f"  Uploading to presigned URL...")

    # Step 2: PUT the file to the presigned URL (no extra headers — OSS signature sensitive)
    with open(pdf_path, "rb") as f:
        put_resp = session.put(upload_url, data=f, timeout=120)
    if put_resp.status_code not in (200, 201):
        raise RuntimeError(f"File upload failed ({put_resp.status_code}): {put_resp.text[:300]}")

    print(f"  Upload complete, parsing...")

    # Step 3: Poll batch result
    result_url = f"{MINERU_API_BASE}/api/v4/extract-results/batch/{batch_id}"
    task_id = None

    # Step 3: Poll batch results
    elapsed = 0
    extract_results = None
    while elapsed < MINERU_MAX_WAIT:
        time.sleep(MINERU_POLL_INTERVAL)
        elapsed += MINERU_POLL_INTERVAL

        resp = session.get(result_url, headers=headers, timeout=30)
        result = resp.json()

        if result.get("code") != 0:
            raise RuntimeError(f"Poll error: {result.get('msg', result)}")

        extract_list = result.get("data", {}).get("extract_result", [])
        if extract_list:
            item = extract_list[0]
            state = item.get("state", "unknown")
            if state == "done":
                extract_results = item
                print(f"  Parsing complete ({elapsed}s)")
                break
            elif state in ("failed", "error"):
                raise RuntimeError(f"MinerU task failed: {item}")

        batch_state = result.get("data", {}).get("state", "unknown")
        if batch_state == "done" and not extract_list:
            raise RuntimeError(f"Batch done but no results: {result}")

        if elapsed % 15 == 0:
            print(f"  Waiting... ({elapsed}s)")

    if elapsed >= MINERU_MAX_WAIT:
        raise RuntimeError(f"MinerU task timed out after {MINERU_MAX_WAIT}s")

    # Step 4: Download results
    zip_url = extract_results.get("full_zip_url", "")
    if not zip_url:
        raise RuntimeError(f"No zip URL in result: {extract_results}")

    print(f"  Downloading results...")
    backoff = 2.0
    for attempt in range(1, 4):  # the .cn CDN occasionally throws SSL EOF; exponential-backoff retry
        try:
            resp = session.get(zip_url, timeout=120)
            resp.raise_for_status()
            break
        except Exception as e:
            if attempt == 3:
                raise
            print(f"  download failed ({e}); retry in {backoff:.0f}s ({attempt}/3)")
            time.sleep(backoff)
            backoff *= 2

    # Step 5: Extract zip contents
    md_text = ""
    figures_dir = os.path.join(output_dir, "figures")
    tables_dir = os.path.join(output_dir, "tables")
    os.makedirs(figures_dir, exist_ok=True)
    os.makedirs(tables_dir, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith(".md"):
                md_text = zf.read(name).decode("utf-8", errors="replace")
                md_path = os.path.join(output_dir, "content.md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_text)
            elif lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
                basename = os.path.basename(name)
                if "table" in lower:
                    dest = os.path.join(tables_dir, basename)
                else:
                    dest = os.path.join(figures_dir, basename)
                with open(dest, "wb") as f:
                    f.write(zf.read(name))
            elif lower.endswith("content_list_v2.json"):
                # MinerU v2 content list: list[page][typed block], where block.content is a dict
                # holding title_content/paragraph_content/level; saved as mineru_raw.json for
                # auto_outline.build_digest to consume.
                # Only v2 is used — the other .json files in the zip (middle/model/v1 content_list) are useless for the poster digest.
                json_path = os.path.join(output_dir, "mineru_raw.json")
                with open(json_path, "wb") as f:
                    f.write(zf.read(name))
            elif lower.endswith("layout.json"):
                # layout.json: the reliable source of each figure/table bbox, used by _recrop_inplace to
                # re-crop sharp images from the 300dpi full page (content_list's bbox coordinate system is inconsistent, so it is not used).
                layout_path = os.path.join(output_dir, "layout.json")
                with open(layout_path, "wb") as f:
                    f.write(zf.read(name))

    # Image-sharpness fix: MinerU's extracted figures are downsampled (blurry). Using the bboxes in
    # layout.json, re-crop in place from a pdftoppm 300dpi full-page render, overwriting the same-named
    # extracted figure (keeping the figures/<basename> path unchanged, so the downstream
    # auto_outline/collect_figures reference schema stays intact). Skipped entirely if there is no layout or pdftoppm is unavailable.
    _recrop_inplace(pdf_path, output_dir)

    return md_text


# ================================================================
# High-res in-place recrop (fix blurry MinerU figure extracts)
# ================================================================

def _load_layout(out_dir):
    """Read out_dir/layout.json (the reliable source of each figure/table bbox). Returns None if not found."""
    from pathlib import Path
    p = Path(out_dir) / "layout.json"
    if not p.exists():
        c = sorted(Path(out_dir).glob("*layout*.json"))
        p = c[0] if c else None
    if not p or not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _bbox_pools(layout):
    """Pre-aggregate each page's image/chart/table block bboxes in reading order (unsorted, aligned with the v2 element order)."""
    pools = {"image": {}, "chart": {}, "table": {}}
    for pi, page in enumerate(layout.get("pdf_info", [])):
        for blk in page.get("para_blocks", []):
            bt = blk.get("type")
            if bt in pools and blk.get("bbox"):
                pools[bt].setdefault(pi, []).append(blk["bbox"])
    return pools


def _norm_bbox(b, layout, pi):
    """[x0,y0,x1,y1] absolute pixels (top-origin) → [x,y,w,h] (0..1)."""
    W, H = layout["pdf_info"][pi]["page_size"]
    x0, y0, x1, y1 = b
    return [x0 / float(W), y0 / float(H), (x1 - x0) / float(W), (y1 - y0) / float(H)]


def _render_pages(pdf_path, pages_dir, dpi=300):
    """Render full pages at 300dpi to pages/page-NN.png; -hide-annotations removes hyperlink boxes. Returns False on failure."""
    from pathlib import Path
    Path(pages_dir).mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-hide-annotations",
                        str(pdf_path), str(Path(pages_dir) / "page")], check=True, capture_output=True)
        return any(Path(pages_dir).glob("page-*.png"))
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


def _crop_from_page(pages_dir, page_no, bbox, out_path, pad=0.005):
    """Crop a hi-res image from pages/page-NN.png by the normalized bbox (+pad) into out_path."""
    from pathlib import Path
    from PIL import Image
    cands = (list(Path(pages_dir).glob(f"page-{page_no}.png"))
             + list(Path(pages_dir).glob(f"page-{page_no:02d}.png"))
             + list(Path(pages_dir).glob(f"page-{page_no:03d}.png")))
    if not cands:
        return False
    try:
        with Image.open(cands[0]) as im:
            W, H = im.size
            x, y, w, h = bbox
            box = (int(max(0.0, x - pad) * W), int(max(0.0, y - pad) * H),
                   int(min(1.0, x + w + pad) * W), int(min(1.0, y + h + pad) * H))
            if box[2] - box[0] < 8 or box[3] - box[1] < 8:
                return False
            im.crop(box).save(out_path)
        return True
    except Exception:
        return False


def _recrop_inplace(pdf_path, out_dir):
    """Replace MinerU's extracted figures, in reading order, with hi-res crops re-cut from the 300dpi full page (overwriting the same-named file in place).

    Reads mineru_raw.json (v2: list[page][block]) and layout.json, renders full pages to out_dir/pages/,
    walks each v2 page's blocks, and on an image/chart (or table figure) pops one bbox in order from the
    corresponding pools[kind][page_idx] (consumed counter). The figure's file name comes from that block's
    content.image_source.path basename, and the hi-res crop **overwrites whatever file that basename actually lives in**
    (extract_with_mineru routes by whether the file name contains "table" into figures/ or tables/, but MinerU v2 figure names
    are content hashes with no "table" in them → table figures actually land in figures/ too; so the overwrite location follows
    where the basename actually is, not an assumption from the block type). If no bbox matches / the crop fails, the original is kept; skipped if there is no layout or pdftoppm is unavailable.
    """
    from pathlib import Path

    out_dir = Path(out_dir)
    raw_path = out_dir / "mineru_raw.json"
    if not raw_path.exists():
        return
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(raw, list):
        return  # re-crop only supports the v2 list[page][block] shape

    layout = _load_layout(out_dir)
    if layout is None:
        print("  [recrop] no layout.json; skipping hi-res re-crop (keeping MinerU's extracted figures)")
        return

    pages_dir = out_dir / "pages"
    if not _render_pages(Path(pdf_path), pages_dir):
        print("  [recrop] pdftoppm unavailable; skipping hi-res re-crop (keeping MinerU's extracted figures)")
        return

    figures_dir = out_dir / "figures"
    tables_dir = out_dir / "tables"
    pools = _bbox_pools(layout)
    consumed = {}
    n_ok = 0
    n_try = 0

    for page_idx, page in enumerate(raw):
        if not isinstance(page, list):
            continue
        for blk in page:
            if not isinstance(blk, dict):
                continue
            kind = blk.get("type")
            if kind not in ("image", "chart", "table"):
                continue
            content = blk.get("content") if isinstance(blk.get("content"), dict) else {}
            source = content.get("image_source") or {}
            path = source.get("path") if isinstance(source, dict) else None
            if not path:
                continue
            basename = os.path.basename(path)
            # The overwrite location follows where the basename actually lands: extract_with_mineru routes by
            # whether the file name contains "table", but MinerU v2 figure names are hashes → table figures usually live in figures/ too. Check both and overwrite at the real location.
            dest = None
            for d in (figures_dir, tables_dir):
                if (d / basename).exists():
                    dest = d / basename
                    break
            if dest is None:
                continue  # the extracted figure never landed (e.g. skipped earlier by the <noise> logic); don't force a crop

            n_try += 1
            avail = pools.get(kind, {}).get(page_idx, [])
            i = consumed.get((kind, page_idx), 0)
            if i >= len(avail):
                continue  # this page's bboxes of this kind are exhausted / not given by layout; keep the original
            consumed[(kind, page_idx)] = i + 1
            if _crop_from_page(pages_dir, page_idx + 1,
                               _norm_bbox(avail[i], layout, page_idx), dest):
                n_ok += 1

    print(f"  [recrop] hi-res re-crop overwrote {n_ok}/{n_try} figures (300dpi full page + layout bbox)")


# ================================================================
# Metadata extraction
# ================================================================

def extract_metadata(md_text: str) -> dict:
    """Extract title, authors, abstract from markdown text."""
    lines = md_text.strip().split("\n")

    metadata = {
        "title": "",
        "authors": "",
        "affiliations": "",
        "abstract": "",
    }

    # Heuristic: first non-empty line is title
    for line in lines:
        line = line.strip().lstrip("#").strip()
        if line and len(line) > 5:
            metadata["title"] = line
            break

    # Look for abstract
    abstract_match = re.search(
        r"(?i)(?:^|\n)#+?\s*abstract\s*\n(.*?)(?=\n#+?\s|\n\n\n|\Z)",
        md_text,
        re.DOTALL,
    )
    if abstract_match:
        metadata["abstract"] = abstract_match.group(1).strip()[:1000]
    else:
        abs_idx = md_text.lower().find("abstract")
        if abs_idx != -1:
            chunk = md_text[abs_idx : abs_idx + 1500]
            end = re.search(r"\n#{1,3}\s", chunk[50:])
            if end:
                metadata["abstract"] = chunk[: 50 + end.start()].strip()
            else:
                metadata["abstract"] = chunk[:1000].strip()

    return metadata


# ================================================================
# Main
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Parse academic PDF via MinerU Cloud API")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--token", default=None, help="MinerU API token (or set MINERU_API_TOKEN env var)")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf_path):
        print(f"ERROR: File not found: {args.pdf_path}")
        sys.exit(1)

    if args.token:
        os.environ["MINERU_API_TOKEN"] = args.token

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, "figures"), exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, "tables"), exist_ok=True)

    print("Parsing with MinerU Cloud API...")
    try:
        md_text = extract_with_mineru(args.pdf_path, args.output_dir)
    except Exception as e:
        print(f"ERROR: MinerU parsing failed: {e}")
        sys.exit(1)

    if not md_text or len(md_text.strip()) < 100:
        print("ERROR: MinerU returned insufficient content.")
        sys.exit(1)

    # Extract and save metadata
    metadata = extract_metadata(md_text)
    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Count figures
    figures_dir = os.path.join(args.output_dir, "figures")
    fig_count = len([f for f in os.listdir(figures_dir) if f.endswith((".png", ".jpg", ".jpeg"))])

    print(f"Done!")
    print(f"  Content: {args.output_dir}/content.md ({len(md_text)} chars)")
    print(f"  Metadata: {args.output_dir}/metadata.json")
    print(f"  Figures: {fig_count} images extracted")


if __name__ == "__main__":
    main()
