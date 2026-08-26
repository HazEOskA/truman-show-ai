"""World state container.

There is no monolithic ``World`` class (architecture rule 1). ``WorldState`` is a thin,
domain-agnostic container: metadata plus a set of independently registered domain states.
The kernel can snapshot, hash and restore any world without knowing what an economy is.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterator, TypeVar

from .errors import KernelError
from .serialization import content_hash, decode, encode
from .version import KERNEL_VERSION


class WorldPhase(str, enum.Enum):
    GENESIS = "genesis"
    SEALED = "sealed"


@dataclass(slots=True)
class DomainState:
    """Base class for every domain's slice of the world.

    Subclasses set ``DOMAIN`` and are registered with :func:`register_domain` so snapshots
    can be decoded without the kernel importing domain packages.
    """

    DOMAIN: ClassVar[str] = ""


_DOMAIN_REGISTRY: dict[str, type[DomainState]] = {}
_D = TypeVar("_D", bound=DomainState)


def register_domain(cls: type[_D]) -> type[_D]:
    if not cls.DOMAIN:
        raise KernelError(f"{cls.__name__} must define DOMAIN")
    existing = _DOMAIN_REGISTRY.get(cls.DOMAIN)
    if existing is not None and existing is not cls:
        raise KernelError(f"domain {cls.DOMAIN!r} already registered by {existing.__name__}")
    _DOMAIN_REGISTRY[cls.DOMAIN] = cls
    return cls


def domain_registry() -> dict[str, type[DomainState]]:
    return dict(_DOMAIN_REGISTRY)


def _strip_excluded(domains: dict[str, Any], excluded: dict[str, tuple[str, ...]]) -> None:
    for domain_name, fields in excluded.items():
        payload = domains.get(domain_name)
        if isinstance(payload, dict):
            for field_name in fields:
                payload.pop(field_name, None)


@dataclass(slots=True)
class WorldMeta:
    world_id: str
    timeline_id: str
    seed: int
    config_hash: str
    kernel_version: str = KERNEL_VERSION
    tick: int = 0
    phase: WorldPhase = WorldPhase.GENESIS
    parent_timeline_id: str | None = None
    fork_tick: int | None = None
    seed_lineage: list[str] = field(default_factory=list)
    created_at_tick: int = 0
    sealed_at_tick: int | None = None
    event_seq: int = 0
    fact_seq: int = 0


@dataclass(slots=True)
class WorldState:
    meta: WorldMeta
    domains: dict[str, DomainState] = field(default_factory=dict)

    # -- domain access ------------------------------------------------------------
    def add(self, state: DomainState) -> None:
        self.domains[type(state).DOMAIN] = state

    def domain(self, cls: type[_D]) -> _D:
        try:
            state = self.domains[cls.DOMAIN]
        except KeyError:
            raise KernelError(f"domain {cls.DOMAIN!r} is not present in this world") from None
        if not isinstance(state, cls):
            raise KernelError(f"domain {cls.DOMAIN!r} holds {type(state).__name__}")
        return state

    def has(self, cls: type[DomainState]) -> bool:
        return cls.DOMAIN in self.domains

    def __iter__(self) -> Iterator[tuple[str, DomainState]]:
        for name in sorted(self.domains):
            yield name, self.domains[name]

    # -- identity -----------------------------------------------------------------
    @property
    def tick(self) -> int:
        return self.meta.tick

    def next_event_seq(self) -> int:
        self.meta.event_seq += 1
        return self.meta.event_seq

    def next_fact_seq(self) -> int:
        self.meta.fact_seq += 1
        return self.meta.fact_seq

    #: Fields that describe the *run* rather than the world, and are therefore excluded from
    #: the state hash. Telemetry is a report about a simulation: a world resumed from a
    #: snapshot has the same city in it, but its gauges have only been observed since the
    #: moment it resumed.
    HASH_EXCLUDED: ClassVar[dict[str, tuple[str, ...]]] = {"kernel": ("metrics",)}

    def state_hash(self) -> str:
        """Canonical hash of the entire world. The determinism test compares these.

        Computed from the live objects with float quantisation, never from the snapshot
        payload, so a world and the same world reloaded from disk hash identically.
        """

        payload = {
            "meta": encode(self.meta),
            "domains": {name: encode(state) for name, state in sorted(self.domains.items())},
        }
        _strip_excluded(payload["domains"], self.HASH_EXCLUDED)
        return content_hash(payload)

    def domains_hash(self) -> str:
        """Hash of the world without its identity card.

        Two worlds can be the same city under different names — a replay, a fork, a run with
        a different ``world_id``. This compares what is in them, not what they are called.
        """

        domains = {name: encode(state) for name, state in sorted(self.domains.items())}
        _strip_excluded(domains, self.HASH_EXCLUDED)
        return content_hash(domains)

    # -- serialization ------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Exact, lossless encoding — this is what a snapshot stores."""

        return {
            "meta": encode(self.meta, quantize=False),
            "domains": {
                name: encode(state, quantize=False) for name, state in sorted(self.domains.items())
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WorldState":
        meta = decode(WorldMeta, raw["meta"])
        state = cls(meta=meta)
        registry = domain_registry()
        for name, payload in raw.get("domains", {}).items():
            domain_cls = registry.get(name)
            if domain_cls is None:
                raise KernelError(
                    f"snapshot contains unknown domain {name!r}; "
                    "the composing package must be imported before loading"
                )
            state.domains[name] = decode(domain_cls, payload)
        return state
