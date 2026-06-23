# 小红书登录与发布指引（xiaohongshu-mcp）

发布能力由开源项目 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)（作者 xpzouying）提供——一个自带无头 Chromium、暴露 REST API 的单二进制。本指引讲怎么按你的系统/有无显示器完成「登录一次 → 之后免登录发布」。

## 总览
- 登录**只需一次**：成功后 cookies 持久在 mcp 工作目录的 `cookies.json`，之后直接发布。
- 固定从**同一个持久目录**起 mcp（约定 `~/.paper2anything/xhs/`），cookies 才能复用。
- 发布前先查登录态：`GET /api/v1/login/status` 的 `data.is_logged_in` 为 `true` 即可直接发。
- 浏览器用 mcp 首次自动下载的 Chromium（约 150MB），无需额外安装。

## mcp 二进制（skill 自动备好，一般无需手动）
发布时 `SKILL.md` Step 5 ① 起服务前会自动检查二进制：`XHS_MCP_BIN` 已设且存在就用它，否则**按平台自动下载**到 `~/.paper2anything/xhs/`。所以通常什么都不用做。

想用自定义位置/版本，手动下载后在包根 `.env` 设 `XHS_MCP_BIN`：

```bash
mkdir -p ~/.paper2anything/xhs && cd ~/.paper2anything/xhs
# Linux x86_64（macOS Apple Silicon 换 darwin-arm64、Intel 换 darwin-amd64）：
curl -fL -O https://github.com/xpzouying/xiaohongshu-mcp/releases/latest/download/xiaohongshu-mcp-linux-amd64.tar.gz
tar xzf xiaohongshu-mcp-*.tar.gz && chmod +x xiaohongshu-mcp-*
# 包根 .env 里写：XHS_MCP_BIN=~/.paper2anything/xhs/xiaohongshu-mcp-linux-amd64
```

macOS 首次运行被 Gatekeeper 拦时：`xattr -c <二进制>` 去隔离。

## 起服务（任何系统通用）
从持久目录起，cookies.json 落在这里。`$BIN` = 设了 `XHS_MCP_BIN` 就用它，否则用自动下载到本目录的二进制：

```bash
cd ~/.paper2anything/xhs
BIN="${XHS_MCP_BIN:-$PWD/xiaohongshu-mcp-linux-amd64}"   # 其它平台换 darwin-arm64 / darwin-amd64
"$BIN" -port=:18060                                      # 默认无头；启动即加载已有 cookies.json
curl -s http://localhost:18060/api/v1/login/status       # data.is_logged_in:true → 已登录，直接发布
```

已登录就跳过下面的「登录」步骤。（前台启动，登录前用 Ctrl-C 停掉再换登录方式起；后台 mcp 则 `pkill -x xiaohongshu-mcp` 停。）

## 登录（按环境选一种，全程只需一次）

### A. Mac / Linux 有显示器
起一个**带界面**的浏览器，扫码即可（新设备验证也在同一窗口里完成）：

```bash
cd ~/.paper2anything/xhs
"$BIN" -port=:18060 -headless=false
```

弹出的浏览器里显示登录二维码：用 App 扫码 + 确认。**若是这台机器/账号首次登录，会先要求扫一道「新设备验证」二维码——在同一个窗口里扫它、确认，再扫登录码。** 登录成功后 `cookies.json` 写出。

### B. Linux 无显示器（headless 服务器）
看不到浏览器，而**「新设备验证」那道码 REST 拿不到**（`/api/v1/login/qrcode` 只返回登录码）。办法：开 go-rod 的 **monitor 端口**把无头浏览器经 HTTP 可视化出来，在浏览器界面里扫。

1. **带 monitor 起服务**（保持默认无头，仅多开 monitor 端口；若已有后台 mcp 在跑先 `pkill -x xiaohongshu-mcp`）：
   ```bash
   cd ~/.paper2anything/xhs
   "$BIN" -port=:18060 -rod "monitor=:9273"
   ```
2. **看浏览器界面**（二选一）：
   - 端口转发：本地执行 `ssh -L 9273:localhost:9273 你@服务器`，再用本地浏览器开 `http://localhost:9273/`，点开页面即可看到登录浏览器的实时画面；
   - 或截图存文件读：`http://localhost:9273/` 列出页面 id，`curl -s http://localhost:9273/screenshot/<页面id> -o login.png` 存成 PNG 再看。
3. **扫码登录**：界面里的登录二维码与 `curl /api/v1/login/qrcode` 取到的一致。**首次登录会先出现「新设备验证」二维码，先扫它、确认，再扫登录码。**
4. **登录成功后**：`cookies.json` 写出。**先 `pkill -x xiaohongshu-mcp` 停掉，再去掉 `-rod monitor` flag 重启 mcp**（普通发布不需要 monitor）——重启时才会加载 cookies，再用 status 确认 `is_logged_in:true`。

## 发布
登录态 OK 后，发布由 `scripts/publish.py` 完成（读 `xhs_post.json` + `cover.png`，`POST /api/v1/publish`）：

```bash
conda run -n paper2anything --no-capture-output \
  python "${SKILL_DIR}/scripts/publish.py" --workdir "$WORKDIR" --visibility "公开可见"
```

`title`≤20 字、`content`≤1000 字、`images` 用封面的**服务器本地绝对路径**、`visibility` 可选「公开可见 / 仅自己可见 / 仅互关好友可见」。

## 坑速查
- **登录成功后要重启 mcp 才会加载 cookies**：mcp 仅在启动时读 `cookies.json`。首次登录拿到 cookies 后重启一次（无头机顺便去掉 monitor flag），status 才会变 `is_logged_in:true`。
- **二维码 4 分钟有效**：取码后尽快扫完确认，过期就重取。
- **同账号多端互顶**：同一账号在别处重新登录可能把这个会话顶下线；届时 status 变 false，按上面重登一次即可。
