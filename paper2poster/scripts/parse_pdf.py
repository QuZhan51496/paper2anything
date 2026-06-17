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
import sys
import time
import zipfile
import io

import _env  # noqa: F401  # 统一加载包根 .env（凭据）


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

    # 强制无代理直连 mineru.net / 阿里云 OSS。env 里的 ALL_PROXY=socks5h 会让 requests 走
    # SOCKS（无 pysocks 即报错）；而 proxies={"http":None} 会被 requests 的 merge_setting 当作
    # None 键剥掉、压不住 all_proxy —— 必须用 trust_env=False 的 Session 才真正绕过。
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
    resp = session.get(zip_url, timeout=120)
    resp.raise_for_status()

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
            elif lower.endswith(".json"):
                # Save the structured JSON output too
                json_path = os.path.join(output_dir, "mineru_raw.json")
                with open(json_path, "wb") as f:
                    f.write(zf.read(name))

    return md_text


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
