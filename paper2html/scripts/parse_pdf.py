#!/usr/bin/env python
"""parse_pdf —— 解析 + 确定性抽取（机械，闸门1）。

PDF → MinerU 解析 → normalize → extract_manifest（title/authors/abstract/links/claims/
figures/tables/method/bibtex，附录过滤，抽不到留空交你兜底）→ 复制页面图。

产物（落在 --workdir，即 <pdf目录>/.paper2anything/html/）：
  clean.md       normalize 后的 markdown（你通读全文用）
  manifest.json  确定性抽取的事实（你创作只能用这里的真实素材）
  parsed/        MinerU 原始解析（含 full.md 供重跑复用、images/ 所有裁图）
  images/        页面引用的图（你以 images/<name> 引用，与 index.html 同级）
  logs/parse_pdf_result.json

用法：
  python parse_pdf.py <paper.pdf> --workdir <.paper2anything/html> [--paper-url URL] [--code-url URL] [--lite]
"""
import argparse
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: F401  统一加载包根 .env
from utils import (
    resolve_workspace, save_json, save_stage_result, print_stage_header,
    print_info, print_success, print_warning, print_error,
)
from lib import core


def run(input_path: str, workdir: str, *, paper_url=None, code_url=None,
        use_lite: bool = False, copy_images: bool = True) -> dict:
    print_stage_header("MinerU 解析 + 确定性抽取（闸门1）")
    ws = resolve_workspace(workdir)
    root = ws["root"]

    source = Path(input_path).expanduser().resolve()
    if not source.exists():
        print_error(f"输入不存在: {source}")
        return {"status": "failed", "error": f"输入不存在: {source}"}

    # 解析（PDF 走 MinerU；MD 直接读）。reuse_parsed=True：parsed/full.md 在则跳过云端解析。
    print_info(f"解析输入: {source.name}")
    raw_markdown, parsed_images, parsed_dir = core._load_or_parse_source(
        source, root, use_lite=use_lite, reuse_parsed=True
    )
    # 写 full.md 供重跑复用（不依赖外部流程产出）
    if parsed_dir is not None:
        Path(parsed_dir).mkdir(parents=True, exist_ok=True)
        (Path(parsed_dir) / "full.md").write_text(raw_markdown, encoding="utf-8")

    # 高清重裁：MinerU 抽出图是降采样的（偏糊）。在拷图到 images/ 前，按 layout.json 的 bbox
    # 从 pdftoppm 300dpi 整页里重裁、原地覆盖 parsed/ 下被引用的源图（不改文件名/manifest）。
    # 仅 PDF 输入且有 parsed_dir 时执行；MD 输入（无 PDF）则跳过。
    if parsed_dir is not None and source.suffix.lower() == ".pdf":
        core._recrop_inplace(source, Path(parsed_dir))

    markdown = core.normalize_markdown(raw_markdown)
    (root / "clean.md").write_text(markdown, encoding="utf-8")
    print_success(f"clean.md 已写（{len(markdown)} 字符）")

    # 确定性抽取（闸门1）
    image_roots = core._candidate_image_roots(source, root, None)
    manifest = core.extract_manifest(
        markdown, source=source, image_roots=image_roots,
        paper_url=paper_url, code_url=code_url, parsed_dir=parsed_dir,
    )

    # 复制页面引用的图到 root/images/，使你写的 images/<name> 能解析、QA 不报缺图
    copied = set()
    if copy_images:
        copied = core.copy_manifest_images(manifest, root, image_roots, parsed_images)
        for fig in manifest.figures:
            fig.exists = fig.file in copied or (root / fig.file).exists()

    save_json(asdict(manifest), root / "manifest.json")

    # ── 摘要（抽不到的字段留空，交你在创作阶段兜底，不报错）──
    print_success(f"论文标题: {manifest.title}")
    if not manifest.abstract:
        print_warning("未抽到摘要（论文可能无 Abstract 标题）；留空交给你兜底")
    if not manifest.authors:
        print_warning("未抽到作者（确定性抽取局限）；留空交给你兜底")
    if not manifest.links.paper:
        print_info("未自动确定论文链接（不假设 arxiv）；如需可重跑加 --paper-url")
    print_info(f"作者 {len(manifest.authors)} | 摘要 {len(manifest.abstract)} 字 | "
               f"图 {len(manifest.figures)} | 表 {len(manifest.tables)} | claims {len(manifest.claims)}")
    print_info(f"已复制页面图 {len(copied)} 张 → {root / 'images'}")
    print_info(f"PIR 已保存至: {root}")

    result = {
        "status": "success",
        "workdir": str(root),
        "clean_md": str(root / "clean.md"),
        "manifest": str(root / "manifest.json"),
        "title": manifest.title,
        "counts": {
            "authors": len(manifest.authors),
            "abstract_chars": len(manifest.abstract),
            "figures": len(manifest.figures),
            "tables": len(manifest.tables),
            "claims": len(manifest.claims),
            "images_copied": len(copied),
        },
        "links": asdict(manifest.links),
    }
    save_stage_result(result, "parse_pdf", ws)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="paper2html parse_pdf: 解析 + 确定性抽取")
    ap.add_argument("input", help="论文 PDF（或已解析的 Markdown）")
    ap.add_argument("--workdir", required=True, help="工作目录（<pdf目录>/.paper2anything/html）")
    ap.add_argument("--paper-url", default=None, help="论文规范链接（不传则留空，不假设 arxiv）")
    ap.add_argument("--code-url", default=None, help="代码仓库链接覆盖")
    ap.add_argument("--lite", action="store_true", help="用 MinerU 轻量解析 API")
    ap.add_argument("--no-copy-images", action="store_true", help="不复制图到 images/")
    args = ap.parse_args()

    result = run(
        args.input, args.workdir,
        paper_url=args.paper_url, code_url=args.code_url,
        use_lite=args.lite, copy_images=not args.no_copy_images,
    )
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
