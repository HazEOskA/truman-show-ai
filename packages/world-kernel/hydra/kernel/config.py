"""World configuration.

Configuration is part of the determinism identity: ``seed + kernel_version + config_hash``
identifies a world completely. Anything that changes simulation outcomes belongs here and
nowhere else — no magic numbers hidden in systems that an operator cannot see.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .clock import TICKS_PER_DAY, TICKS_PER_HOUR, TICKS_PER_MONTH
from .serialization import content_hash


@dataclass(slots=True)
class CadenceConfig:
    """How often each system phase runs, in ticks (1 tick = 10 simulated minutes)."""

    environment: int = 1
    transport: int = 1
    markets: int = TICKS_PER_HOUR
    agents: int = TICKS_PER_HOUR
    companies: int = TICKS_PER_HOUR
    production: int = TICKS_PER_HOUR
    households: int = TICKS_PER_HOUR
    information: int = TICKS_PER_HOUR
    labour_market: int = TICKS_PER_DAY
    banking: int = TICKS_PER_DAY
    government: int = TICKS_PER_DAY
    media: int = TICKS_PER_HOUR // 2 or 1
    culture: int = TICKS_PER_DAY * 7
    demographics: int = TICKS_PER_MONTH
    technology: int = TICKS_PER_MONTH


@dataclass(slots=True)
class PopulationConfig:
    total_residents: int = 48_000
    persistent_agents: int = 120
    lightweight_agents: int = 4_800
    cohort_bucket_years: int = 10
    household_size_mean: float = 2.4


@dataclass(slots=True)
class EconomyConfig:
    currency_code: str = "HYD"
    company_count: int = 140
    base_price_drift: float = 0.35
    price_change_cap: float = 0.025
    target_margin: float = 0.18
    vat_rate: float = 0.19
    income_tax_rate: float = 0.17
    corporate_tax_rate: float = 0.19
    interest_rate: float = 0.04
    unemployment_benefit_ratio: float = 0.4
    layoff_cash_months: float = 1.5
    hiring_margin_threshold: float = 0.12


@dataclass(slots=True)
class DormancyConfig:
    sleep_hour: float = 23.0
    wake_hour: float = 7.0
    sleep_hour_jitter: float = 1.5
    dormant_after_idle_days: int = 3
    wake_importance_threshold: float = 0.45
    light_idle_importance_threshold: float = 0.2


@dataclass(slots=True)
class AgentRuntimeConfig:
    """Compute governor for the agent layer — the priority queue of spec section 26."""

    max_brain_evaluations_per_tick: int = 700
    perception_batch: int = 1_200
    tier_b_activity_share: float = 0.55
    promotion_importance: float = 0.72


@dataclass(slots=True)
class InformationConfig:
    """Knobs of the information world: how facts travel and decay."""

    media_pickup_threshold: float = 0.35
    social_share_probability: float = 0.22
    rumour_distortion_probability: float = 0.12
    belief_update_rate: float = 0.35
    memory_decay_per_day: float = 0.012
    max_working_memory: int = 12
    max_episodic_memory: int = 220


@dataclass(slots=True)
class LLMConfig:
    """LLM is an optional adapter. Default: disabled, world runs on rules alone."""

    enabled: bool = False
    provider: str = "disabled"
    # Gemini 3.5 Flash on both rungs of the ladder. The escalation thresholds below still
    # decide *whether* a model is consulted at all; what changes with importance is the
    # budget spent, not the vendor. Defaults stay `disabled` because a world must run to
    # completion with no provider configured — the determinism tests require exactly that.
    small_model: str = "gemini-3.5-flash"
    large_model: str = "gemini-3.5-flash"
    daily_calls_per_agent: int = 6
    token_budget_per_agent: int = 12_000
    escalation_importance: float = 0.6
    large_model_importance: float = 0.8
    max_calls_per_tick: int = 8


@dataclass(slots=True)
class KernelConfig:
    snapshot_interval: int = 4_320          # every 30 simulated days
    checkpoint_interval: int = 1_440        # hash the world every 10 simulated days
    ledger_importance_threshold: float = 0.12
    max_events_per_tick: int = 20_000
    quarantine_after_failures: int = 3


@dataclass(slots=True)
class WorldConfig:
    world_name: str = "Hydra World"
    seed_city: str = "hydra"
    epoch_year: int = 0
    kernel: KernelConfig = field(default_factory=KernelConfig)
    strict_contracts: bool = False
    cadences: CadenceConfig = field(default_factory=CadenceConfig)
    population: PopulationConfig = field(default_factory=PopulationConfig)
    agents: AgentRuntimeConfig = field(default_factory=AgentRuntimeConfig)
    economy: EconomyConfig = field(default_factory=EconomyConfig)
    dormancy: DormancyConfig = field(default_factory=DormancyConfig)
    information: InformationConfig = field(default_factory=InformationConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    def config_hash(self) -> str:
        """Hash of everything that affects the simulation.

        The LLM section is deliberately excluded: enabling a model changes the *quality* of
        decisions, never the identity of the deterministic core, and a world must remain
        replayable on a machine with no provider configured.
        """

        payload = {
            "world_name": self.world_name,
            "seed_city": self.seed_city,
            "epoch_year": self.epoch_year,
            "kernel": self.kernel,
            "cadences": self.cadences,
            "population": self.population,
            "agents": self.agents,
            "economy": self.economy,
            "dormancy": self.dormancy,
            "information": self.information,
        }
        return content_hash(payload)
