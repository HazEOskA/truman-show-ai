"""Shared fixtures.

Tests run against a deliberately small Hydra — a few thousand residents — so the whole suite
finishes in seconds. Nothing about the mechanics changes with size: the same systems, the same
kernel, the same determinism guarantees.
"""

from __future__ import annotations

import pytest

from hydra.kernel.config import WorldConfig
from hydra.world import create_world


def small_config(**overrides) -> WorldConfig:
    config = WorldConfig(world_name="Hydra Test")
    config.population.total_residents = 4_000
    config.population.lightweight_agents = 260
    config.population.persistent_agents = 20
    config.economy.company_count = 40
    config.kernel.snapshot_interval = 288
    config.kernel.checkpoint_interval = 144
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


@pytest.fixture(scope="session")
def config() -> WorldConfig:
    return small_config()


@pytest.fixture
def world(config: WorldConfig):
    return create_world(config, seed=4242, world_id="world_test")
