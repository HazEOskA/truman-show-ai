"""Canonical serialization and state hashing.

Two hard requirements drive this module:

1. Snapshots must round-trip a live state tree exactly, so replay can resume from them.
2. Two runs with the same seed, config and kernel version must produce the same *hash*.
   That means the encoding has to be canonical: sorted keys, quantised floats, no ``set``
   iteration order, no object identity leaking into the output.

Domain code stays free of boilerplate: dataclasses are encoded and decoded generically from
their type hints.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import typing
from typing import Any, TypeVar, get_args, get_origin

FLOAT_PRECISION = 6

_T = TypeVar("_T")
_HINT_CACHE: dict[type, dict[str, Any]] = {}
_FIELD_CACHE: dict[type, tuple[str, ...]] = {}


def _field_names(cls: type) -> tuple[str, ...]:
    names = _FIELD_CACHE.get(cls)
    if names is None:
        names = tuple(f.name for f in dataclasses.fields(cls))
        _FIELD_CACHE[cls] = names
    return names


def _hints(cls: type) -> dict[str, Any]:
    cached = _HINT_CACHE.get(cls)
    if cached is None:
        module = __import__(cls.__module__, fromlist=["*"])
        cached = typing.get_type_hints(cls, vars(module))
        _HINT_CACHE[cls] = cached
    return cached


def encode(value: Any, *, quantize: bool = True) -> Any:
    """Convert a live object graph into JSON-compatible primitives.

    ``quantize=True`` rounds floats, which is what makes a state *hash* stable against
    meaningless last-bit noise. Snapshots must instead round-trip exactly, or a world
    restored from disk would drift away from the one that wrote it — so they encode with
    ``quantize=False``.
    """

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not quantize:
            return value
        # -0.0 and 0.0 must hash identically.
        return round(value, FLOAT_PRECISION) + 0.0
    if isinstance(value, enum.Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            name: encode(getattr(value, name), quantize=quantize)
            for name in _field_names(type(value))
        }
    if isinstance(value, dict):
        return {str(k): encode(v, quantize=quantize) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v, quantize=quantize) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(encode(v, quantize=quantize) for v in value)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"cannot canonically encode {type(value)!r}")


def decode(target: Any, raw: Any) -> Any:
    """Rebuild a typed object graph from :func:`encode` output."""

    if target is Any:
        return raw
    origin = get_origin(target)
    if origin is typing.Union:
        args = [a for a in get_args(target) if a is not type(None)]
        if raw is None:
            return None
        if len(args) == 1:
            return decode(args[0], raw)
        return raw
    if origin in (list, tuple):
        args = get_args(target)
        if not args:
            return list(raw)
        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                return tuple(decode(args[0], v) for v in raw)
            return tuple(decode(a, v) for a, v in zip(args, raw))
        return [decode(args[0], v) for v in raw]
    if origin is dict:
        kt, vt = get_args(target) or (str, Any)
        return {(kt(k) if kt is not str else k): decode(vt, v) for k, v in raw.items()}
    if origin in (set, frozenset):
        (vt,) = get_args(target) or (Any,)
        return origin(decode(vt, v) for v in raw)
    if isinstance(target, type):
        if issubclass(target, enum.Enum):
            return target(raw)
        if dataclasses.is_dataclass(target):
            hints = _hints(target)
            kwargs = {}
            for field in dataclasses.fields(target):
                if field.name in raw:
                    kwargs[field.name] = decode(hints[field.name], raw[field.name])
            return target(**kwargs)
        if target is float:
            return float(raw)
        if target is int:
            return int(raw)
    return raw


def canonical_json(value: Any) -> bytes:
    """Deterministic byte representation used for hashing and snapshots."""

    return json.dumps(
        encode(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.blake2b(canonical_json(value), digest_size=16).hexdigest()
