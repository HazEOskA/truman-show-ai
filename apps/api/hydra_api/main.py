"""Hydra World API.

Read-first: almost every endpoint projects the world, and the few that write express operator
intent (create, control, scenario, fork) which the worker picks up at a tick boundary. No
endpoint reaches into a running tick.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hydra.kernel.serialization import encode
from hydra.kernel.version import KERNEL_VERSION

from . import readmodel
from .service import WorldService

app = FastAPI(
    title="Hydra World",
    version=KERNEL_VERSION,
    description="Observatory API for the Hydra World simulation",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("HYDRA_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = WorldService()


class CreateWorldRequest(BaseModel):
    seed: int = Field(default=20260826, description="MASTER_WORLD_SEED")
    world_id: str = ""
    name: str = "Hydra World"
    residents: int | None = None
    persistent_agents: int | None = None
    companies: int | None = None


class ControlRequest(BaseModel):
    mode: str | None = Field(default=None, description="running | paused | stopped")
    speed: float | None = Field(default=None, description="ticks per real second, 0 = unthrottled")
    step_ticks: int | None = None
    target_tick: int | None = None
    note: str | None = None


class ScenarioRequest(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class ForkRequest(BaseModel):
    fork_tick: int
    label: str = ""
    divergence_salt: str = ""


def _state(timeline_id: str):
    try:
        return service.state(timeline_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "kernel_version": KERNEL_VERSION, "worlds": len(service.worlds())}


# -- worlds and timelines ---------------------------------------------------------
@app.post("/worlds")
def create_world(request: CreateWorldRequest) -> dict[str, Any]:
    try:
        return service.create_world(
            seed=request.seed,
            world_id=request.world_id,
            name=request.name,
            residents=request.residents,
            persistent_agents=request.persistent_agents,
            companies=request.companies,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/worlds")
def list_worlds() -> dict[str, Any]:
    return {"worlds": [encode(w) for w in service.worlds()]}


@app.get("/worlds/{world_id}/timelines")
def list_timelines(world_id: str) -> dict[str, Any]:
    return {
        "timelines": [encode(t) for t in service.timelines(world_id)],
        "tree": service.timeline_tree(world_id),
    }


@app.post("/worlds/{world_id}/timelines/{timeline_id}/fork")
def fork(world_id: str, timeline_id: str, request: ForkRequest) -> dict[str, Any]:
    try:
        return service.fork(
            world_id,
            timeline_id,
            fork_tick=request.fork_tick,
            label=request.label,
            divergence_salt=request.divergence_salt,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# -- control ----------------------------------------------------------------------
@app.get("/worlds/{world_id}/timelines/{timeline_id}/control")
def get_control(world_id: str, timeline_id: str) -> dict[str, Any]:
    return encode(service.control(world_id, timeline_id))


@app.post("/worlds/{world_id}/timelines/{timeline_id}/control")
def set_control(world_id: str, timeline_id: str, request: ControlRequest) -> dict[str, Any]:
    if request.mode is not None and request.mode not in ("running", "paused", "stopped"):
        raise HTTPException(status_code=400, detail="mode must be running, paused or stopped")
    return encode(
        service.set_control(
            world_id,
            timeline_id,
            mode=request.mode,
            speed=request.speed,
            step_ticks=request.step_ticks,
            target_tick=request.target_tick,
            note=request.note,
        )
    )


@app.post("/worlds/{world_id}/timelines/{timeline_id}/scenario")
def run_scenario(world_id: str, timeline_id: str, request: ScenarioRequest) -> dict[str, Any]:
    from hydra.world.scenarios import SCENARIOS

    if request.name not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"unknown scenario {request.name}")
    payload = json.dumps({"name": request.name, "params": request.params}, separators=(",", ":"))
    control = service.set_control(world_id, timeline_id, scenario=payload)
    return {"queued": True, "scenario": request.name, "params": request.params, "mode": control.mode}


@app.get("/scenarios")
def list_scenarios() -> dict[str, Any]:
    from hydra.world.scenarios import SCENARIOS

    return {"scenarios": sorted(SCENARIOS)}


# -- projections ------------------------------------------------------------------
@app.get("/worlds/{world_id}/timelines/{timeline_id}/state")
def world_state(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.world_summary(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/metrics")
def metrics(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.metrics_view(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/city")
def city(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.city_view(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/population")
def population(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.population_view(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/people")
def people(
    world_id: str,
    timeline_id: str,
    limit: int = Query(default=50, le=500),
    district: str = "",
    tier: str = "",
    q: str = "",
) -> dict[str, Any]:
    return readmodel.people_view(_state(timeline_id), limit=limit, district=district, tier=tier, query=q)


@app.get("/worlds/{world_id}/timelines/{timeline_id}/people/{person_id}")
def person(world_id: str, timeline_id: str, person_id: str) -> dict[str, Any]:
    detail = readmodel.person_detail(_state(timeline_id), person_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no such person: {person_id}")
    return detail


@app.get("/worlds/{world_id}/timelines/{timeline_id}/companies")
def companies(
    world_id: str, timeline_id: str, limit: int = Query(default=60, le=500), sector: str = ""
) -> dict[str, Any]:
    return readmodel.companies_view(_state(timeline_id), limit=limit, sector=sector)


@app.get("/worlds/{world_id}/timelines/{timeline_id}/economy")
def economy(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.economy_view(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/government")
def government(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.government_view(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/media")
def media(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.media_view(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/technology")
def technology(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.technology_view(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/culture")
def culture(world_id: str, timeline_id: str) -> dict[str, Any]:
    return readmodel.culture_view(_state(timeline_id))


@app.get("/worlds/{world_id}/timelines/{timeline_id}/chronicle")
def chronicle(world_id: str, timeline_id: str, limit: int = Query(default=60, le=400)) -> dict[str, Any]:
    return readmodel.chronicle_view(_state(timeline_id), limit=limit)


# -- history ----------------------------------------------------------------------
@app.get("/worlds/{world_id}/timelines/{timeline_id}/events")
def events(
    world_id: str,
    timeline_id: str,
    limit: int = Query(default=100, le=1000),
    topic: str = "",
    actor: str = "",
    min_importance: float = 0.0,
    start_tick: int = 0,
    end_tick: int | None = None,
) -> dict[str, Any]:
    return {
        "events": service.events(
            timeline_id,
            limit=limit,
            topics=tuple(t for t in topic.split(",") if t),
            actor=actor or None,
            min_importance=min_importance,
            start_tick=start_tick,
            end_tick=end_tick,
        )
    }


@app.get("/worlds/{world_id}/timelines/{timeline_id}/events/{event_id}/causes")
def causes(world_id: str, timeline_id: str, event_id: str) -> dict[str, Any]:
    return service.causal_chain(timeline_id, event_id)


@app.get("/worlds/{world_id}/timelines/{timeline_id}/telemetry")
def telemetry(world_id: str, timeline_id: str, limit: int = Query(default=240, le=2000)) -> dict[str, Any]:
    return {"telemetry": service.telemetry(timeline_id, limit)}


@app.get("/worlds/{world_id}/timelines/{timeline_id}/snapshots")
def snapshots(world_id: str, timeline_id: str) -> dict[str, Any]:
    return {"snapshots": service.snapshots(timeline_id)}


@app.get("/worlds/{world_id}/timelines/{timeline_id}/replay")
def replay(world_id: str, timeline_id: str, tick: int = Query(...)) -> dict[str, Any]:
    try:
        return service.replay(world_id, timeline_id, tick)
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator as a 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/worlds/{world_id}/timelines/{timeline_id}/state_at")
def state_at(world_id: str, timeline_id: str, tick: int = Query(...)) -> dict[str, Any]:
    try:
        return readmodel.world_summary(service.state_at(world_id, timeline_id, tick))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# -- live stream ------------------------------------------------------------------
@app.get("/worlds/{world_id}/timelines/{timeline_id}/stream")
async def stream(world_id: str, timeline_id: str) -> StreamingResponse:
    """Server-sent events: one summary per simulated tick batch, as the worker writes it."""

    async def generator():
        last_tick = -1
        while True:
            try:
                state = service.state(timeline_id)
                if state.meta.tick != last_tick:
                    last_tick = state.meta.tick
                    payload = readmodel.world_summary(state)
                    yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                else:
                    yield ": keep-alive\n\n"
            except FileNotFoundError:
                yield ": waiting for world\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(generator(), media_type="text/event-stream")
