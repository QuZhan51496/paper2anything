#!/usr/bin/env python
"""stage2_validate —— QA 校验（机械，闸门2）。

你亲手写完 index.html 后跑：校验成品页面（结构错误记 error，内容保真记 warning），
产出报告供你据此修订。不改 HTML、不渲染——只看你写的 index.html + manifest.json。

校验项：
  error  —— 缺 <!DOCTYPE html>/</html>、引用的 images/<x> 文件缺失、空 href="#"
  warning —— 标题/图/表未出现在页面、claims<3、图片重复引用、空 alt 等

产物（落在 --workdir）：
  validation.json   机器可读结果（ok/errors/warnings/checks）
  qa_report.md      人类可读报告
  logs/stage2_validate_result.json

用法：
  python stage2_validate.py --workdir <.paper2anything/html>
"""
import argparse
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: F401  统一加载包根 .env
from utils import (
    resolve_workspace, save_json, load_json, save_stage_result, print_stage_header,
    print_info, print_success, print_warning, print_error,
)
from lib import core


def run(workdir: str) -> dict:
    print_stage_header("QA 校验 index.html（闸门2）")
    ws = resolve_workspace(workdir)
    root = ws["root"]

    index_html = root / "index.html"
    manifest_path = root / "manifest.json"
    if not index_html.exists():
        print_error(f"未找到 {index_html}；请先写好 index.html 再跑 QA")
        return {"status": "failed", "error": "index.html 不存在"}
    if not manifest_path.exists():
        print_error(f"未找到 {manifest_path}；请先跑 stage1_parse")
        return {"status": "failed", "error": "manifest.json 不存在"}

    manifest = core.manifest_from_dict(load_json(manifest_path))
    html = index_html.read_text(encoding="utf-8")

    qa = core.validate_site(html, root, manifest)

    save_json(asdict(qa), root / "validation.json")
    (root / "qa_report.md").write_text(core.render_qa_report(qa, manifest), encoding="utf-8")

    if qa.ok:
        print_success("QA PASS（无结构错误）")
    else:
        print_error(f"QA FAIL：{len(qa.errors)} 个错误")
        for e in qa.errors:
            print_error(f"  ✗ {e}")
    for w in qa.warnings:
        print_warning(f"  ⚠ {w}")
    print_info(f"报告: {root / 'qa_report.md'}")

    result = {
        "status": "success" if qa.ok else "qa_failed",
        "ok": qa.ok,
        "errors": qa.errors,
        "warnings": qa.warnings,
        "checks": qa.checks,
        "validation": str(root / "validation.json"),
        "qa_report": str(root / "qa_report.md"),
    }
    save_stage_result(result, "stage2_validate", ws)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="paper2html stage2: QA 校验 index.html")
    ap.add_argument("--workdir", required=True, help="工作目录（<pdf目录>/.paper2anything/html）")
    args = ap.parse_args()
    result = run(args.workdir)
    # QA FAIL 不算脚本错误（你据报告修后重跑）；仅真正异常返回非零
    return 0 if result.get("status") in {"success", "qa_failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
