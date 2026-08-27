"""The view model: the only thing the City View is allowed to see.

Between the simulation's domain objects and the renderer sits this layer, and nothing
crosses it unlabelled. Its job is threefold:

* **Translate.** Domain types never reach the browser. A ``Person`` becomes four small
  integers; a ``Building`` becomes an index and an occupancy count.
* **Compress.** One keyframe, then deltas -- columnar, integer-indexed, viewport-sized.
* **Qualify.** Every position carries where it came from. The world knows where some people
  are and not others, and the view says which is which instead of papering over it.

Nothing here computes economics, behaviour or consequence. If a number is not already in
world state, the view model does not have it, and the renderer does not get to invent it.
"""

from __future__ import annotations

from .frames import (
    ACTIVITY_CODES,
    SOURCE_CODES,
    TIER_CODES,
    AgentRow,
    CityFrame,
    apply_delta,
    build_delta,
    build_keyframe,
    frame_from_dict,
)
from .index import CityIndex, build_index
from .layers import LAYERS, Layer, LayerScope, compute_layers, layer_catalogue
from .presence import (
    Presence,
    PresenceReport,
    PresenceSource,
    is_working_hour,
    presence_of,
    resolve_all,
)
from .wire import projection_payload

__all__ = [
    "ACTIVITY_CODES",
    "AgentRow",
    "CityFrame",
    "CityIndex",
    "LAYERS",
    "Layer",
    "LayerScope",
    "Presence",
    "PresenceReport",
    "PresenceSource",
    "SOURCE_CODES",
    "TIER_CODES",
    "apply_delta",
    "build_delta",
    "build_index",
    "build_keyframe",
    "compute_layers",
    "frame_from_dict",
    "is_working_hour",
    "layer_catalogue",
    "presence_of",
    "projection_payload",
    "resolve_all",
]
