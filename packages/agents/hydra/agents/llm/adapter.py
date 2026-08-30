"""LLM provider adapters (rule 35.11: the provider must be an adapter).

Three real implementations ship: one that declines (the default, used whenever no provider is
configured) and two that talk to a hosted API — Anthropic over plain HTTPS, Gemini through
Google's official GenAI SDK. None of them is a mock — the declining adapter is a policy, and
the world is designed to run entirely on rules when it is active.

Adding a provider means adding a class here and a line in `build_adapter`, and nothing else:
the gateway above knows only this protocol, and the kernel below never learns a model was
consulted at all. That is the whole point of rule 35.11 — the simulation's mechanics cannot
come to depend on which company is answering.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


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


class GeminiAdapter:
    """Talks to Gemini through Google's official GenAI SDK (`google-genai`).

    The SDK rather than raw HTTP, and deliberately: it is the supported client, it resolves
    credentials the way Google Cloud expects, and it is what makes this a Google-framework
    integration rather than somebody's hand-rolled POST to a URL.

    Two credential paths, because a laptop and Cloud Run want different things:

    * an API key (``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``) — the Gemini API, for local runs;
    * Vertex AI, when ``GOOGLE_GENAI_USE_VERTEXAI`` is set — the SDK then resolves project,
      location and Application Default Credentials by itself, which is exactly what a Cloud
      Run service already has and means no key has to be minted or mounted at all.

    Three things about the call are load-bearing:

    * the system prompt goes in ``system_instruction``, a field of its own, so an agent's
      instructions can never be confused with its observations;
    * ``response_mime_type="application/json"`` constrains the model to the one JSON action
      object the gateway parses, instead of asking politely in the prompt and hoping;
    * **every** provider failure becomes :class:`LLMUnavailable`. The SDK raises a wide family
      of errors — API, transport, quota, auth — and none of them may reach the tick loop. An
      agent whose model is unreachable falls back to its rules, which is the same behaviour as
      having no provider configured at all. A simulation that stops because a network hiccuped
      would not be a simulation.
    """

    name = "gemini"

    def __init__(self, api_key: str | None = None, *, timeout: float | None = None) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        self.timeout = timeout
        self._client: Any = None
        self._types: Any = None
        self.enabled = False
        self.mode = "unconfigured"

        # Imported here, not at module scope. Hydra's supported default is to run with no
        # provider at all, and that path must not require a Google package to be installed.
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            self.mode = "sdk-missing"
            return

        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {"1", "true", "yes"}
        try:
            if self.api_key:
                self._client = genai.Client(api_key=self.api_key)
                self.mode = "api-key"
            elif use_vertex:
                self._client = genai.Client()          # project / location / ADC from the environment
                self.mode = "vertex"
            else:
                self.mode = "no-credentials"
                return
        except Exception:                              # noqa: BLE001 - see the class docstring
            self._client = None
            self.mode = "client-init-failed"
            return

        self._types = types
        self.enabled = True

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int) -> LLMResponse:
        if not self.enabled or self._client is None:
            raise LLMUnavailable(f"gemini adapter is not configured ({self.mode})")

        try:
            response = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    temperature=0.4,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:                       # noqa: BLE001 - see the class docstring
            raise LLMUnavailable(f"provider call failed: {exc}") from exc

        # `.text` is a convenience over the candidate parts and raises rather than returning
        # empty when the model produced none, so the refusal case is handled here as a normal
        # outcome instead of an exception escaping into the tick.
        try:
            text = (response.text or "").strip()
        except Exception:                              # noqa: BLE001 - see the class docstring
            text = ""
        if not text:
            raise LLMUnavailable("gemini returned no usable text")

        usage = getattr(response, "usage_metadata", None)
        return LLMResponse(
            text=text,
            model=getattr(response, "model_version", None) or model,
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
        )


def build_adapter(provider: str, api_key: str | None = None) -> LLMAdapter:
    if provider == "anthropic":
        return AnthropicAdapter(api_key)
    if provider in ("gemini", "google"):
        return GeminiAdapter(api_key)
    return DisabledAdapter()
