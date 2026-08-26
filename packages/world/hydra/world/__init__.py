"""Composition root: assembles kernel, domains and systems into a runnable world.

Importing this package registers every domain state class, so snapshots taken by any process
can be decoded here.
"""

from .builder import (  # noqa: F401
    WorldRuntime,
    build_gateway,
    build_kernel,
    build_registry,
    create_world,
    load_world,
)
