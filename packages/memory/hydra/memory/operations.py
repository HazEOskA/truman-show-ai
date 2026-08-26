"""Memory operations: record, decay, consolidate, recall.

These are plain functions over :class:`AgentMemory` so that any system (perception, sleep,
social interaction) can use them without owning the memory domain.
"""

from __future__ import annotations

from hydra.kernel.clock import TICKS_PER_DAY

from .model import AgentMemory, MemoryItem, MemoryKind, MemoryState


def record(
    state: MemoryState,
    person_id: str,
    *,
    tick: int,
    topic: str,
    summary: str,
    kind: MemoryKind = MemoryKind.EPISODIC,
    salience: float = 0.5,
    valence: float = 0.0,
    source: str = "observed",
    refs: list[str] | None = None,
    tags: list[str] | None = None,
    working_limit: int = 12,
) -> MemoryItem:
    memory = state.for_person(person_id)
    item = MemoryItem(
        item_id=memory.new_id(),
        kind=kind,
        tick=tick,
        topic=topic,
        summary=summary,
        salience=min(1.0, max(0.0, salience)),
        valence=max(-1.0, min(1.0, valence)),
        source=source,
        refs=list(refs or []),
        tags=list(tags or []),
    )
    if kind is MemoryKind.SEMANTIC:
        memory.semantic[topic] = item
    else:
        memory.working.append(item)
        overflow = len(memory.working) - working_limit
        if overflow > 0:
            # Working memory spills into episodic in arrival order.
            memory.episodic.extend(memory.working[:overflow])
            del memory.working[:overflow]
    state.total_items += 1
    return item


def decay(memory: AgentMemory, tick: int, per_day: float, floor: float = 0.02) -> int:
    """Forgetting. Salience falls with time; what falls below the floor is gone."""

    forgotten = 0
    keep: list[MemoryItem] = []
    for item in memory.episodic:
        days = max(0.0, (tick - item.tick) / TICKS_PER_DAY)
        item.salience = round(item.salience * (1.0 - per_day) ** max(1.0, days / 7.0), 6)
        if item.salience < floor and item.recall_count == 0:
            forgotten += 1
            continue
        keep.append(item)
    memory.episodic = keep
    memory.forgotten += forgotten
    return forgotten


def consolidate(
    memory: AgentMemory,
    tick: int,
    *,
    episodic_limit: int = 220,
    per_day_decay: float = 0.012,
) -> MemoryItem | None:
    """Sleep-time consolidation: working → episodic, oldest episodic → one summary."""

    memory.episodic.extend(memory.working)
    memory.working.clear()
    decay(memory, tick, per_day_decay)
    summary_item: MemoryItem | None = None
    overflow = len(memory.episodic) - episodic_limit
    if overflow > 0:
        oldest = memory.episodic[:overflow]
        del memory.episodic[:overflow]
        topics: dict[str, int] = {}
        valence = 0.0
        for item in oldest:
            topics[item.topic] = topics.get(item.topic, 0) + 1
            valence += item.valence
        ranked = sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        label = ", ".join(f"{topic}×{count}" for topic, count in ranked)
        summary_item = MemoryItem(
            item_id=memory.new_id(),
            kind=MemoryKind.SUMMARY,
            tick=tick,
            topic="life",
            summary=f"period compressed: {label}",
            salience=0.4,
            valence=round(valence / max(1, len(oldest)), 6),
            source="consolidation",
            refs=[],
            tags=["compressed"],
        )
        memory.summaries.append(summary_item)
        del memory.summaries[:-40]
    memory.last_consolidation_tick = tick
    return summary_item


def recall(memory: AgentMemory, topic: str, tick: int, limit: int = 5) -> list[MemoryItem]:
    """Relevance = topical match × salience × recency."""

    scored: list[tuple[float, MemoryItem]] = []
    for item in (*memory.working, *memory.episodic, *memory.semantic.values()):
        if topic and topic not in item.topic and topic not in item.tags:
            continue
        recency = 1.0 / (1.0 + max(0, tick - item.tick) / (TICKS_PER_DAY * 30.0))
        scored.append((item.salience * recency, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].item_id))
    picked = [item for _, item in scored[:limit]]
    for item in picked:
        item.recall_count += 1
        item.last_recall_tick = tick
        item.salience = min(1.0, item.salience + 0.03)
    return picked
