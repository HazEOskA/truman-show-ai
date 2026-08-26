"""LLM provider adapters (rule 35.11: the provider must be an adapter).

Two real implementations ship: one that declines (the default, used whenever no provider is
configured) and one that talks to the Anthropic API. Neither is a mock — the declining
adapter is a policy, and the world is designed to run entirely on rules when it is active.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class LLMUnavailable(RuntimeError):
    """Raised when no model can serve a request. Callers must fall back to rules."""


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMAdapter(Protocol):
    name: str
    enabled: bool

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int) -> LLMResponse: ...


class DisabledAdapter:
    """Default adapter: there is no provider, so every request is declined.

    This is not a stub standing in for a real implementation — it is the supported production
    configuration. Hydra World's determinism tests require it.
    """

    name = "disabled"
    enabled = False

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int) -> LLMResponse:
        raise LLMUnavailable("no LLM provider configured; agents run on rules")


class AnthropicAdapter:
    """Talks to the Anthropic Messages API over HTTPS."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None, *, base_url: str = "https://api.anthropic.com", timeout: float = 30.0) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.enabled = bool(self.api_key)

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int) -> LLMResponse:
        if not self.enabled:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        payload = json.dumps(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=payload,
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(f"provider call failed: {exc}") from exc

        blocks = body.get("content", [])
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        usage = body.get("usage", {})
        return LLMResponse(
            text=text,
            model=body.get("model", model),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )


def build_adapter(provider: str, api_key: str | None = None) -> LLMAdapter:
    if provider == "anthropic":
        return AnthropicAdapter(api_key)
    return DisabledAdapter()
