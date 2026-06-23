"""
publish — 发布到小红书（xiaohongshu-mcp REST 客户端）

发布前先查登录状态（GET /api/v1/login/status）：
  - 已登录 → 读 xhs_post.json + cover.png 拼载荷 → POST /api/v1/publish
  - 未登录 → 提示按 references/publish-guide.md 完成登录，退出码 2

发布能力由开源项目 xiaohongshu-mcp（作者 xpzouying）提供；用户自行从其官方
release 下载二进制并启动服务（默认 http://localhost:18060，可经 XHS_MCP_URL 覆盖）。
"""

import argparse
import os
import sys

import requests

import _env  # noqa: F401  # 兜底加载包根 .env（XHS_MCP_URL 等）

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

DEFAULT_MCP_URL = "http://localhost:18060"


def _mcp_url(arg: str | None) -> str:
    return (arg or os.environ.get("XHS_MCP_URL") or DEFAULT_MCP_URL).rstrip("/")


def check_login(mcp_url: str) -> tuple[bool, str | None]:
    """查 /api/v1/login/status，返回 (is_logged_in, username)。连接失败抛 requests 异常。"""
    resp = requests.get(f"{mcp_url}/api/v1/login/status", timeout=60)
    try:
        data = resp.json().get("data", {})
    except ValueError:
        data = {}
    return bool(data.get("is_logged_in")), data.get("username")


def _build_payload(workspace: dict, visibility: str) -> dict | None:
    """从 xhs_post.json + cover.png 拼 /publish 载荷。缺关键字段返回 None。"""
    post_path = workspace["xhs"] / "xhs_post.json"
    if not post_path.exists():
        print_error(f"帖子文件不存在: {post_path}")
        return None
    post = load_json(post_path)

    title = (post.get("title") or "").strip()[:20]
    body = post.get("body") or ""
    hashtags = post.get("hashtags") or post.get("tags") or []
    tags = [h.lstrip("#").strip() for h in hashtags if h and h.strip()]

    # 正文去掉末尾的空行与话题行（话题改放 tags 字段，避免正文末尾与 tags 重复）
    lines = body.rstrip().split("\n")
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
        lines.pop()
    content = "\n".join(lines).strip()[:1000]

    # 封面（发布至少需 1 张图）
    cover = workspace["xhs"] / "cover.png"
    if not cover.exists():
        print_error(f"未找到封面 cover.png（发布至少需 1 张图）: {cover}")
        return None
    if not title or not content:
        print_error("标题或正文为空，无法发布")
        return None

    return {
        "title": title,
        "content": content,
        "images": [str(cover.resolve())],
        "tags": tags,
        "visibility": visibility,
    }


def run(workdir: str, visibility: str, mcp_url: str) -> dict:
    """查登录 → 拼载荷 → 发布。"""
    print_stage_header("发布到小红书（xiaohongshu-mcp）")
    workspace = resolve_workspace(workdir)

    # 1) 先查登录
    try:
        logged_in, username = check_login(mcp_url)
    except requests.exceptions.RequestException as e:
        print_error(f"无法连接 mcp（{mcp_url}）：{e}")
        print_info("请先启动 xiaohongshu-mcp，详见 references/publish-guide.md")
        return {"status": "mcp_unreachable", "error": str(e)}

    if not logged_in:
        print_warning("当前未登录小红书。请先完成登录，详见 references/publish-guide.md")
        return {"status": "not_logged_in"}
    print_success(f"已登录{('：' + username) if username else ''}")

    # 2) 拼载荷
    payload = _build_payload(workspace, visibility)
    if payload is None:
        return {"status": "failed", "error": "载荷构建失败"}

    print_info(f"标题（{len(payload['title'])} 字）：{payload['title']}")
    print_info(
        f"正文 {len(payload['content'])} 字 ｜ 话题 {len(payload['tags'])} 个 ｜ 可见性：{visibility}"
    )

    # 3) 发布
    try:
        resp = requests.post(f"{mcp_url}/api/v1/publish", json=payload, timeout=180)
        body = resp.json()
    except requests.exceptions.RequestException as e:
        print_error(f"发布请求失败：{e}")
        return {"status": "failed", "error": str(e)}
    except ValueError:
        print_error(f"发布返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
        return {"status": "failed", "error": "non-json response"}

    if resp.ok and body.get("success"):
        data = body.get("data", {})
        print_success(f"发布成功：{data.get('status', '')}")
        result = {
            "status": "success",
            "title": payload["title"],
            "images_count": len(payload["images"]),
            "visibility": visibility,
            "response": data,
        }
    else:
        print_error(f"发布失败：{body.get('message') or body}")
        result = {"status": "failed", "error": body.get("message") or str(body)}

    save_stage_result(result, "publish", workspace)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="发布到小红书（xiaohongshu-mcp REST 客户端）")
    parser.add_argument(
        "--workdir", help="工作区目录，约定 <pdf目录>/.paper2anything/xhs"
    )
    parser.add_argument(
        "--visibility",
        default="公开可见",
        choices=["公开可见", "仅自己可见", "仅互关好友可见"],
        help="帖子可见性（默认公开可见）",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help="mcp 地址（默认 env XHS_MCP_URL 或 http://localhost:18060）",
    )
    parser.add_argument(
        "--check-only", action="store_true", help="只查登录状态，不发布"
    )
    args = parser.parse_args()

    mcp_url = _mcp_url(args.mcp_url)

    # 只查登录态：0=已登录 / 2=未登录 / 3=连不上 mcp
    if args.check_only:
        try:
            logged_in, username = check_login(mcp_url)
        except requests.exceptions.RequestException as e:
            print_error(f"无法连接 mcp（{mcp_url}）：{e}")
            return 3
        if logged_in:
            print_success(f"已登录{('：' + username) if username else ''}")
            return 0
        print_warning("未登录")
        return 2

    if not args.workdir:
        print_error("发布需要 --workdir")
        return 1

    res = run(args.workdir, args.visibility, mcp_url)
    status = res.get("status")
    if status == "success":
        return 0
    if status == "not_logged_in":
        return 2
    if status == "mcp_unreachable":
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
