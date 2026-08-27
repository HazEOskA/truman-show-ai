"""City frames: what changed in the city since the last one.

The Observatory's existing dashboards re-read the whole world every second -- thirty
megabytes of it. That is fine for a page of numbers and hopeless for a city that redraws
itself continuously, so the City View gets a different shape of data:

* one **keyframe**, complete, sent when a viewer connects or resyncs,
* then **deltas**, each carrying only the agents, buildings and districts that moved.

Frames are columnar. Parallel arrays of small integers compress and parse far better than
an array of objects, and the building an agent stands in is an index into the shared
ordering rather than a twenty-character id.

Frames are built by the worker, because it is the only process that holds tick *t* and
tick *t+1* in memory at once. Everything here is therefore written to be cheap: one pass
over the living, no geometry, no layer maths, nothing that would put the city's appearance
on the critical path of the simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hydra.agents.model import Activity, AgentsState, Tier
from hydra.geography.model import GeographyState
from hydra.kernel.clock import SimClock
from hydra.kernel.state import WorldState

from .index import CityIndex, build_index
from .presence import ASLEEP as _ASLEEP
from .presence import PresenceReport, PresenceSource, is_working_hour, resolve

#: Wire codes. Order is part of the protocol -- append, never reorder.
ACTIVITY_CODES: tuple[str, ...] = (
    Activity.ACTIVE.value,
    Activity.LIGHT_IDLE.value,
    Activity.SLEEP.value,
    Activity.DORMANT.value,
    Activity.OFFSCREEN.value,
)
SOURCE_CODES: tuple[str, ...] = (
    PresenceSource.OBSERVED.value,
    PresenceSource.DERIVED.value,
    PresenceSource.UNKNOWN.value,
)
TIER_CODES: tuple[str, ...] = (Tier.PERSISTENT.value, Tier.LIGHTWEIGHT.value, Tier.COHORT.value)

# Keyed by the enum *members*, not their strings: ``SomeEnum.value`` goes through a
# descriptor and cost 13% of frame time when it ran three times per person per frame.
_ACTIVITY_INDEX = {
    Activity.ACTIVE: 0,
    Activity.LIGHT_IDLE: 1,
    Activity.SLEEP: 2,
    Activity.DORMANT: 3,
    Activity.OFFSCREEN: 4,
}
_TIER_INDEX = {Tier.PERSISTENT: 0, Tier.LIGHTWEIGHT: 1, Tier.COHORT: 2}

#: ``(building, source, activity, tier)``. A tuple, not an object: at five thousand people a
#: frame the allocation showed up in the profile, and nothing here needs behaviour.
AgentRow = tuple[int, int, int, int]


@dataclass(slots=True)
class CityFrame:
    """A keyframe or a delta. ``kind`` says which; the fields mean the same in both."""

    kind: str                       # "keyframe" | "delta"
    tick: int
    timeline_id: str
    sim_time: str = ""
    #: person_id -> row. In a delta, only the people who changed.
    agents: dict[str, AgentRow] = field(default_factory=dict)
    #: people who died or left since the previous frame.
    gone: list[str] = field(default_factory=list)
    #: building index -> [occupancy, awake, condition_milli]
    buildings: dict[int, tuple[int, int, int]] = field(default_factory=dict)
    #: district index -> [population, asleep_share_milli, unrest_milli, power_milli]
    districts: dict[int, tuple[int, int, int, int]] = field(default_factory=dict)
    presence: PresenceReport = field(default_factory=PresenceReport)
    cohort_population: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Columnar wire form. Keys are short because they repeat every tick."""

        ids = sorted(self.agents)
        return {
            "kind": self.kind,
            "tick": self.tick,
            "timeline_id": self.timeline_id,
            "sim_time": self.sim_time,
            "agents": {
                "id": ids,
                "b": [self.agents[i][0] for i in ids],
                "s": [self.agents[i][1] for i in ids],
                "a": [self.agents[i][2] for i in ids],
                "t": [self.agents[i][3] for i in ids],
            },
            "gone": list(self.gone),
            "buildings": {
                "i": sorted(self.buildings),
                "occupancy": [self.buildings[i][0] for i in sorted(self.buildings)],
                "awake": [self.buildings[i][1] for i in sorted(self.buildings)],
                "condition": [self.buildings[i][2] for i in sorted(self.buildings)],
            },
            "districts": {
                "i": sorted(self.districts),
                "population": [self.districts[i][0] for i in sorted(self.districts)],
                "asleep": [self.districts[i][1] for i in sorted(self.districts)],
                "unrest": [self.districts[i][2] for i in sorted(self.districts)],
                "power": [self.districts[i][3] for i in sorted(self.districts)],
            },
            "presence": self.presence.as_dict(),
            "cohort_population": self.cohort_population,
            "codes": {"activity": ACTIVITY_CODES, "source": SOURCE_CODES, "tier": TIER_CODES},
        }


def build_keyframe(state: WorldState, index: CityIndex | None = None) -> CityFrame:
    """The complete current state of the city, for a viewer who has just arrived."""

    return _build(state, index, previous=None, kind="keyframe")


def build_delta(state: WorldState, previous: CityFrame, index: CityIndex | None = None) -> CityFrame:
    """Only what moved since ``previous``.

    ``previous`` must be an *accumulated* frame -- a keyframe brought up to date with every
    delta since -- not the last delta on its own. :func:`apply_delta` maintains that.
    """

    return _build(state, index, previous=previous, kind="delta")


def _build(
    state: WorldState, index: CityIndex | None, previous: CityFrame | None, kind: str
) -> CityFrame:
    geography = state.domain(GeographyState)
    agents = state.domain(AgentsState)
    idx = index or build_index(geography)
    tick = state.meta.tick

    frame = CityFrame(
        kind=kind,
        tick=tick,
        timeline_id=state.meta.timeline_id,
        sim_time=SimClock().at(tick).label(),
    )

    # One pass over the living. This runs on the worker's clock, so everything the frame
    # needs -- presence, who is awake where, the per-district sleep share -- is counted here
    # rather than in a second and third walk over five thousand people.
    awake_in: dict[int, int] = {}
    asleep_in: dict[str, int] = {}
    heads_in: dict[str, int] = {}
    rows: dict[str, AgentRow] = {}
    previous_rows = previous.agents if previous else {}
    changed: dict[str, AgentRow] = {}
    counts = [0, 0, 0]                       # observed, derived, unknown

    working_hour = is_working_hour(tick)     # constant for the frame; not per person
    building_pos = idx.building_positions
    resolve_one = resolve

    for person_id, person in agents.people.items():
        if not person.alive:
            continue
        building_id, source = resolve_one(person, working_hour)
        counts[source] += 1

        building = building_pos.get(building_id, -1) if building_id else -1
        activity = person.activity
        row = (
            building,
            source,
            _ACTIVITY_INDEX.get(activity, 0),
            _TIER_INDEX.get(person.tier, 1),
        )
        rows[person_id] = row
        if previous is not None and previous_rows.get(person_id) != row:
            changed[person_id] = row

        district = person.district_id
        heads_in[district] = heads_in.get(district, 0) + 1
        if activity in _ASLEEP:
            asleep_in[district] = asleep_in.get(district, 0) + 1
        elif building >= 0:
            awake_in[building] = awake_in.get(building, 0) + 1

    frame.presence = PresenceReport(observed=counts[0], derived=counts[1], unknown=counts[2])
    frame.cohort_population = agents.cohort_population()

    if previous is None:
        frame.agents = rows
    else:
        frame.agents = changed
        frame.gone = sorted(set(previous_rows) - set(rows))

    _fill_buildings(frame, geography, idx, awake_in, previous)
    _fill_districts(frame, geography, idx, asleep_in, heads_in, previous)
    return frame


def _fill_buildings(
    frame: CityFrame,
    geography: GeographyState,
    idx: CityIndex,
    awake_in: dict[int, int],
    previous: CityFrame | None,
) -> None:
    for position, building_id in enumerate(idx.buildings):
        building = geography.buildings.get(building_id)
        if building is None:
            continue
        row = (
            int(building.occupancy),
            awake_in.get(position, 0),
            int(round(building.condition * 1000)),
        )
        if previous is None or previous.buildings.get(position) != row:
            frame.buildings[position] = row


def _fill_districts(
    frame: CityFrame,
    geography: GeographyState,
    idx: CityIndex,
    asleep: dict[str, int],
    heads: dict[str, int],
    previous: CityFrame | None,
) -> None:
    for position, district_id in enumerate(idx.districts):
        district = geography.districts.get(district_id)
        if district is None:
            continue
        head = heads.get(district_id, 0)
        share = asleep.get(district_id, 0) / head if head else 0.0
        row = (
            int(district.population),
            int(round(share * 1000)),
            int(round(district.unrest * 1000)),
            int(round(district.power_reliability * 1000)),
        )
        if previous is None or previous.districts.get(position) != row:
            frame.districts[position] = row


def apply_delta(base: CityFrame, delta: CityFrame) -> CityFrame:
    """Fold a delta into an accumulated frame.

    Used by the worker to keep its running picture, and by tests to prove that keyframe +
    deltas equals the keyframe you would have built at that tick. If that ever stops being
    true, viewers drift away from the world without anyone noticing.
    """

    merged = CityFrame(
        kind="keyframe",
        tick=delta.tick,
        timeline_id=delta.timeline_id or base.timeline_id,
        sim_time=delta.sim_time or base.sim_time,
        agents=dict(base.agents),
        buildings=dict(base.buildings),
        districts=dict(base.districts),
        presence=delta.presence,
        cohort_population=delta.cohort_population,
    )
    merged.agents.update(delta.agents)
    for person_id in delta.gone:
        merged.agents.pop(person_id, None)
    merged.buildings.update(delta.buildings)
    merged.districts.update(delta.districts)
    return merged


def frame_from_dict(payload: dict[str, Any]) -> CityFrame:
    """Rebuild a frame from its wire form. The stream and the tests both need this."""

    agents_block = payload.get("agents") or {}
    ids = list(agents_block.get("id", ()))
    rows = {
        person_id: (
            agents_block["b"][i],
            agents_block["s"][i],
            agents_block["a"][i],
            agents_block["t"][i],
        )
        for i, person_id in enumerate(ids)
    }
    buildings_block = payload.get("buildings") or {}
    building_positions = list(buildings_block.get("i", ()))
    buildings = {
        position: (
            buildings_block["occupancy"][i],
            buildings_block["awake"][i],
            buildings_block["condition"][i],
        )
        for i, position in enumerate(building_positions)
    }
    districts_block = payload.get("districts") or {}
    district_positions = list(districts_block.get("i", ()))
    districts = {
        position: (
            districts_block["population"][i],
            districts_block["asleep"][i],
            districts_block["unrest"][i],
            districts_block["power"][i],
        )
        for i, position in enumerate(district_positions)
    }
    presence_block = payload.get("presence") or {}
    return CityFrame(
        kind=payload.get("kind", "delta"),
        tick=int(payload.get("tick", 0)),
        timeline_id=payload.get("timeline_id", ""),
        sim_time=payload.get("sim_time", ""),
        agents=rows,
        gone=list(payload.get("gone", ())),
        buildings=buildings,
        districts=districts,
        presence=PresenceReport(
            observed=int(presence_block.get("observed", 0)),
            derived=int(presence_block.get("derived", 0)),
            unknown=int(presence_block.get("unknown", 0)),
        ),
        cohort_population=int(payload.get("cohort_population", 0)),
    )
