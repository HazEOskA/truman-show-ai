"""Street and place names.

Names are part of the projection, not part of the world: geography names districts and
buildings, but nobody in the simulation has ever needed to say "Foundry Row". They are
generated deterministically from the district seed so that an address, once seen, stays the
same forever -- across restarts, across forks, across machines.

The pools are deliberately plain. A city reads as real when its streets are named after
what used to be there, not when they are named exotically.
"""

from __future__ import annotations

from hydra.kernel.rng import DeterministicRng, derive_seed

#: Neutral stems used everywhere.
COMMON = (
    "Alder", "Anvil", "Ash", "Baker", "Bell", "Birch", "Bridge", "Chapel", "Cinder",
    "Clay", "Copper", "Crane", "Dover", "Elm", "Ferry", "Field", "Forge", "Garden",
    "Granite", "Grove", "Hollow", "Kiln", "Lamp", "Lark", "Lime", "Linden", "Marsh",
    "Meadow", "Mill", "Orchard", "Quarry", "Ridge", "Salt", "Slate", "Spire", "Stone",
    "Thistle", "Vine", "Well", "Willow",
)

#: Extra stems that fit a particular kind of district.
FLAVOUR: dict[str, tuple[str, ...]] = {
    "commercial": ("Exchange", "Ledger", "Market", "Mint", "Guild", "Charter", "Bourse", "Assay"),
    "elite": ("Belvedere", "Consort", "Crescent", "Laurel", "Palisade", "Regent", "Cypress"),
    "industrial": ("Boiler", "Coke", "Foundry", "Furnace", "Gantry", "Rivet", "Slag", "Turbine"),
    "port": ("Anchor", "Bosun", "Capstan", "Harbour", "Jetty", "Mooring", "Quay", "Tide"),
    "mixed": ("Almond", "Cobbler", "Corner", "Dye", "Glover", "Potter", "Tanner", "Weaver"),
    "residential": ("Bramble", "Cottage", "Heather", "Kestrel", "Larch", "Rowan", "Sorrel"),
    "periphery": ("Ashen", "Culvert", "Dust", "Fringe", "Gravel", "Sump", "Verge", "Wither"),
}

#: Suffix by street class. Bigger roads get bigger words.
SUFFIX: dict[str, tuple[str, ...]] = {
    "arterial": ("Avenue", "Way", "Boulevard", "Causeway", "Approach"),
    "collector": ("Street", "Road", "Parade", "Walk", "Rise"),
    "local": ("Lane", "Row", "Close", "Court", "Yard", "Mews", "Path", "Terrace"),
}

PARK_WORDS = ("Green", "Gardens", "Common", "Park", "Meadow", "Grove")
PLAZA_WORDS = ("Square", "Plaza", "Circus", "Court", "Steps")


class NameRegistry:
    """One city, one set of street names.

    Districts each have their own flavour of name, but they share this registry so that no
    two streets in Hydra are called the same thing. Addresses are how a person refers to a
    place they clicked on; two of them meaning two different buildings would be a bug they
    could not see.
    """

    __slots__ = ("_used",)

    def __init__(self) -> None:
        self._used: set[str] = set()

    def pool(self, seed: int, district_kind: str) -> "NamePool":
        return NamePool(seed, district_kind, self._used)

    def __len__(self) -> int:
        return len(self._used)


class NamePool:
    """Hands out distinct names for one district, deterministically and without repeats."""

    __slots__ = ("_rng", "_stems", "_used")

    def __init__(self, seed: int, district_kind: str, used: set[str] | None = None) -> None:
        self._rng = DeterministicRng(derive_seed(seed, "names"))
        stems = list(COMMON) + list(FLAVOUR.get(district_kind, ()))
        self._stems = self._rng.shuffled(sorted(set(stems)))
        self._used: set[str] = self._used_set(used)

    @staticmethod
    def _used_set(used: set[str] | None) -> set[str]:
        return used if used is not None else set()

    def street(self, klass: str, index: int) -> str:
        suffixes = SUFFIX.get(klass, SUFFIX["local"])
        for attempt in range(len(self._stems) * len(suffixes)):
            stem = self._stems[(index + attempt) % len(self._stems)]
            suffix = suffixes[(index + attempt // len(self._stems)) % len(suffixes)]
            name = f"{stem} {suffix}"
            if name not in self._used:
                self._used.add(name)
                return name
        return f"{klass.title()} {index}"

    def open_space(self, use: str, index: int) -> str:
        words = PARK_WORDS if use == "park" else PLAZA_WORDS
        for attempt in range(len(self._stems) * len(words)):
            stem = self._stems[(index + attempt) % len(self._stems)]
            name = f"{stem} {words[(index + attempt // len(self._stems)) % len(words)]}"
            if name not in self._used:
                self._used.add(name)
                return name
        return f"{use.title()} {index}"


def house_number(ordinal: int, side: int) -> int:
    """Odds on one side of the street, evens on the other, starting at 1."""

    return ordinal * 2 + 1 if side else ordinal * 2 + 2
