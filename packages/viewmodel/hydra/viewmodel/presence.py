"""Where people are, and how sure we are about it.

This is the most easily abused module in the City View, so it is the most explicit.

Hydra's agents do not carry a tracked position. ``location_building_id`` is a by-product of
whichever action a person last took, and it is always *set* -- it just stops being refreshed.
Measured on a running world at two in the afternoon, with 3,065 people employed, 383 are
recorded at their workplace and 4,520 of 4,920 are recorded at home. The simulation does not
model the working day as a physical fact: production happens in the companies subsystem, and
nobody has to walk anywhere for it.

That leaves the City View with two ways to be wrong. Drawn literally, Hydra is a ghost town
at noon while its factories run at full output. Drawn creatively, it invents a second,
prettier world -- which is the one thing it must never do.

So every position is labelled with where it came from:

``OBSERVED``  world state's recorded location, used as-is. This is what the world says.
``DERIVED``   we substituted a position, because the recorded one contradicts the rest of
              the person's state. There is exactly one such rule, below.
``UNKNOWN``   nothing to go on. The person is not drawn rather than guessed at.

**The one override.** An employed, awake person during working hours whose recorded location
is their own home is showing a location that has not been refreshed since they went to bed.
For them, and only them, the view shows their workplace and tags it ``DERIVED``. Every other
recorded location is trusted, including "somewhere that is neither home nor work" -- that one
came from an action the person actually took.

The counts ride along in :class:`PresenceReport`, so a viewer can always see how much of the
crowd is inference, and the renderer can grey it down or hide it entirely.

If you are tempted to add "and then they go to a cafe", stop: that is a simulation feature,
and it belongs in the agents package where the rest of the world can react to it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from hydra.agents.model import Activity, AgentsState, Employment, Person
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR

#: Hours during which an employed person is taken to be at work when state does not say.
WORK_START_HOUR = 8
WORK_END_HOUR = 17


class PresenceSource(str, enum.Enum):
    OBSERVED = "observed"
    DERIVED = "derived"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Presence:
    person_id: str
    building_id: str
    source: PresenceSource
    activity: Activity
    district_id: str = ""

    @property
    def is_fact(self) -> bool:
        return self.source is PresenceSource.OBSERVED


@dataclass(slots=True)
class PresenceReport:
    """Counts the UI shows so a viewer knows how much of the crowd is inferred."""

    observed: int = 0
    derived: int = 0
    unknown: int = 0

    @property
    def total(self) -> int:
        return self.observed + self.derived + self.unknown

    @property
    def observed_share(self) -> float:
        return self.observed / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "observed": self.observed,
            "derived": self.derived,
            "unknown": self.unknown,
            "observed_share": round(self.observed_share, 4),
        }


def hour_of(tick: int) -> int:
    return (tick % TICKS_PER_DAY) // TICKS_PER_HOUR


def is_working_hour(tick: int) -> bool:
    return WORK_START_HOUR <= hour_of(tick) < WORK_END_HOUR


WORKING_EMPLOYMENT = frozenset((Employment.EMPLOYED, Employment.PUBLIC, Employment.SELF_EMPLOYED))
ASLEEP = frozenset((Activity.SLEEP, Activity.DORMANT))

#: Wire codes, matching :data:`hydra.viewmodel.frames.SOURCE_CODES`.
OBSERVED_CODE = 0
DERIVED_CODE = 1
UNKNOWN_CODE = 2


def resolve(person: Person, working_hour: bool) -> tuple[str, int]:
    """``(building_id, source_code)`` for one person, allocating nothing.

    This is the hot path: it runs once per living person per frame, so it takes the working
    hour as an argument rather than deriving it from the tick five thousand times, and it
    returns a tuple rather than building an object the caller will immediately unpack.
    :func:`presence_of` is the same logic with a readable return type.
    """

    location = person.location_building_id
    if location:
        if (
            working_hour
            and location == person.home_building_id
            and person.employment in WORKING_EMPLOYMENT
            and person.activity not in ASLEEP
            and person.activity is not Activity.OFFSCREEN
        ):
            work = person.work_building_id
            if work and work != location:
                return (work, DERIVED_CODE)
        return (location, OBSERVED_CODE)

    inferred = _infer(person, working_hour)
    return (inferred, DERIVED_CODE) if inferred else ("", UNKNOWN_CODE)


def presence_of(person: Person, tick: int) -> Presence:
    """Resolve one person's position, and say where the answer came from."""

    building_id, code = resolve(person, is_working_hour(tick))
    source = (PresenceSource.OBSERVED, PresenceSource.DERIVED, PresenceSource.UNKNOWN)[code]
    return Presence(person.person_id, building_id, source, person.activity, person.district_id)


def _infer(person: Person, working_hour: bool) -> str:
    """Used only when state records no location at all.

    Asleep means home. A working person in working hours means work. Everything else means
    home, because home is the only other building the simulation has ever associated with
    them -- not because we know they are there.
    """

    if person.activity in ASLEEP:
        return person.home_building_id
    at_work = (
        working_hour
        and person.work_building_id
        and person.employment in WORKING_EMPLOYMENT
        and person.activity is not Activity.OFFSCREEN
    )
    return person.work_building_id if at_work else person.home_building_id


def resolve_all(agents: AgentsState, tick: int) -> tuple[list[Presence], PresenceReport]:
    """Presence for every living individual, plus the honesty counters."""

    report = PresenceReport()
    out: list[Presence] = []
    for person_id in sorted(agents.people):
        person = agents.people[person_id]
        if not person.alive:
            continue
        presence = presence_of(person, tick)
        if presence.source is PresenceSource.OBSERVED:
            report.observed += 1
        elif presence.source is PresenceSource.DERIVED:
            report.derived += 1
        else:
            report.unknown += 1
        out.append(presence)
    return (out, report)
