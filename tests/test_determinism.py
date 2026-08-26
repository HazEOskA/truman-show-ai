"""Spec section 34 — the determinism test.

Two simulations with the same seed, the same configuration and the same kernel version must
produce an identical state hash after the same number of ticks. This is the property the whole
architecture is built to protect: no process-global randomness, no dictionary-order leakage,
no wall-clock, no LLM in the deterministic path.
"""

from __future__ import annotations

import pytest

from hydra.kernel.clock import TICKS_PER_DAY
from hydra.kernel.kernelstate import KernelDomainState
from hydra.world import create_world

from conftest import small_config

TICKS = TICKS_PER_DAY // 2


def _run(seed: int, ticks: int = TICKS) -> str:
    runtime = create_world(small_config(), seed=seed, world_id=f"world_{seed}")
    runtime.kernel.run(ticks)
    return runtime.state.state_hash()


def test_same_seed_same_config_same_hash():
    first = _run(31337)
    second = _run(31337)
    assert first == second


def test_different_seed_diverges():
    assert _run(31337) != _run(31338)


def test_genesis_alone_is_reproducible():
    a = create_world(small_config(), seed=555, world_id="world_a")
    b = create_world(small_config(), seed=555, world_id="world_b")
    # World ids differ, so compare the domains rather than the metadata.
    from hydra.kernel.serialization import content_hash

    assert content_hash(a.state.to_dict()["domains"]) == content_hash(b.state.to_dict()["domains"])


def test_config_change_changes_the_world_identity():
    base = small_config()
    tweaked = small_config()
    tweaked.economy.vat_rate = base.economy.vat_rate + 0.05
    assert base.config_hash() != tweaked.config_hash()


def test_llm_settings_do_not_change_world_identity():
    """A world must stay replayable on a machine with no model provider configured."""

    base = small_config()
    with_llm = small_config()
    with_llm.llm.enabled = True
    with_llm.llm.provider = "anthropic"
    assert base.config_hash() == with_llm.config_hash()


def test_checkpoints_are_recorded_for_verification():
    runtime = create_world(small_config(), seed=777, world_id="world_ckpt")
    runtime.kernel.run(TICKS_PER_DAY)
    checkpoints = runtime.state.domain(KernelDomainState).checkpoints
    assert checkpoints, "the kernel must record checkpoint hashes for replay verification"
    tick, digest = sorted(checkpoints.items(), key=lambda kv: int(kv[0]))[0]
    assert len(digest) == 32


@pytest.mark.parametrize("split", [3, 7])
def test_running_in_batches_matches_running_in_one_go(split: int):
    """Tick batching is an execution detail; it must not be observable in the world."""

    one_go = create_world(small_config(), seed=99, world_id="world_one")
    one_go.kernel.run(24)

    batched = create_world(small_config(), seed=99, world_id="world_one")
    remaining = 24
    while remaining > 0:
        step = min(split, remaining)
        batched.kernel.run(step)
        remaining -= step

    assert one_go.state.state_hash() == batched.state.state_hash()
