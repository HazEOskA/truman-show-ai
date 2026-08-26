"""Deterministic randomness.

The whole world is reproducible from ``MASTER_WORLD_SEED``. That requires a PRNG whose
output depends on nothing but its own state: no hash randomisation, no floating point
accumulation, no platform specifics. SplitMix64 gives us that in pure integer arithmetic,
and BLAKE2b gives us reproducible seed derivation for the seed tree of spec section 2.
"""

from __future__ import annotations

import hashlib
import math
from typing import Iterable, Sequence, TypeVar

_MASK64 = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15

T = TypeVar("T")


def derive_seed(parent_seed: int, *labels: object) -> int:
    """Derive a child seed from a parent seed and a label path.

    ``derive_seed(master, "planet")`` and ``derive_seed(master, "city", "hydra")`` are stable
    across processes and Python versions because they go through BLAKE2b rather than
    :func:`hash`.
    """

    h = hashlib.blake2b(digest_size=8)
    h.update(parent_seed.to_bytes(8, "little", signed=False))
    for label in labels:
        h.update(b"\x1f")
        h.update(str(label).encode("utf-8"))
    return int.from_bytes(h.digest(), "little", signed=False)


class SplitMix64:
    """Minimal, fast, fully specified 64-bit PRNG."""

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK64

    @property
    def state(self) -> int:
        return self._state

    def next_u64(self) -> int:
        self._state = (self._state + _GOLDEN) & _MASK64
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return z ^ (z >> 31)


class DeterministicRng:
    """The only source of randomness allowed inside the simulation.

    Never use :mod:`random` in domain code: it is process-global and seeded per interpreter,
    which breaks reproducibility the moment two systems interleave differently.
    """

    __slots__ = ("_core", "seed")

    def __init__(self, seed: int) -> None:
        self.seed = seed & _MASK64
        self._core = SplitMix64(self.seed)

    # -- construction -------------------------------------------------------------
    def derive(self, *labels: object) -> "DeterministicRng":
        """A child stream. Use one per system per tick so ordering stays independent."""

        return DeterministicRng(derive_seed(self.seed, *labels))

    # -- primitives ---------------------------------------------------------------
    def u64(self) -> int:
        return self._core.next_u64()

    def random(self) -> float:
        """Uniform float in ``[0, 1)`` with 53 bits of entropy."""

        return (self._core.next_u64() >> 11) * (1.0 / (1 << 53))

    def randint(self, low: int, high: int) -> int:
        """Uniform integer in ``[low, high]`` (inclusive), rejection-free modulo bias below 2^53."""

        if high < low:
            raise ValueError(f"empty range [{low}, {high}]")
        span = high - low + 1
        return low + (self._core.next_u64() % span)

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()

    def chance(self, probability: float) -> bool:
        if probability <= 0.0:
            return False
        if probability >= 1.0:
            return True
        return self.random() < probability

    def normal(self, mean: float = 0.0, sigma: float = 1.0) -> float:
        """Box-Muller. Deterministic given the stream."""

        u1 = max(self.random(), 1e-12)
        u2 = self.random()
        return mean + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def clamped_normal(self, mean: float, sigma: float, low: float, high: float) -> float:
        return min(high, max(low, self.normal(mean, sigma)))

    def exponential(self, rate: float) -> float:
        return -math.log(max(self.random(), 1e-12)) / rate

    # -- collections --------------------------------------------------------------
    def choice(self, items: Sequence[T]) -> T:
        if not items:
            raise ValueError("choice from empty sequence")
        return items[self.randint(0, len(items) - 1)]

    def weighted_choice(self, items: Sequence[T], weights: Sequence[float]) -> T:
        if len(items) != len(weights):
            raise ValueError("items and weights must have equal length")
        total = 0.0
        for w in weights:
            total += max(0.0, w)
        if total <= 0.0:
            return self.choice(items)
        target = self.random() * total
        upto = 0.0
        for item, weight in zip(items, weights):
            upto += max(0.0, weight)
            if upto >= target:
                return item
        return items[-1]

    def sample(self, items: Sequence[T], k: int) -> list[T]:
        """Reservoir-free deterministic sample without replacement."""

        pool = list(items)
        k = min(k, len(pool))
        picked: list[T] = []
        for _ in range(k):
            idx = self.randint(0, len(pool) - 1)
            picked.append(pool.pop(idx))
        return picked

    def shuffled(self, items: Iterable[T]) -> list[T]:
        pool = list(items)
        for i in range(len(pool) - 1, 0, -1):
            j = self.randint(0, i)
            pool[i], pool[j] = pool[j], pool[i]
        return pool
