"""Simulation worker.

The worker is the only process that advances time. It reads the operator's intent from the
control channel at every tick boundary, runs the kernel, and publishes what the Observatory
reads: live state, telemetry and the ledger. If it dies, the world resumes from its last
snapshot — nothing is lost that was not already replayable.
"""

from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass, field
from typing import Any

from hydra.kernel.config import WorldConfig
from hydra.kernel.kernelstate import KernelDomainState
from hydra.kernel.snapshots import restore_snapshot, take_snapshot
from hydra.persistence.store import ControlState, WorldStore
from hydra.world.builder import WorldRuntime, build_kernel
from hydra.world.scenarios import run_scenario

LIVE_EVERY_TICKS = int(os.environ.get("HYDRA_LIVE_EVERY_TICKS", "6"))
TELEMETRY_EVERY_TICKS = int(os.environ.get("HYDRA_TELEMETRY_EVERY_TICKS", "6"))
POLL_SECONDS = float(os.environ.get("HYDRA_POLL_SECONDS", "1.0"))
BATCH_SECONDS = float(os.environ.get("HYDRA_BATCH_SECONDS", "0.5"))


@dataclass(slots=True)
class RunningWorld:
    world_id: str
    timeline_id: str
    runtime: WorldRuntime
    last_live_tick: int = 0
    last_telemetry_tick: int = 0
    notes: list[str] = field(default_factory=list)


class SimulationWorker:
    def __init__(self, store: WorldStore, *, verbose: bool = True) -> None:
        self.store = store
        self.verbose = verbose
        self.running: dict[str, RunningWorld] = {}
        self._stop = False

    # -- lifecycle ----------------------------------------------------------------
    def stop(self, *_: Any) -> None:
        self._stop = True

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self._log("worker started")
        while not self._stop:
            worked = False
            for world in self.store.list_worlds():
                for timeline in self.store.list_timelines(world.world_id):
                    control = self.store.get_control(world.world_id, timeline.timeline_id)
                    if control is None:
                        continue
                    if control.mode == "running" or control.step_ticks > 0 or control.scenario:
                        worked |= self._advance(world.world_id, timeline.timeline_id, control)
            if not worked:
                time.sleep(POLL_SECONDS)
        self._flush_all()
        self._log("worker stopped")

    # -- work ---------------------------------------------------------------------
    def _advance(self, world_id: str, timeline_id: str, control: ControlState) -> bool:
        entry = self._load(world_id, timeline_id)
        if entry is None:
            return False
        runtime = entry.runtime

        if control.scenario:
            self._apply_scenario(entry, control)

        budget_ticks = self._budget(control)
        if budget_ticks <= 0:
            return False

        started = time.perf_counter()
        for _ in range(budget_ticks):
            runtime.kernel.tick()
            tick = runtime.state.meta.tick
            if tick - entry.last_telemetry_tick >= TELEMETRY_EVERY_TICKS:
                entry.last_telemetry_tick = tick
                metrics = dict(runtime.state.domain(KernelDomainState).metrics)
                self.store.write_telemetry(timeline_id, tick, metrics)
            if tick - entry.last_live_tick >= LIVE_EVERY_TICKS:
                entry.last_live_tick = tick
                runtime.ledger.flush()
                self.store.write_live(take_snapshot(runtime.state))
            if control.target_tick is not None and tick >= control.target_tick:
                self._pause(control, note=f"reached target tick {control.target_tick}")
                break
            if time.perf_counter() - started > BATCH_SECONDS and control.speed <= 0:
                break

        runtime.ledger.flush()
        self.store.write_live(take_snapshot(runtime.state))
        entry.last_live_tick = runtime.state.meta.tick

        if control.step_ticks > 0:
            control.step_ticks = max(0, control.step_ticks - budget_ticks)
            if control.step_ticks == 0 and control.mode != "running":
                self._pause(control, note="step complete")
            else:
                self.store.put_control(control)
        if control.speed > 0:
            time.sleep(max(0.0, budget_ticks / control.speed - (time.perf_counter() - started)))
        return True

    def _budget(self, control: ControlState) -> int:
        if control.step_ticks > 0:
            return min(control.step_ticks, 144)
        if control.mode != "running":
            return 0
        if control.speed <= 0:
            return 24          # unthrottled: a batch at a time, so control stays responsive
        return max(1, int(round(control.speed * BATCH_SECONDS)))

    def _pause(self, control: ControlState, *, note: str) -> None:
        control.mode = "paused"
        control.step_ticks = 0
        control.target_tick = None
        control.note = note
        self.store.put_control(control)
        self._log(f"{control.timeline_id}: paused ({note})")

    def _apply_scenario(self, entry: RunningWorld, control: ControlState) -> None:
        try:
            request = json.loads(control.scenario)
            result = run_scenario(entry.runtime, request["name"], **request.get("params", {}))
            entry.notes.append(f"t{result.tick} {result.name} {result.detail}")
            self._log(f"{entry.timeline_id}: scenario {result.name} at tick {result.tick} → {result.detail}")
        except Exception as exc:  # noqa: BLE001 - a bad scenario must not kill the worker
            self._log(f"{entry.timeline_id}: scenario failed: {exc}")
        finally:
            control.scenario = ""
            self.store.put_control(control)

    # -- state --------------------------------------------------------------------
    def _load(self, world_id: str, timeline_id: str) -> RunningWorld | None:
        entry = self.running.get(timeline_id)
        if entry is not None:
            return entry
        snapshot = self.store.read_live(timeline_id) or self.store.nearest_snapshot(timeline_id, 10**12)
        if snapshot is None:
            return None
        record = self.store.get_world(world_id)
        config = WorldConfig()
        if record is not None and record.config:
            from hydra.kernel.serialization import decode

            try:
                config = decode(WorldConfig, record.config)
            except Exception:  # noqa: BLE001 - fall back to defaults rather than refusing to run
                self._log(f"{world_id}: stored config could not be decoded, using defaults")
        state = restore_snapshot(snapshot, verify=False)
        kernel, ledger = build_kernel(state, config, store=self.store)
        runtime = WorldRuntime(kernel=kernel, state=state, config=config, ledger=ledger, store=self.store)
        entry = RunningWorld(
            world_id=world_id,
            timeline_id=timeline_id,
            runtime=runtime,
            last_live_tick=state.meta.tick,
            last_telemetry_tick=state.meta.tick,
        )
        self.running[timeline_id] = entry
        self._log(f"{timeline_id}: loaded at tick {state.meta.tick}")
        return entry

    def _flush_all(self) -> None:
        for entry in self.running.values():
            entry.runtime.ledger.flush()
            self.store.write_live(take_snapshot(entry.runtime.state))

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[worker] {message}", flush=True)


def main() -> int:
    from hydra_api.service import build_store  # the worker and API agree on one store

    worker = SimulationWorker(build_store())
    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
