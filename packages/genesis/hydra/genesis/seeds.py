"""Seed tree (spec section 2).

``MASTER_WORLD_SEED`` fans out into one derived seed per world element. Because derivation is
a pure function of the label path, generating the same district twice — in another process,
after a restart, inside a fork — produces the identical result.

    MASTER_WORLD_SEED
     ├── planet_seed
     ├── continent_seed
     ├── country_seed
     ├── city_seed
     ├── district_seed
     ├── company_seed
     └── person_seed
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.kernel.rng import DeterministicRng, derive_seed


@dataclass(frozen=True, slots=True)
class SeedTree:
    master: int

    def branch(self, *labels: object) -> int:
        return derive_seed(self.master, *labels)

    def rng(self, *labels: object) -> DeterministicRng:
        return DeterministicRng(self.branch(*labels))

    # Named branches, spelled out so the tree is visible in code and in the docs.
    def planet(self) -> DeterministicRng:
        return self.rng("planet")

    def continent(self, continent_id: str) -> DeterministicRng:
        return self.rng("continent", continent_id)

    def country(self, country_id: str) -> DeterministicRng:
        return self.rng("country", country_id)

    def region(self, region_id: str) -> DeterministicRng:
        return self.rng("region", region_id)

    def city(self, city_id: str) -> DeterministicRng:
        return self.rng("city", city_id)

    def district(self, district_id: str) -> DeterministicRng:
        return self.rng("district", district_id)

    def company(self, index: int) -> DeterministicRng:
        return self.rng("company", index)

    def person(self, index: int) -> DeterministicRng:
        return self.rng("person", index)

    def cohort(self, cohort_id: str) -> DeterministicRng:
        return self.rng("cohort", cohort_id)

    def institution(self, name: str) -> DeterministicRng:
        return self.rng("institution", name)

    def lineage(self, *labels: object) -> str:
        return "/".join(str(label) for label in labels)
