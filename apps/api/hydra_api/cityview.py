"""City View API: the projection, the frames, and the panels behind a click.

Three kinds of thing are served here, and they are served differently on purpose.

*The projection* is the city's ground plan. It never changes while a world runs, so it is
computed once, cached by its hash, and downloaded once per viewer.

*Frames* are what changed. One keyframe on connect, then deltas -- a fraction of a kilobyte
each when the city is quiet.

*Panels* are pulled, not pushed: a viewer who clicks a building or follows a person asks for
that one thing, rather than the stream carrying detail for five thousand people nobody is
looking at.

A note on where deltas are computed. The architecture called for the worker to build them,
on the reasoning that it is the only process holding two consecutive ticks. In the event the
API does it, from the live state it already reads, keeping the previous accumulated frame per
timeline in memory. That is strictly better for the property the original decision was
protecting: it moves frame building off the simulation process entirely, so watching the city
costs the world exactly nothing rather than a few milliseconds a tick. The cost is that
motion is only as fine-grained as the worker's live-state interval (``HYDRA_LIVE_EVERY_TICKS``,
one simulated hour by default); lower it for smoother movement and more state writes.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from hydra.agents.model import AgentsState
from hydra.companies.model import CompaniesState
from hydra.geography.model import GeographyState
from hydra.kernel.clock import SimClock
from hydra.kernel.state import WorldState
from hydra.spatial import ProjectionCache, from_geography
from hydra.viewmodel import (
    CityFrame,
    CityIndex,
    apply_delta,
    build_delta,
    build_index,
    build_keyframe,
    compute_layers,
    layer_catalogue,
    presence_of,
    projection_payload,
)
from hydra.viewmodel.presence import PresenceSource

router = APIRouter(prefix="/city", tags=["city"])

_projections = ProjectionCache(limit=4)
_indexes: dict[str, tuple[str, CityIndex]] = {}
_frames: dict[str, CityFrame] = {}

STREAM_POLL_SECONDS = 0.5


def _service():
    from .main import service

    return service


def _state(timeline_id: str) -> WorldState:
    try:
        return _service().state(timeline_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _index_for(state: WorldState) -> CityIndex:
    """Cached per timeline, rebuilt when the building roster changes."""

    geography = state.domain(GeographyState)
    signature = f"{len(geography.buildings)}:{geography.seed_city_id}"
    cached = _indexes.get(state.meta.timeline_id)
    if cached is None or cached[0] != signature:
        cached = (signature, build_index(geography))
        _indexes[state.meta.timeline_id] = cached
    return cached[1]


def _projection_for(state: WorldState):
    geography = state.domain(GeographyState)
    return _projections.get(from_geography(geography, seed=state.meta.seed))


# -- the ground plan --------------------------------------------------------------


@router.get("/{timeline_id}/projection")
def projection(timeline_id: str) -> dict[str, Any]:
    """The city's geometry. Stable for the life of a world; cache it hard."""

    state = _state(timeline_id)
    return projection_payload(_projection_for(state), _index_for(state))


# -- frames -----------------------------------------------------------------------


@router.get("/{timeline_id}/keyframe")
def keyframe(timeline_id: str) -> dict[str, Any]:
    state = _state(timeline_id)
    frame = build_keyframe(state, _index_for(state))
    _frames[timeline_id] = frame
    return frame.as_dict()


class FrameStream:
    """One viewer's place in the city's history.

    Holds the accumulated frame -- the keyframe brought up to date with every delta sent so
    far -- so the next delta can be measured against what this viewer actually has. Kept out
    of the endpoint so it can be tested without a socket: the interesting behaviour is
    *keyframe first, deltas after, keyframe again on resync*, and none of that is HTTP.
    """

    __slots__ = ("timeline_id", "resync_every", "accumulated", "last_tick", "last_key_tick")

    def __init__(self, timeline_id: str, resync_every: int = 600) -> None:
        self.timeline_id = timeline_id
        self.resync_every = resync_every
        self.accumulated: CityFrame | None = None
        self.last_tick = -1
        self.last_key_tick = -1

    def next_frame(self, state: WorldState) -> CityFrame | None:
        """The frame to send for this state, or ``None`` if the world has not moved."""

        tick = state.meta.tick
        if tick == self.last_tick:
            return None

        index = _index_for(state)
        stale = bool(self.resync_every) and (tick - self.last_key_tick) >= self.resync_every
        if self.accumulated is None or stale:
            frame = build_keyframe(state, index)
            self.accumulated = frame
            self.last_key_tick = tick
        else:
            frame = build_delta(state, self.accumulated, index)
            self.accumulated = apply_delta(self.accumulated, frame)

        self.last_tick = tick
        _frames[self.timeline_id] = self.accumulated
        return frame


@router.get("/{timeline_id}/stream")
async def stream(timeline_id: str, resync_every: int = Query(default=600, ge=0)) -> StreamingResponse:
    """Keyframe, then deltas.

    A keyframe is re-sent every ``resync_every`` ticks so a viewer who missed one -- a
    dropped connection, a backgrounded tab -- is never left drawing a city that has quietly
    drifted from the real one.
    """

    feed = FrameStream(timeline_id, resync_every)

    async def generator():
        while True:
            try:
                state = _state(timeline_id)
            except HTTPException:
                yield ": waiting for world\n\n"
                await asyncio.sleep(1.0)
                continue

            frame = feed.next_frame(state)
            if frame is None:
                yield ": keep-alive\n\n"
            else:
                yield f"data: {json.dumps(frame.as_dict(), separators=(',', ':'))}\n\n"
            await asyncio.sleep(STREAM_POLL_SECONDS)

    return StreamingResponse(generator(), media_type="text/event-stream")


# -- layers -----------------------------------------------------------------------


@router.get("/layers")
def layers() -> dict[str, Any]:
    """What can be switched on, and what each layer actually reads."""

    return {"layers": layer_catalogue()}


@router.get("/{timeline_id}/layers")
def layer_values(timeline_id: str, ids: str = Query(default="")) -> dict[str, Any]:
    state = _state(timeline_id)
    wanted = tuple(i for i in ids.split(",") if i)
    return {
        "tick": state.meta.tick,
        "catalogue": layer_catalogue(),
        "values": compute_layers(state, wanted),
    }


# -- panels -----------------------------------------------------------------------


@router.get("/{timeline_id}/building/{building_id}")
def building(timeline_id: str, building_id: str) -> dict[str, Any]:
    """What a viewer sees when they click a building."""

    state = _state(timeline_id)
    geography = state.domain(GeographyState)
    record = geography.buildings.get(building_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no building {building_id}")

    placement = _projection_for(state).buildings.get(building_id)
    district = geography.districts.get(record.district_id)
    agents = state.domain(AgentsState)
    tick = state.meta.tick

    inside = []
    for person in agents.people.values():
        if not person.alive:
            continue
        presence = presence_of(person, tick)
        if presence.building_id != building_id:
            continue
        inside.append(
            {
                "person_id": person.person_id,
                "name": person.name,
                "activity": person.activity.value,
                "tier": person.tier.value,
                "position_source": presence.source.value,
            }
        )
    inside.sort(key=lambda p: p["person_id"])

    owner = state.domain(CompaniesState).companies.get(record.owner_id) if record.owner_id else None
    return {
        "building_id": building_id,
        "name": record.name,
        "kind": record.kind.value,
        "district": {"id": record.district_id, "name": district.name if district else ""},
        "capacity": record.capacity,
        "occupancy": record.occupancy,
        "condition": round(record.condition, 4),
        "value": round(record.value_minor / 100.0, 2),
        "owner": {"id": record.owner_id, "name": owner.name if owner else ""},
        "address": placement.address if placement else "",
        "floors": placement.floors if placement else 0,
        "centre": list(placement.centre) if placement else None,
        "people_here": inside[:80],
        "people_here_total": len(inside),
        "observed_here": sum(1 for p in inside if p["position_source"] == PresenceSource.OBSERVED.value),
    }


@router.get("/{timeline_id}/agent/{person_id}")
def agent(timeline_id: str, person_id: str) -> dict[str, Any]:
    """The click panel, and what FOLLOW AGENT reads each tick."""

    state = _state(timeline_id)
    agents = state.domain(AgentsState)
    person = agents.people.get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"no person {person_id}")

    tick = state.meta.tick
    presence = presence_of(person, tick)
    projection = _projection_for(state)
    geography = state.domain(GeographyState)

    def place(building_id: str) -> dict[str, Any] | None:
        if not building_id:
            return None
        record = geography.buildings.get(building_id)
        placement = projection.buildings.get(building_id)
        return {
            "building_id": building_id,
            "name": record.name if record else "",
            "kind": record.kind.value if record else "",
            "address": placement.address if placement else "",
            "centre": list(placement.centre) if placement else None,
        }

    return {
        "person_id": person.person_id,
        "name": person.name,
        "tier": person.tier.value,
        "age": round(person.age_years, 1),
        "activity": person.activity.value,
        "awake": person.is_awake(),
        "employment": person.employment.value,
        "occupation": person.occupation,
        "employer_id": person.employer_id,
        "wage": round(person.wage_minor / 100.0, 2),
        "mood": round(person.mood, 3),
        "energy": round(person.energy, 3),
        "stress": round(person.stress, 3),
        "health": round(person.health, 3),
        "needs": {
            "food": round(person.needs.food, 3),
            "rest": round(person.needs.rest, 3),
            "safety": round(person.needs.safety, 3),
            "social": round(person.needs.social, 3),
        },
        "goals": [
            {"label": g.label, "kind": g.kind, "priority": round(g.priority, 3),
             "progress": round(g.progress, 3)}
            for g in person.goals[:6]
        ],
        "last_action": person.last_action,
        "recent_actions": list(person.recent_actions[-8:]),
        "position": {
            "building_id": presence.building_id,
            "source": presence.source.value,
            "district_id": person.district_id,
        },
        "home": place(person.home_building_id),
        "work": place(person.work_building_id),
        "at": place(presence.building_id),
        "sim_time": SimClock().at(tick).label(),
        "tick": tick,
    }


@router.get("/{timeline_id}/events")
def events(
    timeline_id: str,
    limit: int = Query(default=60, ge=1, le=400),
    min_importance: float = Query(default=0.0, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Recent events, anchored to somewhere on the map.

    Hydra's events carry ``location``, and ``location`` is a district id -- every system that
    sets it sets it to one. So an event knows the quarter it happened in and almost never the
    building. This endpoint resolves the finest anchor each event actually supports and says
    which it got: a building point when something names a building, the quarter's centre
    otherwise, and ``none`` when the event is about the city as a whole. Nothing is dropped,
    and nothing is given a position it did not earn -- an event pinned to an invented address
    would be the City View inventing history.
    """

    state = _state(timeline_id)
    store = _service().store
    projection = _projection_for(state)
    geography = state.domain(GeographyState)
    agents = state.domain(AgentsState)

    records = store.read_events(
        timeline_id, limit=limit, min_importance=min_importance, newest_first=True
    )

    out = []
    for event in records:
        building_id = _building_named_by(event, geography)
        district_id = _district_of(event, building_id, geography, agents)

        placement = projection.buildings.get(building_id) if building_id else None
        if placement is not None:
            anchor, anchor_kind = list(placement.centre), "building"
        elif district_id and district_id in projection.districts:
            anchor, anchor_kind = list(projection.districts[district_id].centre), "district"
        else:
            anchor, anchor_kind = None, "none"

        out.append(
            {
                "event_id": event.event_id,
                "tick": event.tick,
                "sim_time": event.sim_time,
                "topic": event.topic,
                "action": event.action,
                "headline": event.headline(),
                "importance": round(event.importance, 3),
                "actor": event.actor,
                "target": event.target,
                "district_id": district_id,
                "building_id": building_id,
                "anchor": anchor,
                "anchor_kind": anchor_kind,
                "causes": list(event.causes),
                "effects": list(event.effects),
            }
        )
    return {"tick": state.meta.tick, "events": out}


def _building_named_by(event, geography: GeographyState) -> str:
    """The building an event mentions, if any. Checked, never assumed."""

    for candidate in (event.payload.get("building_id"), event.target):
        if candidate and str(candidate) in geography.buildings:
            return str(candidate)
    return ""


def _district_of(event, building_id: str, geography: GeographyState, agents: AgentsState) -> str:
    if event.location and event.location in geography.districts:
        return str(event.location)
    if building_id:
        record = geography.buildings.get(building_id)
        if record:
            return record.district_id
    person = agents.people.get(str(event.actor or ""))
    return person.district_id if person else ""
