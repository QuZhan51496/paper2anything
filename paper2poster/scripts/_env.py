"""Load the paper2anything package-root .env in one place (the poster scripts run standalone with no shared entry point, so this is centralized here).

Any script that does `import _env` at its top lets os.environ read the credentials from the package-root .env; if not found, it is silently skipped.
Credential precedence is still "already-exported env vars > .env" — load_dotenv does not override existing variables by default.
"""
from pathlib import Path

from dotenv import load_dotenv

# package root = two levels up from this file: _env.py → scripts → paper2poster → package root (parents[2]).
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
