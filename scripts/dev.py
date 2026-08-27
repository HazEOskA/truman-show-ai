#!/usr/bin/env python3
"""Run the whole stack locally, in one command, on any operating system.

    python scripts/dev.py

Starts the API, the simulation worker and the Observatory, wires the import paths they each
need, and stops all three together on Ctrl-C. No database, no Docker, no environment
variables to remember.

This exists because the three-terminal version has three ways to fail and every one of them
looks like a broken repository rather than a missing path:

* ``uvicorn hydra_api.main:app`` cannot find ``hydra_api`` unless ``apps/api`` is on
  ``PYTHONPATH`` -- the Dockerfile sets it, a shell does not,
* the ``hydra.*`` packages need ``scripts/install_dev_paths.py`` to have been run once,
* ``npm run dev`` has to be run from ``apps/observatory``, not from the repository root.

A city is created automatically when the data directory is empty, so the Observatory has
something to show the moment it opens. ``--fresh`` rebuilds one that is already there.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ROOT / "packages"
#: What ``run_world.py`` names the world it creates. Printed so the control endpoints can
#: be reached by hand without guessing.
WORLD_ID = "world_hydra"

API_DIR = ROOT / "apps" / "api"
WORKER_DIR = ROOT / "apps" / "simulation-worker"
OBSERVATORY_DIR = ROOT / "apps" / "observatory"


def package_paths() -> list[str]:
    return sorted(str(p) for p in PACKAGES.iterdir() if p.is_dir() and (p / "hydra").is_dir())


def python_env(data_dir: Path) -> dict[str, str]:
    """Everything the Python processes need, without touching the user's site-packages."""

    env = os.environ.copy()
    parts = package_paths() + [str(API_DIR), str(WORKER_DIR)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["HYDRA_DATA_DIR"] = str(data_dir)
    env.setdefault("PYTHONUNBUFFERED", "1")
    # The file store is the default; make sure a stale service URL cannot hijack a local run.
    env.pop("HYDRA_DATABASE_URL", None)
    env.pop("HYDRA_REDIS_URL", None)
    return env


def create_world(data_dir: Path, seed: int, days: float, env: dict[str, str]) -> None:
    print(f"[dev] no world in {data_dir}; running genesis (seed {seed})")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_world.py"),
        "--seed", str(seed),
        "--days", str(days),
        "--data", str(data_dir),
        "--world-id", WORLD_ID,
    ]
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def npm_command() -> list[str] | None:
    """npm is ``npm.cmd`` on Windows, and absent entirely if Node was never installed."""

    for name in ("npm.cmd", "npm") if os.name == "nt" else ("npm",):
        found = shutil.which(name)
        if found:
            return [found]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Hydra World locally")
    parser.add_argument("--data", default=str(ROOT / "data"), help="where world state lives")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--days", type=float, default=1.0, help="days to simulate before serving")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--no-web", action="store_true", help="skip the Observatory")
    parser.add_argument("--no-worker", action="store_true", help="serve a frozen world")
    parser.add_argument("--fresh", action="store_true", help="rebuild the world even if one exists")
    args = parser.parse_args()

    data_dir = Path(args.data).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    env = python_env(data_dir)

    worlds_dir = data_dir / "worlds"
    if args.fresh or not worlds_dir.is_dir() or not any(worlds_dir.iterdir()):
        create_world(data_dir, args.seed, args.days, env)

    processes: list[tuple[str, subprocess.Popen]] = []

    def spawn(name: str, command: list[str], cwd: Path, extra: dict[str, str] | None = None) -> None:
        merged = dict(env)
        if extra:
            merged.update(extra)
        print(f"[dev] {name}: {' '.join(command)}")
        processes.append((name, subprocess.Popen(command, cwd=cwd, env=merged)))

    spawn(
        "api",
        [sys.executable, "-m", "uvicorn", "hydra_api.main:app",
         "--host", "127.0.0.1", "--port", str(args.api_port)],
        ROOT,
    )

    if not args.no_worker:
        time.sleep(1.5)                       # let the API claim the port before the log noise
        spawn("worker", [sys.executable, "-m", "hydra_worker.worker"], ROOT)

    if not args.no_web:
        npm = npm_command()
        if npm is None:
            print("[dev] npm not found; skipping the Observatory (install Node 20+ to see the city)")
        else:
            if not (OBSERVATORY_DIR / "node_modules").is_dir():
                print("[dev] installing Observatory dependencies (first run only)")
                subprocess.run(npm + ["install", "--no-audit", "--no-fund"],
                               cwd=OBSERVATORY_DIR, check=True)
            spawn(
                "observatory",
                npm + ["run", "dev", "--", "--port", str(args.web_port)],
                OBSERVATORY_DIR,
                {"NEXT_PUBLIC_API_URL": f"http://127.0.0.1:{args.api_port}"},
            )

    print()
    print(f"[dev] world       {WORLD_ID} / tl_zero")
    print(f"[dev] City View   http://localhost:{args.web_port}/city")
    print(f"[dev] Observatory http://localhost:{args.web_port}")
    print(f"[dev] API docs    http://localhost:{args.api_port}/docs")
    print("[dev] Ctrl-C stops everything.")
    print()

    try:
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    print(f"[dev] {name} exited with {process.returncode}; shutting down")
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for _, process in reversed(processes):
            if process.poll() is None:
                process.terminate()          # portable; CTRL_BREAK needs a process group
        deadline = time.time() + 8
        for _, process in reversed(processes):
            remaining = max(0.1, deadline - time.time())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
        print("[dev] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
