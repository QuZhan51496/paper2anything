#!/usr/bin/env bash
# tools/install.sh — 把 paper2anything 的 5 个 skill 注册到 Claude Code
#
# 做的事：
#   1. 确保 ~/.claude/skills/ 存在
#   2. 为 5 个 skill 各创建/更新符号链接 ~/.claude/skills/<name> → <repo>/<name>
#   3. 没有 .env 时从 .env.example 复制一份（提示填 key）
#   4. 依赖检查（conda env paper2anything / node+pptxgenjs / playwright chromium /
#      poppler / libreoffice / MINERU 凭据），缺什么只提示、不阻塞
#
# 可选：
#   --create-env   顺手创建/更新 conda 环境并装 playwright chromium，
#                  再跑 pip check + 关键库 import 自检（conda env create 退出 0
#                  不代表 pip 全装上，故务必自检——见 README 排错）。
#
# 不做的事（需 sudo / 系统级，按提示手动装）：
#   - 不装系统包（poppler-utils / libreoffice / nodejs）
#   - 不装 npm 全局包（pptxgenjs）

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_dir="$HOME/.claude/skills"
ENV_NAME="paper2anything"
SKILLS=(paper2slides paper2poster paper2html paper2xhs paper2wechat)

green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*"; }

CREATE_ENV=0
for arg in "$@"; do
  case "$arg" in
    --create-env) CREATE_ENV=1 ;;
    -h|--help)
      awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
      exit 0 ;;
    *) red "未知参数: $arg（用 -h 看用法）"; exit 1 ;;
  esac
done

# ---------- 1. 注册 5 个 skill 的 symlink ----------

echo "Registering skills → $skills_dir"
mkdir -p "$skills_dir"

link_skill() {
  local name="$1"
  local src="$repo_root/$name"
  local dst="$skills_dir/$name"
  if [[ ! -f "$src/SKILL.md" ]]; then
    red "  [skip] $name — 源目录缺 SKILL.md: $src"; return 1
  fi
  if [[ -L "$dst" ]]; then
    local current; current="$(readlink "$dst")"
    if [[ "$current" == "$src" ]]; then
      green "  [ok]  $name → 已指向本仓库"
    else
      yellow "  [upd] $name — 旧链接 $current 改指 $src"
      rm "$dst"; ln -s "$src" "$dst"
    fi
  elif [[ -e "$dst" ]]; then
    red "  [skip] $dst 已存在且不是符号链接，拒绝覆盖；请手动移除后重跑"; return 1
  else
    ln -s "$src" "$dst"; green "  [new] $name → $src"
  fi
}

fail=0
for name in "${SKILLS[@]}"; do link_skill "$name" || fail=1; done

# ---------- 2. .env 引导 ----------

echo
if [[ -f "$repo_root/.env" ]]; then
  green ".env 已存在"
elif [[ -f "$repo_root/.env.example" ]]; then
  cp "$repo_root/.env.example" "$repo_root/.env"
  green ".env 已从 .env.example 复制 —— 填入你的 key（至少 MINERU_API_TOKEN）"
else
  yellow ".env 与 .env.example 都不存在，跳过"
fi

# ---------- 3.（可选）创建/更新 conda 环境 ----------

if [[ "$CREATE_ENV" == 1 ]]; then
  echo
  echo "Creating/updating conda env '$ENV_NAME' ..."
  if ! command -v conda >/dev/null 2>&1; then
    red "conda 不在 PATH，无法 --create-env；先装 miniconda/anaconda"; exit 1
  fi
  if conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    yellow "  env 已存在 → 按 environment.yml 更新（--prune）"
    conda env update -n "$ENV_NAME" -f "$repo_root/environment.yml" --prune
  else
    conda env create -f "$repo_root/environment.yml"
  fi
  echo "  装 playwright chromium ..."
  conda run -n "$ENV_NAME" python -m playwright install chromium \
    || yellow "  playwright chromium 安装失败，可稍后手动重试"
  echo "  自检（pip check + 关键库 import）..."
  conda run -n "$ENV_NAME" pip check || yellow "  pip check 有告警（见上）"
  conda run -n "$ENV_NAME" python -c \
    "import requests, rich, dotenv, PIL, openai, playwright, markitdown; print('  关键库 import OK')" \
    || red "  关键库 import 失败 —— pip 可能 PARTIAL，按 README 单独补装后再 pip check"
fi

# ---------- 4. 依赖检查（只警告，不阻塞）----------

echo
echo "Dependency check:"

check() {
  local name="$1" cmd="$2" hint="$3"
  if command -v "$cmd" >/dev/null 2>&1; then
    green "  [ok] $name → $(command -v "$cmd")"
  else
    yellow "  [missing] $name — $hint"
  fi
}

check "conda"       "conda"  "装 miniconda/anaconda"
check "node"        "node"   "装 Node.js v20+（NodeSource）；paper2slides 渲染 PPT 用"
check "pdftoppm"    "pdftoppm"  "sudo apt install poppler-utils（paper2slides 整页渲染）"
check "libreoffice" "soffice"   "sudo apt install libreoffice（paper2slides 视觉 QA）"

# conda env
if command -v conda >/dev/null 2>&1; then
  if conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    green "  [ok] conda env '$ENV_NAME'"
  else
    yellow "  [missing] conda env '$ENV_NAME' — 跑: conda env create -f $repo_root/environment.yml（或本脚本加 --create-env）"
  fi
fi

# pptxgenjs（npm 全局，paper2slides）
if command -v npm >/dev/null 2>&1; then
  if npm list -g --depth=0 2>/dev/null | grep -q pptxgenjs; then
    green "  [ok] pptxgenjs (npm global)"
  else
    yellow "  [missing] pptxgenjs (npm global) — 跑: sudo npm install -g pptxgenjs react-icons react react-dom sharp"
  fi
fi

# playwright chromium（paper2poster / paper2xhs）—— 查浏览器缓存目录，避免 conda run playwright 卡超时
if compgen -G "$HOME/.cache/ms-playwright/chromium-*" >/dev/null 2>&1; then
  green "  [ok] playwright chromium (~/.cache/ms-playwright)"
else
  yellow "  [missing] playwright chromium — 跑: conda run -n $ENV_NAME python -m playwright install chromium"
fi

# MINERU 凭据（5 个 skill 解析 PDF 必需；不 abort，只提示）
if [[ -n "${MINERU_API_TOKEN:-}" ]]; then
  green "  [ok] MINERU_API_TOKEN 已在环境中"
elif [[ -f "$repo_root/.env" ]] \
     && grep -q '^MINERU_API_TOKEN=' "$repo_root/.env" \
     && ! grep -q '^MINERU_API_TOKEN=your-mineru-token' "$repo_root/.env"; then
  green "  [ok] .env 内已填 MINERU_API_TOKEN（skill 运行时自动读取）"
else
  yellow "  [todo] MINERU_API_TOKEN 未设置 — 在包根 .env 填入即可（https://mineru.net 申请；skill 会自动从 .env 读取）"
fi

# ---------- 收尾 ----------

echo
if [[ "$fail" == 0 ]]; then
  green "Done. 5 个 skill 已注册。在 Claude Code 里测试，如: /paper2html <paper>.pdf"
else
  yellow "完成，但有 skill 注册失败（见上）。修正后重跑本脚本。"
  exit 1
fi
