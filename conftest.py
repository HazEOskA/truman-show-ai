"""Test bootstrap.

Adds every package directory to ``sys.path`` so the suite runs straight from a clone, with
no install step and no environment variables.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for package in sorted((ROOT / "packages").iterdir()):
    if package.is_dir() and (package / "hydra").is_dir():
        path = str(package)
        if path not in sys.path:
            sys.path.insert(0, path)
