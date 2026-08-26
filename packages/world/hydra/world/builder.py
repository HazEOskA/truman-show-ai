"""Composition root.

The kernel knows no domains and domains know no kernel internals; this module is the only
place where the two meet. It registers every system with its configured cadence, wires the
action pipeline and the optional LLM gateway, and hands back a runnable world.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.agents.actions import register_actions
from hydra.agents.llm.adapter import build_adapter
from hydra.agents.llm.gateway import LLMGateway
from hydra.agents.systems import AgentBrainSystem, PerceptionSystem
from hydra.companies.systems import CompanyDecisionSystem, PayrollSystem, ProductionSystem
from hydra.culture.systems import CultureSystem
from hydra.demographics.systems import DemographySystem
from hydra.dormancy.systems import DormancySystem
from hydra.economy.systems import BankingSystem, LabourMarketSystem, MarketCloseSystem, MarketSystem
from hydra.events.bus import EventBus, EventTransport
from hydra.genesis.engine import GenesisEngine, seal
from hydra.geography.systems import PowerGridSystem, TransportSystem, WaterSystem, WeatherSystem
from hydra.government.systems import GovernmentSystem, TaxSystem
from hydra.history.ledger import Ledger, NullLedger
from hydra.history.systems import HistorySystem
from hydra.information.systems import FactSystem, PropagationSystem
from hydra.kernel.actions import ActionPipeline
from hydra.kernel.config import WorldConfig
from hydra.kernel.engine import Kernel
from hydra.kernel.snapshots import Snapshot, restore_snapshot
from hydra.kernel.state import WorldState
from hydra.kernel.systems import SystemRegistry
from hydra.media.systems import MediaSystem
from hydra.population.systems import CohortConsumptionSystem, HouseholdConsumptionSystem, HousingSystem
from hydra.persistence.store import TimelineRecord, WorldRecord, WorldStore
from hydra.technology.systems import ResearchSystem


@dataclass(slots=True)
class WorldRuntime:
    kernel: Kernel
    state: WorldState
    config: WorldConfig
    ledger: Ledger | NullLedger
    store: WorldStore | None = None

    @property
    def tick(self) -> int:
        return self.state.meta.tick

    def run(self, ticks: int) -> int:
        result = self.kernel.run(ticks)
        self.ledger.flush()
        return result

    def flush(self) -> None:
        self.ledger.flush()


def build_registry(config: WorldConfig) -> SystemRegistry:
    """Every system, with cadence taken from configuration (spec section 4)."""

    cadences = config.cadences
    registry = SystemRegistry()
    for system in (
        # 1 — environment
        WeatherSystem(),
        PowerGridSystem(),
        WaterSystem(),
        TransportSystem(),
        # 2 — agents
        DormancySystem(cadences.agents),
        PerceptionSystem(cadences.agents),
        AgentBrainSystem(cadences.agents),
        # 3 — institutions
        GovernmentSystem(),
        PayrollSystem(),
        CompanyDecisionSystem(),
        HousingSystem(),
        TaxSystem(),
        # 4 — markets
        MarketSystem(cadences.markets),
        LabourMarketSystem(),
        BankingSystem(),
        # 5 — physical
        ProductionSystem(cadences.production),
        HouseholdConsumptionSystem(),
        CohortConsumptionSystem(),
        # 6 — information
        FactSystem(),
        MediaSystem(cadences.media),
        PropagationSystem(cadences.information),
        HistorySystem(),
        # 7 — slow
        MarketCloseSystem(cadences.markets),
        DemographySystem(),
        ResearchSystem(),
        CultureSystem(),
    ):
        registry.register(system)
    return registry


def build_gateway(config: WorldConfig) -> LLMGateway:
    adapter = build_adapter(config.llm.provider if config.llm.enabled else "disabled")
    return LLMGateway(adapter, config.llm)


def build_kernel(
    state: WorldState,
    config: WorldConfig,
    *,
    store: WorldStore | None = None,
    transport: EventTransport | None = None,
    strict_contracts: bool | None = None,
) -> tuple[Kernel, Ledger | NullLedger]:
    registry = build_registry(config)
    pipeline = register_actions(ActionPipeline())
    ledger: Ledger | NullLedger = (
        Ledger(store, state.meta.timeline_id) if store is not None else NullLedger()
    )
    kernel = Kernel(
        state,
        config,
        registry,
        actions=pipeline,
        bus=EventBus(transport),
        sink=ledger,
        llm=build_gateway(config),
        strict_contracts=config.strict_contracts if strict_contracts is None else strict_contracts,
    )
    if store is not None:
        kernel.snapshot_hook = _snapshot_hook(store, ledger)
    return kernel, ledger


def _snapshot_hook(store: WorldStore, ledger: Ledger | NullLedger):
    def _write(snapshot: Snapshot) -> None:
        ledger.flush()
        store.write_snapshot(snapshot)

    return _write


def create_world(
    config: WorldConfig,
    *,
    seed: int,
    world_id: str = "world_hydra",
    timeline_id: str = "tl_zero",
    store: WorldStore | None = None,
    seal_world: bool = True,
) -> WorldRuntime:
    """GENESIS → SEAL → a world that runs on its own."""

    result = GenesisEngine(config).create(world_id=world_id, seed=seed, timeline_id=timeline_id)
    state = result.state
    if seal_world:
        seal(state)
    kernel, ledger = build_kernel(state, config, store=store)

    if store is not None:
        from hydra.kernel.serialization import encode
        from hydra.kernel.snapshots import take_snapshot

        store.put_world(
            WorldRecord(
                world_id=world_id,
                name=config.world_name,
                seed=seed,
                config_hash=state.meta.config_hash,
                kernel_version=state.meta.kernel_version,
                config=encode(config),
                root_timeline_id=timeline_id,
            )
        )
        store.put_timeline(
            TimelineRecord(
                timeline_id=timeline_id,
                world_id=world_id,
                seed=seed,
                seed_lineage=list(state.meta.seed_lineage),
                label="Timeline Zero",
                sealed=seal_world,
                head_tick=0,
            )
        )
        store.write_snapshot(take_snapshot(state))
    return WorldRuntime(kernel=kernel, state=state, config=config, ledger=ledger, store=store)


def load_world(
    store: WorldStore,
    *,
    config: WorldConfig,
    timeline_id: str,
    tick: int | None = None,
    verify: bool = True,
) -> WorldRuntime:
    """Restore from the nearest snapshot at or before ``tick``."""

    snapshot = (
        store.nearest_snapshot(timeline_id, tick)
        if tick is not None
        else store.nearest_snapshot(timeline_id, 10**12)
    )
    if snapshot is None:
        raise FileNotFoundError(f"no snapshot for timeline {timeline_id}")
    state = restore_snapshot(snapshot, verify=verify)
    kernel, ledger = build_kernel(state, config, store=store)
    return WorldRuntime(kernel=kernel, state=state, config=config, ledger=ledger, store=store)
