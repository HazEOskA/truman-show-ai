"""LLM gateway: budget, escalation ladder and the intent contract.

The ladder is always ``rules → small model → large model`` (spec section 27). A model is
consulted only when the decision is important enough *and* the agent still has budget, and
its answer is an action proposal that the kernel then validates like any other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from hydra.kernel.actions import ActionIntent
from hydra.kernel.clock import TICKS_PER_DAY
from hydra.kernel.config import LLMConfig

from ..model import ComputeBudget, Person, Tier
from ..view import AgentView
from .adapter import LLMAdapter, LLMResponse, LLMUnavailable

SYSTEM_PROMPT = """You are one inhabitant of the simulated city of Hydra.
You only know what is in the payload; you cannot see the world state, other people's minds or the future.
Choose exactly one action from the allowed list and reply with a single JSON object:
{"action": "<one of the allowed actions>", "params": {...}, "rationale": "<12 words max>"}
No prose, no markdown, no explanation outside the JSON."""


@dataclass(slots=True)
class GatewayStats:
    calls: int = 0
    tokens: int = 0
    failures: int = 0
    declined: int = 0


class LLMGateway:
    def __init__(self, adapter: LLMAdapter, config: LLMConfig) -> None:
        self.adapter = adapter
        self.config = config
        self.stats = GatewayStats()
        self.enabled = bool(config.enabled and getattr(adapter, "enabled", False))
        self._calls_this_tick = 0
        self._tick = -1

    # -- budgeting ----------------------------------------------------------------
    def reset_daily(self, budget: ComputeBudget, tick: int) -> None:
        day = tick // TICKS_PER_DAY
        if budget.day_of_last_reset != day:
            budget.day_of_last_reset = day
            budget.calls_used_today = 0
            budget.tokens_used_today = 0
            budget.reasoning_used = 0

    def may_call(self, person: Person, importance: float, tick: int) -> str:
        """Returns the model to use, or an empty string to stay on rules."""

        if not self.enabled or person.tier is not Tier.PERSISTENT:
            return ""
        if tick != self._tick:
            self._tick = tick
            self._calls_this_tick = 0
        if self._calls_this_tick >= self.config.max_calls_per_tick:
            return ""
        budget = person.compute
        self.reset_daily(budget, tick)
        if budget.calls_used_today >= budget.llm_calls_per_day:
            return ""
        if budget.tokens_used_today >= budget.token_budget:
            return ""
        if importance >= self.config.large_model_importance:
            return self.config.large_model
        if importance >= self.config.escalation_importance:
            return self.config.small_model
        return ""

    # -- proposal -----------------------------------------------------------------
    def propose(self, person: Person, view: AgentView, allowed: list[str], model: str) -> ActionIntent | None:
        prompt = json.dumps(
            {"allowed_actions": allowed, **view.to_prompt_payload()},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        try:
            response: LLMResponse = self.adapter.complete(
                system=SYSTEM_PROMPT, prompt=prompt, model=model, max_tokens=256
            )
        except LLMUnavailable:
            self.stats.failures += 1
            return None

        self.stats.calls += 1
        self.stats.tokens += response.total_tokens
        self._calls_this_tick += 1
        person.compute.calls_used_today += 1
        person.compute.tokens_used_today += response.total_tokens
        person.last_llm_tick = view.tick

        intent = self._parse(response.text, person.person_id, allowed)
        if intent is None:
            self.stats.failures += 1
            return None
        intent.source = f"llm:{response.model}"
        return intent

    @staticmethod
    def _parse(text: str, person_id: str, allowed: list[str]) -> ActionIntent | None:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        action = str(payload.get("action", "")).strip()
        if action not in allowed:
            return None                      # the kernel would reject it anyway; save the trip
        params = payload.get("params", {})
        if not isinstance(params, dict):
            params = {}
        return ActionIntent(
            action=action,
            actor=person_id,
            params={str(k): v for k, v in params.items()},
            rationale=str(payload.get("rationale", ""))[:120],
            source="llm",
            importance=0.6,
        )
