#!/usr/bin/env python3
"""Make the ``hydra.*`` namespace packages importable.

The repository keeps one directory per package (``packages/world-kernel``, ``packages/economy``…)
exactly as the architecture describes, and they all contribute to the same PEP 420 namespace.
This writes a single ``.pth`` file into the active environment so ``import hydra.kernel.engine``
works from anywhere — in tests, in the API, in the worker and in a plain REPL.

    python scripts/install_dev_paths.py
"""

from __future__ import annotations

import site
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ROOT / "packages"
PTH_NAME = "hydra_world.pth"


def package_paths() -> list[str]:
    return sorted(str(p) for p in PACKAGES.iterdir() if p.is_dir() and (p / "hydra").is_dir())


def target_directory() -> Path:
    candidates: list[str] = []
    if hasattr(site, "getsitepackages"):
        candidates.extend(site.getsitepackages())
    user_site = site.getusersitepackages() if hasattr(site, "getusersitepackages") else None
    purelib = sysconfig.get_path("purelib")
    if purelib:
        candidates.insert(0, purelib)
    for candidate in candidates:
        path = Path(candidate)
        if path.is_dir():
            try:
                probe = path / ".hydra_write_test"
                probe.write_text("", encoding="utf-8")
                probe.unlink()
                return path
            except OSError:
                continue
    if user_site:
        path = Path(user_site)
        path.mkdir(parents=True, exist_ok=True)
        return path
    raise SystemExit("no writable site-packages directory found")


def main() -> int:
    paths = package_paths()
    if not paths:
        raise SystemExit(f"no packages found under {PACKAGES}")
    target = target_directory() / PTH_NAME
    target.write_text("\n".join(paths) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
