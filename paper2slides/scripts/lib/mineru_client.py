"""
mineru_client.py — MinerU 云 API 客户端

仅 HTTP/IO 与 ZIP 处理，**不**触碰 paper2slides 的 schema 转换（那是 mineru_parser 的事）。

API 端点（v4）：
  POST /api/v4/extract/task                      创建解析任务（URL 模式）
  POST /api/v4/file-urls/batch                   申请 OSS 上传 URL（本地文件模式）
  GET  /api/v4/extract/task/{task_id}            轮询任务状态
  下载 full_zip_url                               拿结果

设计要点：
  - SSL 坑：CDN 域 cdn-mineru.openxlab.org.cn 经过本地 mihomo 代理触发 SSL EOF
    （把 .cn 走出境会触发 SNI 探测）。download_zip 内部 session.proxies={"http":None,
    "https":None} + trust_env=False，强制无代理直连
  - Token 通过参数显式传入（调用方读 MINERU_API_TOKEN env）；本模块只读可选的
    MINERU_API_BASE（端点根，默认 https://mineru.net，与 html/poster 统一），不读 token

CLI（调试用）：
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

# 提交/轮询强制无代理直连（与下方 download_zip 的 _no_proxy_session 同配置）：env 挂
# ALL_PROXY=socks5h 时上传 OSS 会报 SOCKS 失败；trust_env=False 才能真正压住 all_proxy
# （proxies={"http":None} 会被 merge 剥掉）。
_SESSION = requests.Session()
_SESSION.trust_env = False
_SESSION.proxies = {"http": None, "https": None}


# --------------------------------------------------------------------------- #
# 提交任务
# --------------------------------------------------------------------------- #


def submit_url_task(pdf_url: str, token: str, *,
                    model_version: str = "vlm",
                    enable_table: bool = True,
                    enable_formula: bool = True) -> str:
    """以公网 URL 模式提交解析任务，返回 task_id。"""
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
    """走 file-urls/batch：拿 OSS upload URL → PUT 文件 → 用返回的 file_url 提交任务。"""
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    # 1) 申请上传 URL（batch 接口，单文件场景就一个）
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

    # 2) PUT 上传文件到签名 URL（24h 有效）。**不要**带 Authorization header（OSS 会拒）
    with open(pdf_path, "rb") as f:
        put_resp = _SESSION.put(upload_url, data=f, timeout=120)
    put_resp.raise_for_status()

    # 3) 用 batch_id 拿到的任务，已与文件绑定，状态可直接通过 batch 查
    #    返回 batch_id 当作 task_id 使用 —— v4 batch 接口的设计就是 batch_id 等价 task_id
    return batch_id


# --------------------------------------------------------------------------- #
# 轮询
# --------------------------------------------------------------------------- #


def poll_task(task_id: str, token: str, *,
              timeout_s: int = DEFAULT_TIMEOUT_S,
              interval_s: int = DEFAULT_INTERVAL_S) -> dict:
    """轮询直到 state=done|failed 或超时。返回最后一次 data 字典。"""
    deadline = time.time() + timeout_s
    last_state = "(not seen)"
    last_data: dict = {}
    # batch_id 与单文件 task_id 端点不同：
    #   - 直接 submit_url_task 拿到的 task_id 用 /extract/task/{id}
    #   - file-urls/batch 拿到的 batch_id 用 /extract-results/batch/{id}
    # 我们尝试 batch 端点，失败回退普通端点
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
            # batch 端点返回 extract_result[]，单文件返回 {state, full_zip_url}
            if "extract_result" in payload:
                results = payload["extract_result"] or []
                if not results:
                    last_state = "running"
                    last_data = payload
                    break
                # 单文件 batch：取第一个
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
# 下载 ZIP & 解压
# --------------------------------------------------------------------------- #


def _no_proxy_session() -> requests.Session:
    """绕过本地代理（mihomo 等），强制直连 mineru CDN。"""
    s = requests.Session()
    s.trust_env = False
    s.proxies = {"http": None, "https": None}
    return s


def download_zip(zip_url: str, *, max_retries: int = 3) -> bytes:
    """下载 ZIP 内容（指数退避重试）。"""
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
    """解压到 dest_dir，返回 dest_dir。"""
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(dest_dir)
    return dest_dir


# --------------------------------------------------------------------------- #
# CLI（仅调试用）
# --------------------------------------------------------------------------- #


def _token_from_env() -> str:
    tok = os.environ.get("MINERU_API_TOKEN", "").strip()
    if not tok:
        raise SystemExit("MINERU_API_TOKEN env var is empty")
    return tok


def main() -> None:
    p = argparse.ArgumentParser(description="MinerU API client (debug CLI)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_submit = sub.add_parser("submit", help="提交本地 PDF，打印 task_id")
    s_submit.add_argument("pdf", type=Path)

    s_poll = sub.add_parser("poll", help="轮询任务，打印最终 JSON")
    s_poll.add_argument("task_id")
    s_poll.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)

    s_dl = sub.add_parser("download", help="下载 ZIP 并解压")
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
