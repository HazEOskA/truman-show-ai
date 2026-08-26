"""Deterministic identifier helpers.

Ids are stable, sortable and human readable so an operator reading the Observatory, the
ledger and a database row is always looking at the same name for the same thing.
"""

from __future__ import annotations

import re

_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    return _SLUG.sub("_", text.strip().lower()).strip("_")


def make_id(prefix: str, index: int, width: int = 6) -> str:
    return f"{prefix}_{index:0{width}d}"


def person_id(index: int) -> str:
    return make_id("person", index)


def household_id(index: int) -> str:
    return make_id("household", index)


def company_id(index: int) -> str:
    return make_id("company", index, 4)


def building_id(index: int) -> str:
    return make_id("building", index, 5)


def cohort_id(district: str, age_band: str, income: str) -> str:
    return f"cohort_{slug(district)}_{age_band}_{income}"


def event_id(seq: int) -> str:
    return make_id("evt", seq, 9)


def fact_id(seq: int) -> str:
    return make_id("fact", seq, 9)
