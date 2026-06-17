"""Check that all required dependencies are available."""
import importlib
import os
import sys

import _env  # noqa: F401  # 统一加载包根 .env（凭据）

REQUIRED = {
    "pptx": "python-pptx",
    "PIL": "Pillow",
    "requests": "requests",
}

OPTIONAL = {
    "yaml": "pyyaml (optional)",
}

missing = []
for module, package in REQUIRED.items():
    try:
        importlib.import_module(module)
    except ImportError:
        missing.append(package)

optional_missing = []
for module, desc in OPTIONAL.items():
    try:
        importlib.import_module(module)
    except ImportError:
        optional_missing.append(desc)

# Check MinerU token
has_token = bool(os.environ.get("MINERU_API_TOKEN", ""))

if missing:
    print(f"MISSING DEPENDENCIES: {', '.join(missing)}")
    print(f"Install with: pip install {' '.join(missing)}")
    sys.exit(1)
else:
    print("Required dependencies: OK")

if optional_missing:
    print(f"Optional (not critical): {', '.join(optional_missing)}")

if has_token:
    print("MinerU API token: configured")
else:
    print("MinerU API token: not set (get one at https://mineru.net/apiManage/token)")
    print("  Set with: export MINERU_API_TOKEN=<your_token>")
    print("  Or pass --token <token> to parse_pdf.py")

sys.exit(0)
