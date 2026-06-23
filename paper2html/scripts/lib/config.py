import os
from pathlib import Path

from dotenv import load_dotenv

# 统一加载 paper2anything 包根的 .env（5 个 skill 共用同一份凭据；找不到则静默跳过）。
# 凭据优先级：已 export 的环境变量 > .env（override=False 不覆盖已存在的变量）。
# 包根 = 本文件上溯四级：config.py → lib → scripts → paper2html(skill) → 包根（parents[3]）。
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

# MinerU API Configuration
# 注意：mineru_client 会自行拼接 /api/v4，故此处用主机根，勿写成 .../api/v4。
MINERU_API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net")
MINERU_API_TOKEN = os.environ.get("MINERU_API_TOKEN", "")

# Parsing options
ENABLE_TABLE = True
ENABLE_FORMULA = True
IS_OCR = False
LANGUAGE = "ch"


# Output — 输出根落在输入文件旁的 <input-dir>/.paper2anything/html/，调用方再按 <stem> 分篇（.../html/<stem>/）。
def default_output_root(source) -> Path:
    """输入文件同目录下的 .paper2anything/html/（输出根，调用方按 <stem> 分篇）。"""
    return Path(source).expanduser().resolve().parent / ".paper2anything" / "html"
