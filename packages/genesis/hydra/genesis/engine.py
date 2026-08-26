"""Genesis Engine.

``GENESIS → SEAL → AUTONOMOUS WORLD``. Genesis builds a complete, consistent world from one
master seed. Sealing freezes Timeline Zero: from that moment the operator may read, observe,
pause, replay, analyse and fork, but never retroactively edit what happened.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.agents.model import AgentsState
from hydra.companies.model import CompaniesState
from hydra.culture.model import CultureState
from hydra.economy.model import EconomyState
from hydra.geography.model import GeographyState
from hydra.government.model import GovernmentState
from hydra.history.state import HistoryState
from hydra.information.model import Fact, KnowledgeState, KnownFact, Source
from hydra.information.net import NetState
from hydra.kernel.config import WorldConfig
from hydra.kernel.errors import KernelError
from hydra.kernel.kernelstate import KernelDomainState
from hydra.kernel.state import WorldMeta, WorldPhase, WorldState
from hydra.kernel.version import KERNEL_VERSION
from hydra.media.model import MediaState
from hydra.memory.model import MemoryState
from hydra.population.model import PopulationState
from hydra.social.model import SocialState
from hydra.technology.model import TechnologyState

from hydra.geography.systems import PUBLIC_LOAD_KWH_PER_RESIDENT

from .economy import build_economy, calibrate_economy
from .organisations import (
    assign_plant_operators,
    assign_public_jobs,
    fund_companies,
    build_companies,
    build_government,
    build_media_and_net,
    build_technology,
)
from .planet import build_geography
from .population import build_population
from .seeds import SeedTree

PEAK_FACTOR = 1.28          # daily peak over average load
RESERVE_MARGIN = 1.25       # installed capacity over peak


@dataclass(slots=True)
class GenesisResult:
    state: WorldState
    seeds: SeedTree
    summary: dict[str, int | str | float]


class GenesisEngine:
    """Deterministic constructor of worlds.

    ``seed + kernel version + config`` fully determines the output: the same triple always
    produces the same initial state hash, on any machine.
    """

    def __init__(self, config: WorldConfig) -> None:
        self.config = config

    def create(self, *, world_id: str, seed: int, timeline_id: str = "tl_zero") -> GenesisResult:
        seeds = SeedTree(master=seed)
        config = self.config
        meta = WorldMeta(
            world_id=world_id,
            timeline_id=timeline_id,
            seed=seed,
            config_hash=config.config_hash(),
            kernel_version=KERNEL_VERSION,
            tick=0,
            phase=WorldPhase.GENESIS,
            seed_lineage=[f"master:{seed}"],
        )
        state = WorldState(meta=meta)
        state.add(KernelDomainState())

        residents = config.population.total_residents
        households = max(1, int(residents / max(1.2, config.population.household_size_mean)))
        employed = int(residents * 0.46)

        # Economy first: the bill of materials is what tells us how big the city has to be.
        economy = build_economy(seeds, config, residents)
        daily_demand = calibrate_economy(
            economy, config, residents=residents, households=households, employed=employed
        )
        installed_mw = round(
            (daily_demand.get("electricity", 0.0) / 24.0 + residents * PUBLIC_LOAD_KWH_PER_RESIDENT)
            / 1000.0 * PEAK_FACTOR * RESERVE_MARGIN,
            2,
        )
        geography = build_geography(seeds, residents, config.epoch_year, installed_power_mw=installed_mw)
        companies = build_companies(seeds, config, geography, economy, daily_demand)
        government = build_government(seeds, config, economy)
        media, net = build_media_and_net(seeds, geography)
        technology = build_technology(seeds, companies)
        built = build_population(seeds, config, geography, economy, companies, government, media)

        state.add(geography)
        state.add(economy)
        state.add(companies)
        state.add(government)
        state.add(media)
        state.add(net)
        state.add(technology)
        state.add(built.agents)
        state.add(built.population)
        state.add(built.social)
        state.add(built.memory)
        state.add(CultureState())
        state.add(HistoryState())
        assign_plant_operators(geography, companies)
        fund_companies(companies, economy, seeds)
        assign_public_jobs(government, built.agents)
        state.add(self._seed_knowledge(seeds, economy, geography, built.agents))

        self._prime_markets(economy, companies, built.agents, built.population)
        summary = {
            "world_id": world_id,
            "seed": seed,
            "residents": built.agents.total_population(),
            "individuals": len(built.agents.people),
            "persistent": len(built.agents.persistent_ids),
            "cohorts": len(built.agents.cohorts),
            "households": len(built.population.households),
            "companies": len(companies.companies),
            "buildings": len(geography.buildings),
            "districts": len(geography.districts),
            "outlets": len(media.outlets),
            "sites": len(net.sites),
            "relationships": built.social.edge_count,
            "state_hash": state.state_hash(),
        }
        return GenesisResult(state=state, seeds=seeds, summary=summary)

    # -- helpers ------------------------------------------------------------------
    def _seed_knowledge(
        self,
        seeds: SeedTree,
        economy: EconomyState,
        geography: GeographyState,
        agents: AgentsState,
    ) -> KnowledgeState:
        """Everyone starts out knowing the prices they pay and where they live.

        Nothing more: agents must acquire the rest of their picture of the world through
        observation, media and conversation, exactly like the running simulation demands.
        """

        knowledge = KnowledgeState()
        rng = seeds.rng("knowledge")
        essentials = [g.code for g in economy.goods.values() if g.essential]
        for code in essentials:
            fact = Fact(
                fact_id=f"fact_genesis_price_{code}",
                tick=0,
                topic=f"price.{code}",
                subject=code,
                claim="price_level",
                value=float(economy.markets[code].price_minor),
                text=f"{economy.goods[code].name} costs {economy.markets[code].price_minor / 100:.2f} HYD per {economy.goods[code].unit}",
                importance=0.15,
            )
            knowledge.add_fact(fact)

        for person in agents.people.values():
            for code in essentials:
                if not rng.chance(0.85):
                    continue
                objective = economy.markets[code].price_minor
                perceived = objective * rng.uniform(0.94, 1.06)
                knowledge.learn(
                    person.person_id,
                    KnownFact(
                        fact_id=f"fact_genesis_price_{code}",
                        acquired_tick=0,
                        source=Source.OBSERVED,
                        confidence=round(rng.uniform(0.55, 0.9), 4),
                        value=round(perceived, 2),
                    ),
                )
        for cohort in agents.cohorts.values():
            knowledge.cohort_awareness[cohort.cohort_id] = {
                f"fact_genesis_price_{code}": round(rng.uniform(0.6, 0.95), 4) for code in essentials
            }
        return knowledge

    def _prime_markets(
        self,
        economy: EconomyState,
        companies: CompaniesState,
        agents: AgentsState,
        population: PopulationState,
    ) -> None:
        """Set the first supply/demand reading so tick 1 starts from a plausible economy."""

        residents = agents.total_population()
        for code, market in economy.markets.items():
            producers = companies.producers_of(code)
            market.supply = round(sum(c.capacity_units * c.utilisation for c in producers), 3)
            market.demand = round(market.supply * 0.98, 3)
            market.unit_cost_minor = int(market.price_minor * 0.82)
        infrastructure_demand = 0.0
        economy.gdp_minor = int(
            sum(c.capacity_units * c.utilisation * c.price_minor for c in companies.active()) * 30
        )
        economy.gdp_history.append(economy.gdp_minor)
        economy.unemployment_rate = round(
            1.0 - min(1.0, companies.total_employment / max(1.0, residents * 0.52)), 4
        )
        population.unemployment_rate = economy.unemployment_rate
        economy.markets["electricity"].supply = round(infrastructure_demand * 1.35, 3)
        economy.markets["electricity"].demand = round(infrastructure_demand, 3)


def seal(state: WorldState) -> WorldState:
    """Freeze Timeline Zero (spec section 3)."""

    if state.meta.phase is WorldPhase.SEALED:
        return state
    state.meta.phase = WorldPhase.SEALED
    state.meta.sealed_at_tick = state.meta.tick
    return state


def require_sealed(state: WorldState) -> None:
    if state.meta.phase is not WorldPhase.SEALED:
        raise KernelError("world must be sealed before it can run autonomously")
