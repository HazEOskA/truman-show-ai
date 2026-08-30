"""Jury-world creation keeps the normal deterministic default but can opt into Gemini."""

from __future__ import annotations

from hydra.persistence.filestore import FileStore
from hydra_api.service import WorldService


def test_create_world_can_persist_gemini_config(tmp_path):
    service = WorldService(FileStore(tmp_path))

    result = service.create_world(
        seed=20260830,
        world_id="world_jury_gemini",
        name="Hydra Jury Gemini",
        residents=1_000,
        persistent_agents=8,
        companies=16,
        llm_enabled=True,
        llm_provider="gemini",
        llm_model="gemini-3.5-flash",
    )

    config = service.config_for("world_jury_gemini")
    assert config.llm.enabled is True
    assert config.llm.provider == "gemini"
    assert config.llm.small_model == "gemini-3.5-flash"
    assert config.llm.large_model == "gemini-3.5-flash"
    assert result["llm"] == {
        "enabled": True,
        "provider": "gemini",
        "model": "gemini-3.5-flash",
    }


def test_create_world_still_defaults_to_rules_only(tmp_path):
    service = WorldService(FileStore(tmp_path))

    result = service.create_world(
        seed=20260831,
        world_id="world_rules_only",
        name="Hydra Rules",
        residents=1_000,
        persistent_agents=8,
        companies=16,
    )

    config = service.config_for("world_rules_only")
    assert config.llm.enabled is False
    assert config.llm.provider == "disabled"
    assert result["llm"]["enabled"] is False
    assert result["llm"]["provider"] == "disabled"
