"""Make `packages/papi/src/papi` importable in tests without installing the package."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC = PACKAGE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
