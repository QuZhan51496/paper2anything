"""
xhs_login — 拉取小红书登录二维码 + 等待登录完成（配合 xiaohongshu-mcp）

GET /api/v1/login/qrcode → 存成 PNG 供用户扫；`--wait` 监测 cookies.json 写出判定登录成功。
首次登录可能先有「新设备验证」：那道码只在浏览器界面出现（REST 拿不到），无头服务器需开
`-rod "monitor=:9273"` 在浏览器界面里扫。详见 references/publish-guide.md。
"""

import argparse
import base64
import os
import sys
import time
from pathlib import Path

import requests

import _env  # noqa: F401  # 兜底加载包根 .env（XHS_MCP_URL 等）

from utils import print_error, print_info, print_success, print_warning

DEFAULT_MCP_URL = "http://localhost:18060"


def _mcp_url(arg: str | None) -> str:
    return (arg or os.environ.get("XHS_MCP_URL") or DEFAULT_MCP_URL).rstrip("/")


def fetch_qrcode(mcp_url: str, out: Path) -> str | None:
    """拉登录二维码存成 PNG，返回有效期字符串；已登录或无码返回 None。"""
    resp = requests.get(f"{mcp_url}/api/v1/login/qrcode", timeout=120)
    data = resp.json().get("data", {})
    img = data.get("img", "")
    if not img:
        if data.get("is_logged_in"):
            print_success("已登录，无需扫码")
        else:
            print_error(f"未取到二维码：{resp.text[:200]}")
        return None
    b64 = img.split(",", 1)[1] if "," in img else img
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(b64))
    return data.get("timeout", "")


def wait_login(cookies_path: Path, timeout_s: int = 240) -> bool:
    """监测 cookies.json 写出/更新判定登录成功（比轮询 status 稳——开着 monitor 也不受影响）。"""
    start_mtime = cookies_path.stat().st_mtime if cookies_path.exists() else 0.0
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if cookies_path.exists() and cookies_path.stat().st_mtime > start_mtime:
            return True
        time.sleep(3)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="拉小红书登录二维码 + 等待登录（xiaohongshu-mcp）"
    )
    parser.add_argument(
        "--mcp-url", default=None,
        help="mcp 地址（默认 env XHS_MCP_URL 或 http://localhost:18060）",
    )
    parser.add_argument("--out", default="qr.png", help="二维码 PNG 输出路径（默认 ./qr.png）")
    parser.add_argument(
        "--wait", action="store_true", help="取码后监测 cookies.json 直到登录成功/超时",
    )
    parser.add_argument(
        "--cookies", default="cookies.json",
        help="要监测的 cookies.json 路径（mcp 工作目录下，默认 ./cookies.json）",
    )
    args = parser.parse_args()

    mcp_url = _mcp_url(args.mcp_url)
    out = Path(args.out).expanduser()

    try:
        timeout = fetch_qrcode(mcp_url, out)
    except requests.exceptions.RequestException as e:
        print_error(f"无法连接 mcp（{mcp_url}）：{e}")
        return 3
    except ValueError:
        print_error("二维码返回非 JSON")
        return 1

    if timeout is None:
        return 0  # 已登录或无码

    print_success(f"二维码已存：{out}（有效期 {timeout}）")
    print_info("用小红书 App 扫码 + 确认登录。")
    print_warning(
        "首次登录可能先弹『新设备验证』二维码——那道码只在浏览器界面出现（REST 拿不到）；"
    )
    print_warning(
        "无头服务器需开 monitor 端口在浏览器界面里扫，详见 references/publish-guide.md。"
    )

    if args.wait:
        cookies_path = Path(args.cookies).expanduser()
        print_info(f"等待登录（监测 {cookies_path} 写出，最长 4 分钟）……")
        if wait_login(cookies_path):
            print_success("检测到 cookies.json，登录成功！去掉 monitor flag 重启 mcp 再发布。")
            return 0
        print_error("超时仍未检测到 cookies.json（二维码可能已过期，重试）。")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
