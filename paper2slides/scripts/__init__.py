"""paper2slides scripts package.

Scripts run uniformly via `python -m scripts.<name>`, and importing any submodule executes
this file first, so here we uniformly load the .env at the paper2anything package root
(5 skills share one set of credentials; silently skip if not found).
Credential priority: already-exported environment variables > .env (load_dotenv by default
does not override variables that already exist).
"""
from pathlib import Path

from dotenv import load_dotenv

# package root = this file going up two levels: __init__.py → scripts → paper2slides → package root (parents[2]).
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
