"""paper2slides scripts 包。

脚本统一以 `python -m scripts.<name>` 运行，导入任一子模块都会先执行本文件，
故在此统一加载 paper2anything 包根的 .env（5 个 skill 共用一份凭据；找不到则静默跳过）。
凭据优先级：已 export 的环境变量 > .env（load_dotenv 默认不覆盖已存在的变量）。
"""
from pathlib import Path

from dotenv import load_dotenv

# 包根 = 本文件上溯两级：__init__.py → scripts → paper2slides → 包根（parents[2]）。
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
