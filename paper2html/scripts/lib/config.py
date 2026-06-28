import os
from pathlib import Path

from dotenv import load_dotenv

# Uniformly load the .env at the paper2anything package root (the 5 skills share one set of credentials; silently skipped if not found).
# Credential priority: already-exported env vars > .env (override=False does not overwrite existing variables).
# Package root = this file going up four levels: config.py → lib → scripts → paper2html(skill) → package root (parents[3]).
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

# MinerU API Configuration
# Note: mineru_client appends /api/v4 itself, so use the host root here, not .../api/v4.
MINERU_API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net")
MINERU_API_TOKEN = os.environ.get("MINERU_API_TOKEN", "")

# Parsing options
ENABLE_TABLE = True
ENABLE_FORMULA = True
IS_OCR = False
LANGUAGE = "en"


# Output — the output root lands next to the input file at <input-dir>/.paper2anything/html/, and the caller splits by <stem> (.../html/<stem>/).
def default_output_root(source) -> Path:
    """The .paper2anything/html/ directory next to the input file (the output root; the caller splits by <stem>)."""
    return Path(source).expanduser().resolve().parent / ".paper2anything" / "html"
