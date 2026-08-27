"""The worker, wrapped in just enough HTTP to survive a container platform.

Cloud Run — and every other platform built around request handling — will only keep a
container alive if it answers on ``$PORT``. The worker answers nothing: it is a loop that
owns time. So this module puts a health endpoint alongside it, which is the whole difference
between "deployable" and "killed sixty seconds after start".

    python -m hydra_worker.service

The loop runs on the **main** thread and the HTTP server on a daemon thread beside it, not
the other way round. That ordering is not stylistic: ``SimulationWorker.run_forever`` installs
SIGTERM and SIGINT handlers so a shutdown finishes the tick in flight, and Python only allows
signal handlers on the main thread. Run the loop on a worker thread and it dies immediately
with ``signal only works in main thread``, leaving a container that answers health checks
cheerfully while simulating nothing.

``GET /health`` reports whether the loop is running and which timelines it is advancing, so a
liveness check fails when the *simulation* stops rather than when the process does. Those are
different events, and the first one is the one worth restarting.

**One worker, and only one.** The worker owns the clock for a timeline. Two of them advancing
the same timeline would interleave ticks and overwrite each other's state, and nothing
downstream would report an error — the world would simply stop being a consequence of its own
rules. On Cloud Run that means ``--max-instances=1`` and ``--no-cpu-throttling``; the second is
not an optimisation, because a throttled instance stops running the loop between requests and
the city silently freezes.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from hydra_worker.worker import SimulationWorker

STARTED_AT = time.time()


class WorkerState:
    """What the health endpoint is allowed to know about the loop."""

    __slots__ = ("worker", "running", "error")

    def __init__(self) -> None:
        self.worker: SimulationWorker | None = None
        self.running = False
        self.error = ""

    def report(self) -> dict[str, Any]:
        worker = self.worker
        return {
            "status": "ok" if self.running and not self.error else "stopped",
            "loop_running": self.running,
            "error": self.error,
            "uptime_seconds": round(time.time() - STARTED_AT, 1),
            "timelines": sorted(worker.running) if worker else [],
        }


STATE = WorkerState()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
        if self.path.split("?")[0] not in ("/", "/health", "/healthz"):
            self.send_error(404)
            return
        report = STATE.report()
        body = json.dumps(report).encode("utf-8")
        # A stopped loop must fail the check, or the platform keeps a dead world alive.
        self.send_response(200 if report["status"] == "ok" else 503)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: Any) -> None:
        """Silence per-request logs; health checks would otherwise drown the worker's own."""


def serve_health(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="hydra-health", daemon=True).start()
    print(f"[worker] health endpoint on :{port}", flush=True)
    return server


def main() -> int:
    from hydra_api.service import build_store      # the worker and API agree on one store

    server = serve_health(int(os.environ.get("PORT", "8080")))

    worker = SimulationWorker(build_store())
    STATE.worker = worker
    STATE.running = True
    try:
        worker.run_forever()                        # main thread: owns the signal handlers
    except Exception as exc:                        # noqa: BLE001 - report, then let it restart
        STATE.error = f"{type(exc).__name__}: {exc}"
        print(f"[worker] loop stopped: {STATE.error}", flush=True)
    finally:
        STATE.running = False
        server.shutdown()
        server.server_close()

    print("[worker] stopped", flush=True)
    # Non-zero on a crash so the platform restarts the container rather than leaving a
    # process that is alive but no longer advancing anything.
    return 1 if STATE.error else 0


if __name__ == "__main__":
    raise SystemExit(main())
