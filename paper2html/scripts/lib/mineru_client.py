"""MinerU API client for PDF parsing."""

import time
import zipfile
import requests
from pathlib import Path

from .config import (
    MINERU_API_BASE,
    MINERU_API_TOKEN,
    ENABLE_TABLE,
    ENABLE_FORMULA,
    IS_OCR,
    LANGUAGE,
)

# 强制无代理直连 mineru.net / 阿里云 OSS。env 里的 ALL_PROXY=socks5h 会让 requests 走
# SOCKS（无 pysocks 即报 "Missing dependencies for SOCKS support"）；而 proxies={"http":None}
# 会被 requests 的 merge_setting 当作 None 键剥掉、压不住 all_proxy —— 必须 trust_env=False。
_session = requests.Session()
_session.trust_env = False
_session.proxies = {"http": None, "https": None}


class MineruClient:
    """Client for MinerU Precision API (v4) - supports local file upload."""

    def __init__(self, token: str = None):
        self.token = token or MINERU_API_TOKEN
        self.base_url = MINERU_API_BASE
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def parse_pdf(self, pdf_path: str, output_dir: str = None) -> dict:
        """
        Parse a PDF file using MinerU API.

        Returns:
            dict with keys: 'markdown' (str), 'images' (dict of name->path)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if output_dir is None:
            output_dir = pdf_path.parent / "parsed_output"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Get presigned upload URL
        batch_id, upload_url = self._get_upload_url(pdf_path.name)
        print(f"[MinerU] Got upload URL, batch_id: {batch_id}")

        # Step 2: Upload file via PUT
        self._upload_file(pdf_path, upload_url)
        print(f"[MinerU] File uploaded successfully.")

        # Step 3: Poll for completion (system auto-submits after upload)
        zip_url = self._poll_batch(batch_id)
        print(f"[MinerU] Parsing complete.")

        # Step 4: Download and extract results
        result = self._download_result(zip_url, output_dir)
        return result

    def _get_upload_url(self, filename: str) -> tuple:
        """Request presigned upload URL via batch endpoint."""
        url = f"{self.base_url}/api/v4/file-urls/batch"

        payload = {
            "files": [{"name": filename, "data_id": "paper_0"}],
            "model_version": "vlm",
            "enable_table": ENABLE_TABLE,
            "enable_formula": ENABLE_FORMULA,
            "is_ocr": IS_OCR,
            "language": LANGUAGE,
        }

        resp = _session.post(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        result = resp.json()

        if result.get("code") != 0:
            raise RuntimeError(f"MinerU API error: {result.get('msg', result)}")

        batch_id = result["data"]["batch_id"]
        upload_url = result["data"]["file_urls"][0]
        return batch_id, upload_url

    def _upload_file(self, pdf_path: Path, upload_url: str):
        """Upload local file to presigned URL via PUT."""
        with open(pdf_path, "rb") as f:
            resp = _session.put(upload_url, data=f)
        resp.raise_for_status()

    def _poll_batch(self, batch_id: str, timeout: int = 600, interval: int = 5) -> str:
        """Poll batch results until done. Returns ZIP download URL."""
        url = f"{self.base_url}/api/v4/extract-results/batch/{batch_id}"
        start = time.time()

        while time.time() - start < timeout:
            resp = _session.get(url, headers=self.headers)
            resp.raise_for_status()
            result = resp.json()

            if result.get("code") != 0:
                raise RuntimeError(f"MinerU API error: {result.get('msg', result)}")

            extract_results = result["data"]["extract_result"]
            if not extract_results:
                print(f"[MinerU] Waiting for task to start...")
                time.sleep(interval)
                continue

            task = extract_results[0]
            state = task["state"]

            if state == "done":
                return task["full_zip_url"]
            elif state == "failed":
                raise RuntimeError(f"MinerU parsing failed: {task}")

            print(f"[MinerU] Status: {state}, waiting...")
            time.sleep(interval)

        raise TimeoutError(f"MinerU batch {batch_id} timed out after {timeout}s")

    def _download_result(self, zip_url: str, output_dir: Path) -> dict:
        """Download and extract the result ZIP file（.cn CDN 偶发 SSL EOF，指数退避重试）."""
        backoff = 2.0
        for attempt in range(1, 4):
            try:
                resp = _session.get(zip_url, timeout=120)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"[MinerU] download failed ({e}); retry in {backoff:.0f}s ({attempt}/3)")
                time.sleep(backoff)
                backoff *= 2

        # Save and extract ZIP
        zip_path = output_dir / "result.zip"
        with open(zip_path, "wb") as f:
            f.write(resp.content)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(output_dir)

        # Find markdown file
        md_files = list(output_dir.rglob("*.md"))
        if not md_files:
            raise RuntimeError("No markdown file found in MinerU output")

        markdown_path = md_files[0]
        markdown_content = markdown_path.read_text(encoding="utf-8")

        # Collect image paths
        images = {}
        for img in output_dir.rglob("*"):
            if img.is_file() and img.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
                images[img.name] = str(img)

        # Clean up zip
        zip_path.unlink()

        return {
            "markdown": markdown_content,
            "images": images,
            "output_dir": str(output_dir),
        }


class MineruClientLite:
    """Fallback: MinerU Agent Lightweight API (no token needed, 10MB/20page limit)."""

    def __init__(self):
        self.base_url = MINERU_API_BASE

    def parse_pdf(self, pdf_path: str, output_dir: str = None) -> dict:
        """Parse PDF using the lightweight agent API."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if output_dir is None:
            output_dir = pdf_path.parent / "parsed_output"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Upload file
        task_id = self._upload_file(pdf_path)
        print(f"[MinerU-Lite] Task submitted: {task_id}")

        # Step 2: Poll for result
        md_url = self._poll_task(task_id)
        print(f"[MinerU-Lite] Parsing complete.")

        # Step 3: Download markdown
        resp = _session.get(md_url)
        resp.raise_for_status()
        markdown_content = resp.text

        md_path = output_dir / f"{pdf_path.stem}.md"
        md_path.write_text(markdown_content, encoding="utf-8")

        return {
            "markdown": markdown_content,
            "images": {},
            "output_dir": str(output_dir),
        }

    def _upload_file(self, pdf_path: Path) -> str:
        """Upload file to lightweight API."""
        url = f"{self.base_url}/api/v1/agent/parse/file"
        with open(pdf_path, "rb") as f:
            files = {"file": (pdf_path.name, f, "application/pdf")}
            resp = _session.post(url, files=files)

        resp.raise_for_status()
        result = resp.json()
        return result["data"]["task_id"]

    def _poll_task(self, task_id: str, timeout: int = 300, interval: int = 5) -> str:
        """Poll until done, return markdown CDN URL."""
        url = f"{self.base_url}/api/v1/agent/parse/{task_id}"
        start = time.time()

        while time.time() - start < timeout:
            resp = _session.get(url)
            resp.raise_for_status()
            result = resp.json()

            state = result["data"]["state"]
            if state == "done":
                return result["data"]["markdown_url"]
            elif state == "failed":
                raise RuntimeError(f"MinerU-Lite parsing failed: {result['data']}")

            print(f"[MinerU-Lite] Status: {state}, waiting...")
            time.sleep(interval)

        raise TimeoutError(f"MinerU-Lite task timed out after {timeout}s")
