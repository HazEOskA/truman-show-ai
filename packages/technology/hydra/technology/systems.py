"""Research system.

Progress requires existing knowledge, researchers, funding, infrastructure and time — and
still only succeeds with a probability. When a node unlocks, its effects change the economy
for real (energy efficiency lowers the energy in a recipe, productivity raises output per
worker), and the frontier extends: there is no maximum technology level.
"""

from __future__ import annotations

from hydra.companies.model import CompaniesState
from hydra.economy.model import EconomyState
from hydra.economy.money import transfer
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics
from hydra.kernel.clock import TICKS_PER_MONTH
from hydra.kernel.systems import Phase, SystemSpec

from .model import ResearchProject, TechField, TechNode, TechnologyState


class ResearchSystem:
    spec = SystemSpec(
        name="research",
        phase=Phase.SLOW,
        cadence_ticks=TICKS_PER_MONTH,
        priority=20,
        reads=("technology", "companies", "economy", "agents"),
        writes=("technology", "companies", "economy"),
        emits=(Topics.TECH_DISCOVERY, Topics.TECH_ADOPTION),
        description="Funded research projects, discoveries, adoption and frontier expansion.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        technology = ctx.state.domain(TechnologyState)
        companies = ctx.state.domain(CompaniesState)
        economy = ctx.state.domain(EconomyState)
        rng = ctx.rng("research")

        for project_id in sorted(technology.projects):
            project = technology.projects[project_id]
            if not project.active:
                continue
            node = technology.nodes.get(project.tech_id)
            company = companies.companies.get(project.organisation_id)
            if node is None or node.unlocked or company is None or company.bankrupt:
                project.active = False
                continue
            if not transfer(economy, company.account_id, economy.escrow_account_id, project.funding_per_month_minor):
                project.researchers = max(1, int(project.researchers * 0.8))
                continue
            project.invested_minor += project.funding_per_month_minor
            company.costs_minor += project.funding_per_month_minor

            points = project.researchers * project.progress_rate * (0.6 + company.technology) * rng.uniform(0.7, 1.35)
            node.progress = round(node.progress + points, 3)
            technology.research_points_total = round(technology.research_points_total + points, 3)

            if node.progress >= node.difficulty and rng.chance(0.65):
                self._unlock(ctx, technology, node, project, companies, economy)
                project.active = False

        self._diffuse(ctx, technology, companies)
        technology.tech_level = round(
            sum(1.0 for n in technology.nodes.values() if n.unlocked) / max(1, len(technology.nodes)), 5
        )
        ctx.telemetry.gauge("tech_level", technology.tech_level)
        ctx.telemetry.gauge("tech_unlocked", float(len(technology.unlocked_nodes())))

    def _unlock(self, ctx, technology: TechnologyState, node: TechNode, project: ResearchProject,
                companies: CompaniesState, economy: EconomyState) -> None:  # noqa: ANN001
        node.unlocked = True
        node.unlocked_tick = ctx.tick
        node.discovered_by = project.organisation_id
        node.adoption = 0.05
        technology.discoveries += 1
        company = companies.companies.get(project.organisation_id)
        if company is not None:
            company.technology = round(min(1.0, company.technology + 0.08), 4)
            company.reputation = round(min(1.0, company.reputation + 0.05), 4)
        ctx.emit(
            Topics.TECH_DISCOVERY,
            "discovery",
            actor=project.organisation_id,
            target=node.tech_id,
            payload={"name": node.name, "field": node.field_name.value, "effects": node.effects},
            inputs=ImportanceInputs(
                people_affected=8_000,
                economic_impact=project.invested_minor * 4,
                political_impact=0.2,
                novelty=0.95,
            ),
        )
        self._extend_frontier(technology, node, ctx)

    @staticmethod
    def _extend_frontier(technology: TechnologyState, node: TechNode, ctx) -> None:  # noqa: ANN001
        """Every discovery opens the next question. The graph is never finished."""

        technology.next_node_index += 1
        rng = ctx.rng("frontier", node.tech_id)
        new_id = f"tech_frontier_{technology.next_node_index:04d}"
        technology.nodes[new_id] = TechNode(
            tech_id=new_id,
            name=f"{node.name} II",
            field_name=node.field_name,
            difficulty=round(node.difficulty * rng.uniform(1.3, 2.1), 2),
            prerequisites=[node.tech_id],
            effects={key: round(value * rng.uniform(0.8, 1.6), 4) for key, value in node.effects.items()},
            frontier=True,
        )

    @staticmethod
    def _diffuse(ctx, technology: TechnologyState, companies: CompaniesState) -> None:  # noqa: ANN001
        economy = ctx.state.domain(EconomyState)
        for tech_id in sorted(technology.nodes):
            node = technology.nodes[tech_id]
            if not node.unlocked or node.adoption >= 0.99:
                continue
            previous = node.adoption
            node.adoption = round(min(1.0, node.adoption + 0.04 + node.adoption * 0.12), 5)
            gain = node.adoption - previous
            if gain <= 0:
                continue
            for key, magnitude in node.effects.items():
                delta = magnitude * gain
                if key == "productivity":
                    for company in companies.active():
                        company.productivity = round(min(4.0, company.productivity * (1.0 + delta * 0.5)), 5)
                elif key == "energy_efficiency":
                    for recipe in economy.recipes.values():
                        recipe.energy_kwh = round(max(0.0, recipe.energy_kwh * (1.0 - delta * 0.5)), 6)
                elif key == "food_yield":
                    recipe = economy.recipes.get("grain")
                    if recipe is not None:
                        recipe.inputs["water"] = round(max(0.05, recipe.inputs.get("water", 0.3) * (1.0 - delta * 0.4)), 6)
            if previous < 0.5 <= node.adoption:
                ctx.emit(
                    Topics.TECH_ADOPTION,
                    "technology_adopted",
                    target=node.tech_id,
                    payload={"name": node.name, "adoption": node.adoption},
                    importance=0.3,
                )
