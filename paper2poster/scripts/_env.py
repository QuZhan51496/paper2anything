"""统一加载 paper2anything 包根的 .env（poster 各脚本独立运行、无公共入口，故集中于此）。

任一脚本在顶部 `import _env` 即可让 os.environ 读到包根 .env 里的凭据；找不到则静默跳过。
凭据优先级仍是「已 export 的环境变量 > .env」——load_dotenv 默认不覆盖已存在的变量。
"""
from pathlib import Path

from dotenv import load_dotenv

# 包根 = 本文件上溯两级：_env.py → scripts → paper2poster → 包根（parents[2]）。
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
