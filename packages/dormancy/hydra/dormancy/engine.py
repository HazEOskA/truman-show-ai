"""Sleep and dormancy state machine (spec section 8).

The rule that shapes this module: **sleep is a skip, not a loop**. When an agent falls asleep
the kernel computes the wake tick and stops evaluating that agent entirely — no reasoning, no
LLM, no per-tick decisions. At wake, one aggregate resolution applies eight hours of recovery
and hands the agent a delta summary of what it missed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hydra.agents.model import Activity, Person, Tier
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR, SimClock
from hydra.kernel.config import DormancyConfig
from hydra.kernel.rng import DeterministicRng


@dataclass(slots=True)
class SleepSchedule:
    sleep_hour: float
    wake_hour: float

    def duration_hours(self) -> float:
        span = self.wake_hour - self.sleep_hour
        return span if span > 0 else span + 24.0


@dataclass(slots=True)
class DeltaSummary:
    """What an agent is told when it wakes up. Never the world state — only its own inbox."""

    person_id: str
    from_tick: int
    to_tick: int
    items: list[str] = field(default_factory=list)
    messages: int = 0
    top_importance: float = 0.0
    topics: dict[str, int] = field(default_factory=dict)

    def text(self) -> str:
        if not self.items:
            return "Nothing of note happened while you slept."
        return "During sleep: " + "; ".join(self.items[:6])


def schedule_for(person: Person, config: DormancyConfig, rng: DeterministicRng) -> SleepSchedule:
    """Stable per-person circadian rhythm — a night-shift worker keeps their hours."""

    jitter = rng.uniform(-config.sleep_hour_jitter, config.sleep_hour_jitter)
    chronotype = (person.personality.conscientiousness - 0.5) * 1.4
    sleep_hour = (config.sleep_hour + jitter - chronotype) % 24.0
    wake_hour = (config.wake_hour + jitter * 0.6 - chronotype) % 24.0
    return SleepSchedule(sleep_hour=round(sleep_hour, 3), wake_hour=round(wake_hour, 3))


def should_sleep(person: Person, schedule: SleepSchedule, hour: float) -> bool:
    if person.activity in (Activity.SLEEP, Activity.OFFSCREEN):
        return False
    if person.energy < 0.12:
        return True
    start, end = schedule.sleep_hour, schedule.wake_hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def wake_tick_for(tick: int, schedule: SleepSchedule) -> int:
    """First tick at or after the agent's wake hour, at least one hour ahead."""

    day_start = SimClock.start_of_day(tick)
    candidate = day_start + int(round(schedule.wake_hour * TICKS_PER_HOUR))
    if candidate <= tick + TICKS_PER_HOUR:
        candidate += TICKS_PER_DAY
    return candidate


def apply_sleep_recovery(person: Person, slept_ticks: int) -> None:
    """One aggregate update for the whole night, applied once at wake."""

    hours = slept_ticks / TICKS_PER_HOUR
    quality = max(0.2, 1.0 - person.stress * 0.5)
    person.energy = round(min(1.0, person.energy + 0.085 * hours * quality), 4)
    person.stress = round(max(0.0, person.stress - 0.045 * hours * quality), 4)
    person.health = round(min(1.0, person.health + 0.004 * hours * quality - 0.002 * (1.0 - quality)), 4)
    person.mood = round(min(1.0, max(0.0, person.mood + 0.02 * hours * quality - 0.01)), 4)
    person.needs.rest = round(min(1.0, person.needs.rest + 0.1 * hours * quality), 4)


def idle_decay(person: Person, hours: float) -> None:
    person.energy = round(max(0.0, person.energy - 0.015 * hours), 4)
    person.needs.rest = round(max(0.0, person.needs.rest - 0.02 * hours), 4)
    person.needs.food = round(max(0.0, person.needs.food - 0.03 * hours), 4)
    person.needs.social = round(max(0.0, person.needs.social - 0.012 * hours), 4)


def next_activity(person: Person, salience: float, config: DormancyConfig) -> Activity:
    """Activity level for an awake agent, from how much the world is asking of it."""

    if person.tier is Tier.PERSISTENT:
        return Activity.ACTIVE if salience >= config.light_idle_importance_threshold * 0.5 else Activity.LIGHT_IDLE
    if salience >= config.light_idle_importance_threshold:
        return Activity.ACTIVE
    if person.idle_days >= config.dormant_after_idle_days:
        return Activity.DORMANT
    return Activity.LIGHT_IDLE


def wake_reason(event_importance: float, personal: bool, config: DormancyConfig) -> str:
    if personal and event_importance >= config.wake_importance_threshold * 0.6:
        return "personal_event"
    if event_importance >= 0.8:
        return "danger"
    if event_importance >= config.wake_importance_threshold:
        return "world_event"
    return ""
