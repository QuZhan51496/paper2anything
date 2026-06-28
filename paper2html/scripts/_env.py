"""Uniformly load the .env at the paper2anything package root (a fallback when a mechanical script runs standalone; already-exported env vars take priority).

Any script can `import _env` at the top to let os.environ read the credentials in the package-root .env; silently skipped if not found.
Package root = this file going up two levels: _env.py → scripts → paper2html → package root (parents[2]).
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
