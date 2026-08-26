"""Simulation clock.

A tick is ten simulated minutes. The calendar is regular on purpose: 12 months of 30 days.
Irregular real-world calendars add nothing to the simulation but break arithmetic that many
subsystems rely on (monthly cadences, wage cycles, tax periods).
"""

from __future__ import annotations

from dataclasses import dataclass

TICK_MINUTES = 10
TICKS_PER_HOUR = 60 // TICK_MINUTES
TICKS_PER_DAY = 24 * TICKS_PER_HOUR
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
TICKS_PER_MONTH = TICKS_PER_DAY * DAYS_PER_MONTH
TICKS_PER_YEAR = TICKS_PER_MONTH * MONTHS_PER_YEAR
DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True, slots=True)
class SimTime:
    tick: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    day_of_week: int
    day_of_year: int

    @property
    def is_weekend(self) -> bool:
        return self.day_of_week >= 5

    @property
    def minutes_of_day(self) -> int:
        return self.hour * 60 + self.minute

    def label(self) -> str:
        return f"Y{self.year}-M{self.month:02d}-D{self.day:02d} {self.hour:02d}:{self.minute:02d}"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.label()


class SimClock:
    """Pure function from tick to calendar position."""

    __slots__ = ("epoch_year",)

    def __init__(self, epoch_year: int = 0) -> None:
        self.epoch_year = epoch_year

    def at(self, tick: int) -> SimTime:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        minute_of_day = (tick % TICKS_PER_DAY) * TICK_MINUTES
        total_days = tick // TICKS_PER_DAY
        year = self.epoch_year + total_days // DAYS_PER_YEAR
        day_of_year = total_days % DAYS_PER_YEAR
        month = day_of_year // DAYS_PER_MONTH + 1
        day = day_of_year % DAYS_PER_MONTH + 1
        return SimTime(
            tick=tick,
            year=year,
            month=month,
            day=day,
            hour=minute_of_day // 60,
            minute=minute_of_day % 60,
            day_of_week=total_days % 7,
            day_of_year=day_of_year,
        )

    @staticmethod
    def ticks_from_hours(hours: float) -> int:
        return int(round(hours * TICKS_PER_HOUR))

    @staticmethod
    def start_of_day(tick: int) -> int:
        return tick - (tick % TICKS_PER_DAY)

    @staticmethod
    def tick_of_day(tick: int) -> int:
        return tick % TICKS_PER_DAY

    @staticmethod
    def tick_at_hour(tick: int, hour: float) -> int:
        """First tick at or after ``hour`` on the day that contains ``tick``."""

        return SimClock.start_of_day(tick) + int(round(hour * TICKS_PER_HOUR))
