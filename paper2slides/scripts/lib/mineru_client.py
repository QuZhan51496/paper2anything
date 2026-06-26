"""
mineru_client.py — MinerU cloud API client

HTTP/IO and ZIP handling only; does **not** touch paper2slides' schema conversion
(that is mineru_parser's job).

API endpoints (v4):
  POST /api/v4/extract/task                      create parse task (URL mode)
  POST /api/v4/file-urls/batch                   request OSS upload URL (local file mode)
  GET  /api/v4/extract/task/{task_id}            poll task status
  download full_zip_url                               get the result

Design notes:
  - SSL pitfall: the CDN domain cdn-mineru.openxlab.org.cn triggers an SSL EOF when routed
    through the local mihomo proxy (sending .cn out of the country triggers SNI probing).
    download_zip internally sets session.proxies={"http":None,
    "https":None} + trust_env=False to force a direct, proxy-free connection
  - The token is passed in explicitly via a parameter (the caller reads the MINERU_API_TOKEN
    env); this module only reads the optional MINERU_API_BASE (endpoint root, default
    https://mineru.net), it does not read the token

CLI (for debugging):
  python -m scripts.lib.mineru_client submit <pdf-path> [--token-from-env]
  python -m scripts.lib.mineru_client poll   <task-id>  [--token-from-env]
  python -m scripts.lib.mineru_client download <zip-url> <dest-dir>
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import requests

API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net")
DEFAULT_TIMEOUT_S = 300
DEFAULT_INTERVAL_S = 5

# Submit/poll force a direct, proxy-free connection (same config as _no_proxy_session in
# download_zip below): when the env has ALL_PROXY=socks5h set, uploading to OSS reports a
# SOCKS failure; only trust_env=False can truly suppress all_proxy
# (proxies={"http":None} gets stripped away by the merge).
_SESSION = requests.Session()
_SESSION.trust_env = False
_SESSION.proxies = {"http": None, "https": None}


# --------------------------------------------------------------------------- #
# Submit task
# --------------------------------------------------------------------------- #


def submit_url_task(pdf_url: str, token: str, *,
                    model_version: str = "vlm",
                    enable_table: bool = True,
                    enable_formula: bool = True) -> str:
    """Submit a parse task in public-URL mode, return the task_id."""
    body = {
        "url": pdf_url,
        "model_version": model_version,
        "enable_table": enable_table,
        "enable_formula": enable_formula,
    }
    r = _SESSION.post(
        f"{API_BASE}/api/v4/extract/task",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        json=body, timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"submit failed: {data}")
    return data["data"]["task_id"]


def submit_local_pdf(pdf_path: Path, token: str, *,
                     model_version: str = "vlm",
                     enable_table: bool = True,
                     enable_formula: bool = True) -> str:
    """Use file-urls/batch: get an OSS upload URL → PUT the file → submit the task with the returned file_url."""
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    # 1) Request an upload URL (batch endpoint; just one in the single-file case)
    batch_body = {
        "files": [{"name": pdf_path.name, "is_ocr": False}],
        "model_version": model_version,
        "enable_table": enable_table,
        "enable_formula": enable_formula,
    }
    r = _SESSION.post(
        f"{API_BASE}/api/v4/file-urls/batch",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        json=batch_body, timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"file-urls/batch failed: {data}")

    batch_id = data["data"]["batch_id"]
    file_urls = data["data"]["file_urls"]
    if not file_urls:
        raise RuntimeError(f"no file_urls returned: {data}")
    upload_url = file_urls[0]

    # 2) PUT the file to the signed URL (valid for 24h). Do **not** include an Authorization header (OSS will reject it)
    with open(pdf_path, "rb") as f:
        put_resp = _SESSION.put(upload_url, data=f, timeout=120)
    put_resp.raise_for_status()

    # 3) The task obtained via batch_id is already bound to the file; its status can be queried directly through batch
    #    Return batch_id to be used as the task_id — the v4 batch endpoint is designed such that batch_id is equivalent to task_id
    return batch_id


# --------------------------------------------------------------------------- #
# Poll
# --------------------------------------------------------------------------- #


def poll_task(task_id: str, token: str, *,
              timeout_s: int = DEFAULT_TIMEOUT_S,
              interval_s: int = DEFAULT_INTERVAL_S) -> dict:
    """Poll until state=done|failed or timeout. Return the last data dict."""
    deadline = time.time() + timeout_s
    last_state = "(not seen)"
    last_data: dict = {}
    # batch_id and single-file task_id use different endpoints:
    #   - a task_id obtained directly from submit_url_task uses /extract/task/{id}
    #   - a batch_id obtained from file-urls/batch uses /extract-results/batch/{id}
    # we try the batch endpoint, falling back to the plain endpoint on failure
    endpoints = [
        f"{API_BASE}/api/v4/extract-results/batch/{task_id}",
        f"{API_BASE}/api/v4/extract/task/{task_id}",
    ]
    while time.time() < deadline:
        for url in endpoints:
            r = _SESSION.get(
                url, headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                continue
            payload = data.get("data", {})
            # the batch endpoint returns extract_result[], single-file returns {state, full_zip_url}
            if "extract_result" in payload:
                results = payload["extract_result"] or []
                if not results:
                    last_state = "running"
                    last_data = payload
                    break
                # single-file batch: take the first one
                first = results[0]
                last_state = first.get("state", "")
                last_data = first
            else:
                last_state = payload.get("state", "")
                last_data = payload
            break
        if last_state in ("done", "failed"):
            return last_data
        time.sleep(interval_s)
    raise TimeoutError(
        f"task {task_id} did not finish in {timeout_s}s "
        f"(last state: {last_state})")


# --------------------------------------------------------------------------- #
# Download ZIP & extract
# --------------------------------------------------------------------------- #


def _no_proxy_session() -> requests.Session:
    """Bypass the local proxy (mihomo etc.), force a direct connection to the mineru CDN."""
    s = requests.Session()
    s.trust_env = False
    s.proxies = {"http": None, "https": None}
    return s


def download_zip(zip_url: str, *, max_retries: int = 3) -> bytes:
    """Download the ZIP content (with exponential-backoff retries)."""
    backoff = 2.0
    last_err: Exception | None = None
    with _no_proxy_session() as s:
        for attempt in range(1, max_retries + 1):
            try:
                r = s.get(zip_url, timeout=120,
                          headers={"User-Agent": "paper2slides/0.1"})
                r.raise_for_status()
                return r.content
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff *= 2
    raise RuntimeError(f"zip download failed after {max_retries} attempts: {last_err}")


def extract_zip(zip_bytes: bytes, dest_dir: Path) -> Path:
    """Extract into dest_dir, return dest_dir."""
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(dest_dir)
    return dest_dir


# --------------------------------------------------------------------------- #
# CLI (debug only)
# --------------------------------------------------------------------------- #


def _token_from_env() -> str:
    tok = os.environ.get("MINERU_API_TOKEN", "").strip()
    if not tok:
        raise SystemExit("MINERU_API_TOKEN env var is empty")
    return tok


def main() -> None:
    p = argparse.ArgumentParser(description="MinerU API client (debug CLI)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_submit = sub.add_parser("submit", help="submit a local PDF, print the task_id")
    s_submit.add_argument("pdf", type=Path)

    s_poll = sub.add_parser("poll", help="poll the task, print the final JSON")
    s_poll.add_argument("task_id")
    s_poll.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)

    s_dl = sub.add_parser("download", help="download the ZIP and extract it")
    s_dl.add_argument("zip_url")
    s_dl.add_argument("dest", type=Path)

    args = p.parse_args()

    if args.cmd == "submit":
        tok = _token_from_env()
        tid = submit_local_pdf(args.pdf, tok)
        print(tid)
    elif args.cmd == "poll":
        tok = _token_from_env()
        result = poll_task(args.task_id, tok, timeout_s=args.timeout)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.cmd == "download":
        zip_bytes = download_zip(args.zip_url)
        path = extract_zip(zip_bytes, args.dest)
        print(path)


if __name__ == "__main__":
    main()
