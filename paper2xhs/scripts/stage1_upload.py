"""
Stage 1 — PDF 上传验证
接收本地 PDF 文件，验证有效性，复制到工作区
"""

import shutil
from pathlib import Path

from utils import (
    create_workspace,
    generate_task_id,
    logger,
    print_error,
    print_info,
    print_stage_header,
    print_success,
    save_json,
    save_stage_result,
)


def run(pdf_path: str, base_dir: str = "workspace") -> dict:
    """
    执行 Stage 1：PDF 上传验证

    输入：本地 PDF 文件路径
    输出：{status, pdf_path, task_id}
    """
    print_stage_header(1, "PDF 上传验证")

    pdf = Path(pdf_path).resolve()

    # 验证文件存在
    if not pdf.exists():
        print_error(f"文件不存在: {pdf}")
        return {"status": "failed", "error": "文件不存在", "pdf_path": str(pdf)}

    # 验证扩展名
    if pdf.suffix.lower() != ".pdf":
        print_error(f"文件不是 PDF 格式: {pdf.suffix}")
        return {"status": "failed", "error": "文件不是 PDF 格式", "pdf_path": str(pdf)}

    # 验证文件可读
    try:
        with open(pdf, "rb") as f:
            header = f.read(5)
        if header != b"%PDF-":
            print_error("文件不是有效的 PDF（文件头校验失败）")
            return {"status": "failed", "error": "无效的 PDF 文件头", "pdf_path": str(pdf)}
    except OSError as e:
        print_error(f"文件无法读取: {e}")
        return {"status": "failed", "error": str(e), "pdf_path": str(pdf)}

    # 生成任务 ID，创建工作区
    task_id = generate_task_id()
    workspace = create_workspace(task_id, base_dir)

    # 复制 PDF 到工作区
    dest = workspace["raw"] / "paper.pdf"
    shutil.copy2(pdf, dest)

    file_size_mb = dest.stat().st_size / (1024 * 1024)
    print_success(f"PDF 验证通过: {pdf.name} ({file_size_mb:.2f} MB)")
    print_info(f"任务 ID: {task_id}")
    print_info(f"工作区: {workspace['root']}")

    result = {
        "status": "success",
        "pdf_path": str(dest),
        "task_id": task_id,
        "workspace_root": str(workspace["root"]),
        "file_size_mb": round(file_size_mb, 2),
        "original_filename": pdf.name,
    }

    save_json(result, workspace["raw"] / "upload_info.json")
    save_stage_result(result, "stage1_upload", workspace)

    return result
