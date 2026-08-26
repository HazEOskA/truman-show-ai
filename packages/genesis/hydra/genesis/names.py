"""Deterministic name generation for a world with its own culture.

Hydra is not Earth, so names are built from an invented phonology rather than borrowed from
a real-world list. Everything here is a pure function of a seeded RNG — no LLM, no I/O.
"""

from __future__ import annotations

from hydra.kernel.rng import DeterministicRng

_ONSET = ("k", "v", "r", "s", "t", "m", "n", "l", "d", "h", "br", "dr", "kl", "st", "th", "vr", "gr", "sk")
_NUCLEUS = ("a", "e", "i", "o", "u", "ae", "ei", "ou", "ia", "ar", "or", "en")
_CODA = ("n", "k", "r", "s", "l", "th", "sk", "rn", "va", "ek", "el", "im", "or")

_GIVEN_SUFFIX_F = ("a", "ia", "el", "ine", "ora", "ys")
_GIVEN_SUFFIX_M = ("or", "an", "us", "ek", "im", "ar")

_SHORT_CODA = ("n", "k", "r", "s", "l", "ek", "el", "im", "or")

_COMPANY_TAIL = (
    "Works", "Industries", "Systems", "Collective", "Union", "Foundry", "Logistics",
    "Grid", "Labs", "Holdings", "Provisions", "Mill", "Trading", "Assembly", "Dynamics",
)
_OUTLET_TAIL = ("Herald", "Signal", "Ledger", "Dispatch", "Voice", "Chronicle", "Wire", "Post", "Review")


def _syllable(rng: DeterministicRng, coda: bool = True) -> str:
    out = rng.choice(_ONSET) + rng.choice(_NUCLEUS)
    if coda and rng.chance(0.55):
        out += rng.choice(_CODA)
    return out


def word(rng: DeterministicRng, syllables: int = 2) -> str:
    return "".join(_syllable(rng, coda=(i == syllables - 1)) for i in range(syllables)).capitalize()


def given_name(rng: DeterministicRng, female: bool) -> str:
    """Two-syllable names: short enough to read in a dashboard row."""

    base = rng.choice(_ONSET) + rng.choice(("a", "e", "i", "o", "u"))
    suffix = rng.choice(_GIVEN_SUFFIX_F if female else _GIVEN_SUFFIX_M)
    return (base + suffix).capitalize()


def surname(rng: DeterministicRng) -> str:
    base = rng.choice(_ONSET) + rng.choice(("a", "e", "i", "o", "u", "ar", "or"))
    return (base + rng.choice(_CODA)).capitalize()


def full_name(rng: DeterministicRng, female: bool) -> str:
    return f"{given_name(rng, female)} {surname(rng)}"


def company_name(rng: DeterministicRng) -> str:
    return f"{word(rng, 2)} {rng.choice(_COMPANY_TAIL)}"


def outlet_name(rng: DeterministicRng) -> str:
    return f"{rng.choice(('Hydra', 'City', word(rng, 1), word(rng, 2)))} {rng.choice(_OUTLET_TAIL)}"


def place_name(rng: DeterministicRng) -> str:
    return word(rng, 2)
