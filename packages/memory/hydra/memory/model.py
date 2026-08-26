"""Layered agent memory (spec section 10).

Nobody stores a life as raw tokens. Memory here is structured events with salience, which
decay, consolidate into summaries during sleep, and are retrieved by relevance — the same
shape a human uses when they remember "prices went up last month" but not which afternoon.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


class MemoryKind(str, enum.Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    RELATIONSHIP = "relationship"
    BELIEF = "belief"
    SUMMARY = "summary"


@dataclass(slots=True)
class MemoryItem:
    item_id: str
    kind: MemoryKind
    tick: int
    topic: str
    summary: str
    salience: float = 0.5
    valence: float = 0.0            # -1 painful .. +1 pleasant
    source: str = "observed"
    refs: list[str] = field(default_factory=list)     # event ids, person ids, fact ids
    tags: list[str] = field(default_factory=list)
    recall_count: int = 0
    last_recall_tick: int = 0


@dataclass(slots=True)
class AgentMemory:
    person_id: str
    working: list[MemoryItem] = field(default_factory=list)
    episodic: list[MemoryItem] = field(default_factory=list)
    semantic: dict[str, MemoryItem] = field(default_factory=dict)
    summaries: list[MemoryItem] = field(default_factory=list)
    last_consolidation_tick: int = 0
    forgotten: int = 0
    next_item_index: int = 0

    def new_id(self) -> str:
        self.next_item_index += 1
        return f"{self.person_id}_m{self.next_item_index:05d}"


@register_domain
@dataclass(slots=True)
class MemoryState(DomainState):
    DOMAIN: ClassVar[str] = "memory"

    memories: dict[str, AgentMemory] = field(default_factory=dict)
    total_items: int = 0
    total_forgotten: int = 0
    consolidations: int = 0

    def for_person(self, person_id: str) -> AgentMemory:
        memory = self.memories.get(person_id)
        if memory is None:
            memory = AgentMemory(person_id=person_id)
            self.memories[person_id] = memory
        return memory
