"""Research graph (spec section 19).

Technology never appears by decree. A node unlocks only when prerequisite knowledge exists
and researchers, funding, infrastructure, experiments, time and luck line up. There is no
maximum tech level: the graph grows by extending frontier nodes.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


class TechField(str, enum.Enum):
    ENERGY = "energy"
    MATERIALS = "materials"
    COMPUTING = "computing"
    MEDICINE = "medicine"
    AGRICULTURE = "agriculture"
    TRANSPORT = "transport"
    SOCIAL = "social"


@dataclass(slots=True)
class TechNode:
    tech_id: str
    name: str
    field_name: TechField
    difficulty: float                      # research-points required
    prerequisites: list[str] = field(default_factory=list)
    progress: float = 0.0
    unlocked: bool = False
    unlocked_tick: int | None = None
    discovered_by: str = ""
    effects: dict[str, float] = field(default_factory=dict)
    adoption: float = 0.0
    frontier: bool = False


@dataclass(slots=True)
class ResearchProject:
    project_id: str
    tech_id: str
    organisation_id: str
    lead_researcher_id: str = ""
    researchers: int = 1
    funding_per_month_minor: int = 0
    invested_minor: int = 0
    started_tick: int = 0
    progress_rate: float = 1.0
    active: bool = True


@register_domain
@dataclass(slots=True)
class TechnologyState(DomainState):
    DOMAIN: ClassVar[str] = "technology"

    nodes: dict[str, TechNode] = field(default_factory=dict)
    projects: dict[str, ResearchProject] = field(default_factory=dict)
    tech_level: float = 0.5
    research_points_total: float = 0.0
    discoveries: int = 0
    next_project_index: int = 0
    next_node_index: int = 0

    def available(self) -> list[TechNode]:
        return [
            node
            for node in self.nodes.values()
            if not node.unlocked and all(self.nodes[p].unlocked for p in node.prerequisites if p in self.nodes)
        ]

    def unlocked_nodes(self) -> list[TechNode]:
        return [n for n in self.nodes.values() if n.unlocked]
