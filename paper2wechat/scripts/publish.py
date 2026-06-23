"""
publish — 发布到微信公众号草稿箱（封装 md2wechat 2.0.1）

md2wechat 2.0.1 经公众号官方 API 直接把文章上传到「草稿箱」：解析 md → 上传封面与正文图到素材库
→ draft/add 建草稿 → stdout 打印含 media_id 的 JSON，本身不产本地文件。本脚本据此分两路：
  - 有凭据（WECHAT_APPID / WECHAT_APP_SECRET）→ 调 md2wechat 建草稿，解析其 stdout JSON
  - 无凭据 / 指定 --local-only / 上传失败 → 降级：用 md2wechat 自带 converter 本地生成样式化
    HTML（wechat_article.html）供手动粘贴到公众号编辑器

凭据获取：微信开发者平台 developers.weixin.qq.com（AppID / AppSecret）；并把本机出口 IP 加入
「API IP白名单」；草稿接口需认证公众号。详见 SKILL.md「Step 5」与「排错」。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import _env  # noqa: F401  # 兜底加载包根 .env（WECHAT_APPID/APP_SECRET、MD2WECHAT_* 等）

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

# skill 主题词 → md2wechat 的 --style（也接受直接传 md2wechat 原生样式名）
_THEME_TO_STYLE = {
    "default": "academic_gray", "academic": "academic_gray",
    "tech": "tech", "dark": "announcement",
}
_VALID_STYLES = {"academic_gray", "festival", "tech", "announcement"}


def _style_from_theme(theme: str) -> str:
    style = _THEME_TO_STYLE.get(theme, theme)
    return style if style in _VALID_STYLES else "academic_gray"


def _creds_present() -> bool:
    return bool(os.environ.get("WECHAT_APPID") and os.environ.get("WECHAT_APP_SECRET"))


def _get_md2wechat_cmd() -> str:
    custom = os.environ.get("MD2WECHAT_CMD", "").strip()
    return custom or shutil.which("md2wechat") or "md2wechat"


def _md2wechat_available(cmd: str) -> bool:
    try:
        r = subprocess.run([cmd, "--help"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0 or "--markdown" in (r.stdout + r.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _local_html(md_path: Path, html_path: Path, style: str) -> bool:
    """降级：用 md2wechat 自带 converter 离线生成样式化 HTML（不调 API）。"""
    try:
        from skills.md2wechat.scripts.parsers import MarkdownParser
    except ImportError:
        print_warning("无法导入 md2wechat converter，跳过本地 HTML 生成")
        return False
    try:
        pr = MarkdownParser().parse(str(md_path), style=style)
        doc = (
            '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{pr.title}</title>\n</head>\n<body>\n{pr.content}\n</body>\n</html>\n"
        )
        html_path.write_text(doc, encoding="utf-8")
        return True
    except Exception as e:
        print_warning(f"本地生成 HTML 失败：{e}")
        return False


def _extract_json(stdout: str) -> dict | None:
    """从 md2wechat stdout（进度行 + 末尾结果 JSON）里抠出结果 JSON。"""
    m = re.search(r"\{.*\}", stdout, re.DOTALL)  # 进度行不含 {，贪婪取整段结果 JSON
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def _upload_draft(cmd: str, md_path: Path, style: str, title: str,
                  summary: str, cover_path: Path | None) -> dict:
    """调 md2wechat 建草稿。返回 {ok, media_id?, error?, code?, stderr?}。"""
    args = [cmd, "--markdown", str(md_path), "--style", style]
    if title:
        args += ["--title", title[:64]]
    if summary:
        args += ["--summary", summary[:120]]
    has_cover = bool(cover_path and cover_path.exists())
    if has_cover:
        args += ["--cover", str(cover_path.resolve())]
    print_info(f"执行：md2wechat --markdown … --style {style}"
               + (" --cover cover.jpg" if has_cover else ""))
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        return {"ok": False, "error": f"找不到 md2wechat：{cmd}", "code": "NO_CMD"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "md2wechat 执行超时（>180s）", "code": "TIMEOUT"}

    data = _extract_json(r.stdout)
    if data and data.get("success"):
        d = data.get("data", {})
        return {"ok": True, "media_id": d.get("media_id"), "raw": d}
    err = (data or {}).get("error") or (r.stderr or "").strip() or "md2wechat 未返回成功结果"
    code = (data or {}).get("code") or f"exit{r.returncode}"
    return {"ok": False, "error": err, "code": code, "stderr": (r.stderr or "")[:500]}


def _hint_for_error(up: dict) -> None:
    s = f"{up.get('code')} {up.get('error')} {up.get('stderr', '')}".lower()
    if "40164" in s or ("ip" in s and "whitelist" in s):
        print_info("  → IP 白名单：把本机出口 IP 加到 developers.weixin.qq.com 的「API IP白名单」")
    elif "40001" in s or "appsecret" in s:
        print_info("  → AppSecret 无效：核对 / 重置 WECHAT_APP_SECRET（重置后旧的失效）")
    elif "40013" in s or "appid" in s:
        print_info("  → AppID 无效：WECHAT_APPID 应以 wx 开头")
    elif "404" in s:
        print_info("  → 草稿接口不可用：需认证公众号（未认证号无 draft/add 权限）")
    elif "missing_cover" in s or "封面" in s:
        print_info("  → 缺封面：确保 cover.jpg 存在（先跑封面步骤）")


def _guide_draft(media_id: str | None, title: str) -> None:
    print_info("─" * 56)
    print_success("草稿已上传到公众号草稿箱")
    print_info(f"  标题：{title}")
    if media_id:
        print_info(f"  media_id：{media_id}")
    print_info("  下一步：登录 mp.weixin.qq.com → 草稿箱 → 预览确认 → 群发 / 发表")
    print_info("─" * 56)


def _guide_local(html_path: Path, md_path: Path, had_creds: bool) -> None:
    print_info("─" * 56)
    if html_path.exists():
        print_success(f"已生成样式化 HTML：{html_path}")
        print_info("  打开它、全选复制，粘贴到公众号编辑器（mp.weixin.qq.com → 新建图文）")
    print_info(f"  Markdown 原文：{md_path}")
    if not had_creds:
        print_info("  想一键直推草稿箱：配 WECHAT_APPID / WECHAT_APP_SECRET（developers.weixin.qq.com）"
                   " + 本机出口 IP 加入「API IP白名单」+ 用认证公众号")
    print_info("─" * 56)


def run(workdir: str, local_only: bool) -> dict:
    print_stage_header("发布到微信公众号草稿箱（md2wechat）")
    workspace = resolve_workspace(workdir)
    md_path = workspace["wechat"] / "wechat_article.md"
    html_path = workspace["wechat"] / "wechat_article.html"
    cover_path = workspace["wechat"] / "cover.jpg"

    if not md_path.exists():
        print_error(f"文章不存在：{md_path}")
        return {"status": "failed", "error": "wechat_article.md 不存在"}

    article = {}
    json_path = workspace["wechat"] / "wechat_article.json"
    if json_path.exists():
        try:
            article = load_json(json_path)
        except Exception:
            pass
    title = (article.get("title") or "").strip()
    summary = (article.get("digest") or "").strip()
    style = _style_from_theme(os.environ.get("MD2WECHAT_THEME", "default"))

    # —— 降级路：--local-only 或没凭据 → 本地出 HTML，不碰 API ——
    if local_only or not _creds_present():
        reason = "指定 --local-only" if local_only else "未配 WECHAT_APPID/WECHAT_APP_SECRET"
        print_warning(f"{reason}：走本地排版（不上传草稿）")
        _local_html(md_path, html_path, style)
        _guide_local(html_path, md_path, had_creds=_creds_present())
        res = {"status": "local", "reason": reason, "title": title,
               "markdown_path": str(md_path)}
        if html_path.exists():
            res["html_path"] = str(html_path)
        save_stage_result(res, "publish", workspace)
        return res

    # —— 上传草稿路 ——
    cmd = _get_md2wechat_cmd()
    if not _md2wechat_available(cmd):
        print_warning(f"md2wechat 不可用（{cmd}），降级本地排版")
        _local_html(md_path, html_path, style)
        _guide_local(html_path, md_path, had_creds=True)
        return {"status": "degraded", "reason": "md2wechat 不可用",
                "html_path": str(html_path) if html_path.exists() else None}

    if not cover_path.exists():
        print_warning("未找到 cover.jpg —— md2wechat 需至少一张图作封面，否则 MISSING_COVER_IMAGE")
    print_info(f"标题：{title[:40]} ｜ 摘要 {len(summary)} 字 ｜ 样式 {style}")

    up = _upload_draft(cmd, md_path, style, title, summary, cover_path)
    if up["ok"]:
        _guide_draft(up.get("media_id"), title)
        res = {"status": "success", "media_id": up.get("media_id"),
               "title": title, "target": "草稿箱"}
        save_stage_result(res, "publish", workspace)
        return res

    # 上传失败：可操作提示 + 仍本地出 HTML 兜底
    print_error(f"上传草稿失败（{up.get('code')}）：{up.get('error')}")
    _hint_for_error(up)
    _local_html(md_path, html_path, style)
    _guide_local(html_path, md_path, had_creds=True)
    res = {"status": "failed", "error": up.get("error"), "code": up.get("code")}
    if html_path.exists():
        res["html_path"] = str(html_path)
    save_stage_result(res, "publish", workspace)
    return res


def main() -> int:
    parser = argparse.ArgumentParser(description="发布到微信公众号草稿箱（md2wechat 封装）")
    parser.add_argument("--workdir", help="工作区目录，约定 <pdf目录>/.paper2anything/wechat")
    parser.add_argument("--local-only", action="store_true",
                        help="只本地生成样式化 HTML，不上传草稿（无需凭据）")
    parser.add_argument("--check-creds", action="store_true",
                        help="只检查 WECHAT_APPID/APP_SECRET 是否就位（0=有 / 2=无）")
    args = parser.parse_args()

    if args.check_creds:
        if _creds_present():
            print_success("WECHAT_APPID / WECHAT_APP_SECRET 已配置")
            return 0
        print_warning("未配置 WECHAT_APPID / WECHAT_APP_SECRET")
        return 2

    if not args.workdir:
        print_error("需要 --workdir")
        return 1

    res = run(args.workdir, args.local_only)
    # success / local / degraded 均不算失败（local、degraded 都已产出可用产物）
    return 0 if res.get("status") in ("success", "local", "degraded") else 1


if __name__ == "__main__":
    sys.exit(main())
