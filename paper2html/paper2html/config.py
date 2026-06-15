import os
from pathlib import Path

from dotenv import load_dotenv

# 统一加载 paper2anything 包根的 .env（5 个 skill 共用同一份凭据；找不到则静默跳过）。
# 包根 = 本文件上溯三级：config.py → paper2html → paper2html(skill) → 包根。
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# MinerU API Configuration
# 注意：mineru_client 会自行拼接 /api/v4，故此处用主机根，勿写成 .../api/v4。
MINERU_API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net")
MINERU_API_TOKEN = os.environ.get("MINERU_API_TOKEN", "")

# LLM Configuration
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "azure_openai/gpt-5.4")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://model.mify.ai.srv/v1")
LLM_REQUEST_TIMEOUT = int(os.environ.get("LLM_REQUEST_TIMEOUT", "900"))

# Parsing options
ENABLE_TABLE = True
ENABLE_FORMULA = True
IS_OCR = False
LANGUAGE = "ch"


# Output — 默认输出根目录落在输入文件旁的 <input-dir>/.paper2anything/html/，
# 与 slides/poster/xhs/wechat 的 .paper2anything/<skill>/ 方案统一；-o/--output 可覆盖。
def default_output_root(source) -> Path:
    """输入文件同目录下的 .paper2anything/html/。"""
    return Path(source).expanduser().resolve().parent / ".paper2anything" / "html"
