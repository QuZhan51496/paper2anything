"""
post_images — 正文配图（可选）

把 understanding.post_figures 选定的论文原图（主图 / 主实验结果）按序复制为
post_images/p1.<原后缀>, p2.…，供发布为多图帖。**原图直出、不做任何加工**。

输入：understanding/paper_understanding.json（post_figures；缺失回退 important_figures 按分前 3）
输出：post_images/p1.png|jpg, p2.…（按 post_figures 顺序，后缀随原图）
"""

import argparse
import shutil
import sys
from pathlib import Path

import _env  # noqa: F401  # 独立运行时兜底加载包根 .env

from utils import (
    load_json,
    print_error,
    print_info,
    print_stage_header,
    print_success,
    print_warning,
    resolve_workspace,
    save_stage_result,
)

MAX_IMAGES_DEFAULT = 8  # 图集含封面上限 18 张，配图给个宽松的软上限


def _select_figures(understanding: dict, max_images: int) -> list[Path] | None:
    """优先 post_figures（你挑好并排序的）；未提供时回退 important_figures 按分前 3。
    post_figures 显式提供但全部无效返回 None（硬错误——静默换成别的图集比报错更糟）。"""
    post_list = understanding.get("post_figures") or []
    figs = []
    for item in post_list:
        p = Path(item.get("image_path", ""))
        if p.exists():
            figs.append(p)
        else:
            print_warning(f"post_figures 里的图不存在，跳过: {p}")
    if post_list and not figs:
        print_error("post_figures 全部无效（image_path 均不存在）——路径须取自 parsed/figures_index.json，修正后重跑")
        return None
    if not figs:
        ranked = sorted(understanding.get("important_figures") or [],
                        key=lambda x: x.get("importance_score", 0), reverse=True)
        figs = [Path(f["image_path"])
                for f in ranked if f.get("image_path") and Path(f["image_path"]).exists()][:3]
        if figs:
            print_info("understanding 无 post_figures，回退 important_figures 按分前 3")
    if len(figs) > max_images:
        print_warning(f"配图 {len(figs)} 张超过上限 {max_images}，截取前 {max_images} 张")
        figs = figs[:max_images]
    return figs


def run(workdir: str, max_images: int = MAX_IMAGES_DEFAULT) -> dict:
    """读 understanding → 按序复制原图 → post_images/p<N>.<后缀>。无可用图 status=skipped（不阻断）。"""
    print_stage_header("生成正文配图")

    workspace = resolve_workspace(workdir)
    understanding_path = workspace["understanding"] / "paper_understanding.json"
    if not understanding_path.exists():
        print_error(f"输入文件不存在: {understanding_path}")
        return {"status": "failed", "error": f"{understanding_path.name} 不存在"}
    understanding = load_json(understanding_path)

    figs = _select_figures(understanding, max_images)
    if figs is None:
        result = {"status": "failed", "error": "post_figures 全部无效（image_path 均不存在）"}
        save_stage_result(result, "post_images", workspace)
        return result
    if not figs:
        print_warning("没有可用的配图来源（post_figures / important_figures 均无有效图），跳过")
        result = {"status": "skipped", "reason": "无可用论文原图"}
        save_stage_result(result, "post_images", workspace)
        return result

    out_dir = workspace["root"] / "post_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("p[0-9]*"):  # 重跑覆盖：先清旧图，避免残留多余的 pN
        if stale.is_file():
            stale.unlink()

    images = []
    for i, src in enumerate(figs, 1):
        dst = out_dir / f"p{i}{src.suffix.lower() or '.png'}"
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            print_warning(f"复制失败（{src.name}）：{e}")
            continue
        images.append(str(dst))
        print_success(f"{dst.name} ← {src.name}")

    if not images:
        result = {"status": "failed", "error": "所有配图复制均失败"}
        save_stage_result(result, "post_images", workspace)
        return result

    print_success(f"配图就绪：{len(images)} 张（{out_dir}）")
    result = {"status": "success", "count": len(images), "images": images}
    save_stage_result(result, "post_images", workspace)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="正文配图·原图直出（协调式机械步骤）")
    parser.add_argument(
        "--workdir", required=True,
        help="工作区目录，约定 <pdf目录>/.paper2anything/xhs/<stem>",
    )
    parser.add_argument("--max", type=int, default=MAX_IMAGES_DEFAULT, help="配图张数上限")
    args = parser.parse_args()
    res = run(args.workdir, args.max)
    # skipped（无可用图）不算失败
    sys.exit(0 if res.get("status") in ("success", "skipped") else 1)
