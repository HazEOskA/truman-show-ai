"""Test bootstrap.

Adds every package directory to ``sys.path`` so the suite runs straight from a clone, with
no install step and no environment variables. The two applications go on the path too --
their Dockerfiles do the same with ``PYTHONPATH`` -- so the API and the worker can be tested
as the running processes they are, not just as the libraries underneath them.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _add(path: Path) -> None:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


for package in sorted((ROOT / "packages").iterdir()):
    if package.is_dir() and (package / "hydra").is_dir():
        _add(package)

for app in ("api", "simulation-worker"):
    directory = ROOT / "apps" / app
    if directory.is_dir():
        _add(directory)
