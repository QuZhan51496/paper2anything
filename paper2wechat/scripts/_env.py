"""统一加载 paper2anything 包根的 .env（机械脚本独立运行时兜底；已 export 的环境变量优先）。

任一脚本在顶部 `import _env` 即可让 os.environ 读到包根 .env 里的凭据；找不到则静默跳过。
包根 = 本文件上溯两级：_env.py → scripts → paper2wechat → 包根（parents[2]）。
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
