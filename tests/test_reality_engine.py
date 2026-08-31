"""Hydra Reality Engine v0.1 acceptance tests.

The first vertical slice follows one material chain from natural stock to a consumer good.
If a stage invents its required stock, teleports it between locations, or skips time, these
assertions fail.
"""

from __future__ import annotations

import pytest

from hydra.reality import ProcessDefinition, ProcessStatus, RealityEngine, ResourceDefinition


def _engine() -> RealityEngine:
    engine = RealityEngine()
    for code, unit, category in (
        ("standing_timber", "kg", "natural"),
        ("logs", "kg", "material"),
        ("lumber", "kg", "material"),
        ("sawdust", "kg", "byproduct"),
        ("steel", "kg", "material"),
        ("glue", "kg", "material"),
        ("electricity", "kWh", "energy"),
        ("labour", "hour", "labour"),
        ("chair", "unit", "consumer"),
    ):
        engine.register_resource(ResourceDefinition(code, unit, category))

    for location in ("forest", "sawmill", "furniture_factory", "shop"):
        engine.add_location(location)

    engine.register_process(
        ProcessDefinition(
            code="harvest_tree",
            duration_minutes=120,
            inputs={"standing_timber": 10.0, "labour": 1.0},
            outputs={"logs": 10.0},
        )
    )
    engine.register_process(
        ProcessDefinition(
            code="haul_logs",
            duration_minutes=60,
            inputs={"logs": 10.0, "electricity": 0.5},
            outputs={"logs": 10.0},
        )
    )
    engine.register_process(
        ProcessDefinition(
            code="saw_logs",
            duration_minutes=90,
            inputs={"logs": 10.0, "electricity": 0.5, "labour": 0.5},
            outputs={"lumber": 8.0},
            byproducts={"sawdust": 2.0},
        )
    )
    engine.register_process(
        ProcessDefinition(
            code="haul_lumber",
            duration_minutes=45,
            inputs={"lumber": 8.0, "electricity": 0.4},
            outputs={"lumber": 8.0},
        )
    )
    engine.register_process(
        ProcessDefinition(
            code="make_chair",
            duration_minutes=48,
            inputs={
                "lumber": 8.0,
                "steel": 0.7,
                "glue": 0.15,
                "electricity": 1.4,
                "labour": 0.8,
            },
            outputs={"chair": 1.0},
        )
    )
    engine.register_process(
        ProcessDefinition(
            code="deliver_chair",
            duration_minutes=30,
            inputs={"chair": 1.0, "electricity": 0.2},
            outputs={"chair": 1.0},
        )
    )
    return engine


def _run(engine: RealityEngine, code: str, source: str, destination: str, minutes: int) -> None:
    process = engine.start(code, input_location_id=source, output_location_id=destination)
    assert process.status is ProcessStatus.RUNNING
    engine.advance(minutes)
    assert process.status is ProcessStatus.COMPLETE


def test_forest_to_chair_has_time_location_and_provenance() -> None:
    engine = _engine()

    # Natural capital / upstream support is explicit and auditable, never a hidden spawn.
    engine.seed_resource("forest", "standing_timber", 10.0, source="genesis:forest_cell_001")
    engine.seed_resource("forest", "labour", 1.0, source="genesis:workforce")
    engine.seed_resource("forest", "electricity", 0.5, source="genesis:vehicle_energy")
    engine.seed_resource("sawmill", "electricity", 0.5, source="genesis:grid")
    engine.seed_resource("sawmill", "labour", 0.5, source="genesis:workforce")
    engine.seed_resource("sawmill", "electricity", 0.4, source="genesis:vehicle_energy")
    engine.seed_resource("furniture_factory", "steel", 0.7, source="genesis:upstream_supply")
    engine.seed_resource("furniture_factory", "glue", 0.15, source="genesis:upstream_supply")
    engine.seed_resource("furniture_factory", "electricity", 1.6, source="genesis:grid")
    engine.seed_resource("furniture_factory", "labour", 0.8, source="genesis:workforce")

    _run(engine, "harvest_tree", "forest", "forest", 120)
    assert engine.state.locations["forest"].quantity("standing_timber") == pytest.approx(0)
    assert engine.state.locations["forest"].quantity("logs") == pytest.approx(10)

    _run(engine, "haul_logs", "forest", "sawmill", 60)
    assert engine.state.locations["forest"].quantity("logs") == pytest.approx(0)
    assert engine.state.locations["sawmill"].quantity("logs") == pytest.approx(10)

    _run(engine, "saw_logs", "sawmill", "sawmill", 90)
    assert engine.state.locations["sawmill"].quantity("lumber") == pytest.approx(8)
    assert engine.state.locations["sawmill"].quantity("sawdust") == pytest.approx(2)

    _run(engine, "haul_lumber", "sawmill", "furniture_factory", 45)
    _run(engine, "make_chair", "furniture_factory", "furniture_factory", 48)
    _run(engine, "deliver_chair", "furniture_factory", "shop", 30)

    shop_batches = engine.state.locations["shop"].inventory["chair"]
    assert len(shop_batches) == 1
    chair = shop_batches[0]
    assert chair.quantity == pytest.approx(1)
    assert engine.state.minute == 393

    chain = engine.provenance_chain(chair.batch_id)
    process_codes = [
        engine.state.running[event.process_id].definition_code
        for event in chain
        if event.kind == "process"
    ]
    assert process_codes == [
        "harvest_tree",
        "haul_logs",
        "saw_logs",
        "haul_lumber",
        "make_chair",
        "deliver_chair",
    ]
    assert "genesis:forest_cell_001" in {event.source for event in chain if event.kind == "origin"}


def test_process_cannot_start_without_material() -> None:
    engine = _engine()
    engine.seed_resource("forest", "labour", 1.0, source="genesis:workforce")

    with pytest.raises(ValueError, match="insufficient standing_timber"):
        engine.start("harvest_tree", input_location_id="forest")


def test_origin_must_be_named() -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="non-empty source"):
        engine.seed_resource("forest", "standing_timber", 10.0, source="")
