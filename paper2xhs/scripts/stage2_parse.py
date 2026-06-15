"""
Stage 2 — MinerU 解析（云端 API 版）
通过 https://mineru.net/api/v4 调用 MinerU SaaS：
  1. POST /file-urls/batch → 拿到 PUT 上传 URL + batch_id
  2. PUT 本地 PDF 到上传 URL
  3. 轮询 GET /extract-results/batch/{batch_id} 直到 state=done
  4. 下载 full_zip_url 并解压得到 *_content_list.json / 图片 等
输出：paper_meta.json, sections.json, figures_index.json, references.json
"""

import io
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path

import requests

from utils import (
    load_json,
    logger,
    print_error,
    print_info,
    print_stage_header,
    print_success,
    print_warning,
    save_json,
    save_stage_result,
)


MINERU_API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net/api/v4")
MINERU_POLL_INTERVAL = 5
MINERU_POLL_TIMEOUT = 600  # 10 分钟


def _mineru_headers() -> dict:
    token = os.environ.get("MINERU_API_TOKEN")
    if not token:
        raise RuntimeError("未设置 MINERU_API_TOKEN 环境变量（请在 .env 中填入）")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def _request_upload_url(pdf_name: str, model_version: str = "vlm") -> tuple[str, str]:
    """请求一个 PUT 上传 URL，返回 (batch_id, upload_url)"""
    url = f"{MINERU_API_BASE}/file-urls/batch"
    payload = {
        "files": [{"name": pdf_name}],
        "model_version": model_version,
    }
    r = requests.post(url, headers=_mineru_headers(), json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    if body.get("code") not in (0, 200):
        raise RuntimeError(f"MinerU file-urls/batch 返回错误: {body}")
    data = body["data"]
    batch_id = data["batch_id"]
    file_urls = data.get("file_urls") or []
    if not file_urls:
        raise RuntimeError(f"MinerU 未返回上传 URL: {body}")
    return batch_id, file_urls[0]


def _upload_pdf(upload_url: str, pdf_path: Path) -> None:
    """PUT 上传 PDF 到预签名地址。注意：不要带 Authorization 头。"""
    with open(pdf_path, "rb") as f:
        r = requests.put(upload_url, data=f, timeout=300)
    r.raise_for_status()


def _poll_batch(batch_id: str) -> dict:
    """轮询批次状态直到 done/failed/超时；返回该文件的结果对象"""
    url = f"{MINERU_API_BASE}/extract-results/batch/{batch_id}"
    headers = {"Authorization": _mineru_headers()["Authorization"]}
    deadline = time.time() + MINERU_POLL_TIMEOUT
    last_state = None
    while time.time() < deadline:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        if body.get("code") not in (0, 200):
            raise RuntimeError(f"MinerU 查询失败: {body}")
        # data 中通常含 extract_result 列表
        data = body.get("data") or {}
        results = data.get("extract_result") or data.get("results") or []
        if not results:
            time.sleep(MINERU_POLL_INTERVAL)
            continue
        item = results[0]
        state = item.get("state")
        if state != last_state:
            print_info(f"MinerU 任务状态: {state}")
            last_state = state
        if state == "done":
            return item
        if state == "failed":
            raise RuntimeError(f"MinerU 解析失败: {item.get('err_msg') or item}")
        time.sleep(MINERU_POLL_INTERVAL)
    raise RuntimeError(f"MinerU 轮询超时（{MINERU_POLL_TIMEOUT}s）")


def _download_and_unzip(zip_url: str, output_dir: Path) -> None:
    """下载结果 zip 并解压到 output_dir"""
    r = requests.get(zip_url, timeout=300)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        zf.extractall(output_dir)


def _run_mineru(pdf_path: Path, output_dir: Path) -> bool:
    """通过 MinerU 云端 API 解析 PDF，结果解压到 output_dir。失败返回 False。"""
    try:
        print_info(f"请求 MinerU 上传 URL（{pdf_path.name}）...")
        batch_id, upload_url = _request_upload_url(pdf_path.name)
        print_info(f"上传 PDF（batch_id={batch_id}）...")
        _upload_pdf(upload_url, pdf_path)
        print_info("轮询解析任务...")
        result = _poll_batch(batch_id)
        zip_url = result.get("full_zip_url")
        if not zip_url:
            print_error(f"MinerU 完成但未返回 full_zip_url: {result}")
            return False
        print_info("下载并解压结果...")
        _download_and_unzip(zip_url, output_dir)
        return True
    except Exception as e:
        logger.exception("MinerU API 调用失败")
        print_error(f"MinerU API 调用失败: {e}")
        return False


def _find_mineru_output(output_dir: Path, pdf_stem: str) -> Path | None:
    """找到 MinerU 实际输出目录"""
    candidates = [
        output_dir / pdf_stem / "auto",
        output_dir / pdf_stem,
        output_dir,
    ]
    for c in candidates:
        if c.exists():
            try:
                if any(c.iterdir()):
                    return c
            except StopIteration:
                pass
    return None


def _parse_content_list(content_list_path: Path) -> tuple:
    """解析 MinerU content_list.json → (meta, sections, figures, references)"""
    with open(content_list_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    meta = {"title": "", "authors": [], "abstract": "", "keywords": []}
    sections = []
    figures = []
    references = []

    current_section = None
    current_lines = []
    in_abstract = False
    in_references = False
    title_found = False

    def flush_section():
        nonlocal current_section, current_lines
        if current_section is not None:
            sections.append({
                "title": current_section,
                "content": "\n".join(current_lines).strip(),
            })
        current_section = None
        current_lines = []

    for item in items:
        itype = item.get("type", "")
        text = item.get("text", "").strip()
        page = item.get("page_idx", 0) + 1
        is_heading = (itype == "title") or (itype == "text" and item.get("text_level") == 1)

        if is_heading:
            if not title_found and len(text) > 5:
                meta["title"] = text
                title_found = True
            else:
                flush_section()
                current_section = text
                in_abstract = text.lower() in ("abstract", "摘要")
                in_references = text.lower() in ("references", "参考文献", "bibliography")

        elif itype == "text":
            if in_abstract and not meta["abstract"]:
                meta["abstract"] = text
            elif in_references:
                references.append(text)
            elif current_section is not None:
                current_lines.append(text)
            elif not meta["authors"] and title_found and len(text) < 300:
                meta["authors"] = [a.strip() for a in re.split(r"[,;，；\n]", text) if a.strip()]

        elif itype == "image":
            img_path = item.get("img_path", "")
            captions = item.get("img_caption", [])
            caption = captions[0] if captions else ""
            if img_path:
                figures.append({
                    "figure_id": f"fig_{len(figures) + 1}",
                    "caption": caption,
                    "image_path": img_path,
                    "page": page,
                })

    flush_section()
    return meta, sections, figures, references


def _parse_markdown(md_path: Path) -> tuple:
    """备用：解析 MinerU Markdown → (meta, sections, figures)"""
    text = md_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    meta = {"title": "", "authors": [], "abstract": "", "keywords": []}
    sections = []
    figures = []

    current_section = None
    current_lines = []
    title_found = False
    in_abstract = False

    def flush():
        if current_section is not None:
            sections.append({
                "title": current_section,
                "content": "\n".join(current_lines).strip(),
            })

    for line in lines:
        s = line.strip()
        if s.startswith("# ") and not title_found:
            meta["title"] = s[2:].strip()
            title_found = True
        elif s.startswith("## "):
            flush()
            current_section = s[3:].strip()
            current_lines = []
            in_abstract = current_section.lower() in ("abstract", "摘要")
        elif s.startswith("### "):
            current_lines.append(s)
        else:
            img_m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", s)
            if img_m:
                figures.append({
                    "figure_id": f"fig_{len(figures) + 1}",
                    "caption": img_m.group(1),
                    "image_path": img_m.group(2),
                    "page": 0,
                })
            elif in_abstract and not meta["abstract"] and s:
                meta["abstract"] = s
            elif current_section and s:
                current_lines.append(s)

    flush()
    return meta, sections, figures


def _copy_figures(mineru_out: Path, figures_dir: Path, figures_index: list) -> list:
    """将图片复制到工作区 figures/ 目录，更新路径"""
    updated = []
    for fig in figures_index:
        src = Path(fig["image_path"])
        if not src.is_absolute():
            src = mineru_out / src
        if src.exists():
            dest = figures_dir / src.name
            shutil.copy2(src, dest)
            fig = dict(fig)
            fig["image_path"] = str(dest)
        updated.append(fig)
    return updated


def _copy_pages(mineru_out: Path, pages_dir: Path) -> None:
    """将页面图片复制到工作区 pages/ 目录"""
    for img in sorted(mineru_out.glob("*.png")):
        shutil.copy2(img, pages_dir / img.name)
    # MinerU 有时将页面图放在 images/ 子目录
    images_sub = mineru_out / "images"
    if images_sub.exists():
        for img in sorted(images_sub.glob("*.png")):
            shutil.copy2(img, pages_dir / img.name)


def _validate(meta: dict, sections: list) -> dict:
    """验证解析结果"""
    checks = {
        "title": bool(meta.get("title")),
        "abstract": bool(meta.get("abstract")),
        "sections": len(sections) > 0,
        "sections_have_content": any(s.get("content") for s in sections),
    }
    return checks


def run(task_id: str, workspace: dict, base_dir: str = "workspace") -> dict:
    """
    执行 Stage 2：MinerU 解析

    输入：workspace["raw"]/paper.pdf
    输出：workspace["parsed"]/ 下的 PIR 文件
    """
    print_stage_header(2, "MinerU 解析")

    pdf_path = workspace["raw"] / "paper.pdf"
    parsed_dir = workspace["parsed"]
    figures_dir = workspace["figures"]
    pages_dir = workspace["pages"]

    if not pdf_path.exists():
        print_error(f"PDF 不存在: {pdf_path}")
        return {"status": "failed", "error": "PDF 文件不存在"}

    # ── 调用 MinerU ──
    mineru_tmp = workspace["root"] / "_mineru_tmp"
    mineru_tmp.mkdir(exist_ok=True)

    success = _run_mineru(pdf_path, mineru_tmp)
    if not success:
        print_warning("MinerU 调用失败，尝试备用解析方案...")

    # ── 找到输出目录 ──
    pdf_stem = pdf_path.stem
    mineru_out = _find_mineru_output(mineru_tmp, pdf_stem)

    meta = {"title": "", "authors": [], "abstract": "", "keywords": []}
    sections = []
    figures = []
    references = []

    if mineru_out:
        # 优先使用 content_list.json
        content_list_path = mineru_out / f"{pdf_stem}_content_list.json"
        if not content_list_path.exists():
            # 尝试其他命名
            candidates = list(mineru_out.glob("*content_list*.json"))
            content_list_path = candidates[0] if candidates else None

        if content_list_path and content_list_path.exists():
            print_info("使用 content_list.json 解析")
            meta, sections, figures, references = _parse_content_list(content_list_path)
        else:
            # 备用：使用 Markdown
            md_candidates = list(mineru_out.glob("*.md"))
            if md_candidates:
                print_info(f"使用 Markdown 备用解析: {md_candidates[0].name}")
                meta, sections, figures = _parse_markdown(md_candidates[0])
            else:
                print_error("MinerU 输出中未找到可解析文件")
                return {"status": "failed", "error": "MinerU 输出无法解析"}

        # 复制图片和页面
        figures = _copy_figures(mineru_out, figures_dir, figures)
        _copy_pages(mineru_out, pages_dir)
    else:
        print_error("MinerU 未生成输出目录")
        return {"status": "failed", "error": "MinerU 未生成输出"}

    # ── 验证 ──
    checks = _validate(meta, sections)
    if not checks["title"] or not checks["abstract"] or not checks["sections"]:
        print_error("解析验证失败")
        for k, v in checks.items():
            status = "[green]✓[/green]" if v else "[red]✗[/red]"
            print_info(f"  {status} {k}")
        return {
            "status": "failed",
            "error": "解析验证失败",
            "validation": checks,
        }

    # ── 保存 PIR ──
    save_json(meta, parsed_dir / "paper_meta.json")
    save_json(sections, parsed_dir / "sections.json")
    save_json(figures, parsed_dir / "figures_index.json")
    save_json(references, parsed_dir / "references.json")

    print_success(f"论文标题: {meta['title'][:80]}")
    print_success(f"章节数量: {len(sections)}")
    print_success(f"图片数量: {len(figures)}")
    print_info(f"PIR 已保存至: {parsed_dir}")

    result = {
        "status": "success",
        "parsed_dir": str(parsed_dir),
        "validation": checks,
        "stats": {
            "sections": len(sections),
            "figures": len(figures),
            "references": len(references),
        },
    }
    save_stage_result(result, "stage2_parse", workspace)
    return result
