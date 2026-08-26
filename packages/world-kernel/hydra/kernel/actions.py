"""Action pipeline (spec section 36).

Nothing in the world mutates state directly. Brains — rule based or LLM based — produce an
``ActionIntent``. The kernel validates it against world rules and resources, executes it, and
emits the resulting event. This is the single choke point that makes an LLM safe: it can
propose anything it likes and still cannot corrupt the world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .errors import ActionRejected


@dataclass(slots=True)
class ActionIntent:
    action: str
    actor: str
    params: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    source: str = "rules"          # rules | utility | llm:<model> | scenario | institution
    importance: float = 0.1
    causes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ActionResult:
    intent: ActionIntent
    accepted: bool
    reason: str = ""
    detail: str = ""
    event_id: str | None = None
    outcome: dict[str, Any] = field(default_factory=dict)


class ActionHandler(Protocol):
    """One handler per action verb. Validation and execution are deliberately separate."""

    action: str

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        """Raise :class:`ActionRejected` if the world forbids this intent."""

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        """Apply the mutation. Must be called only after :meth:`validate` passed."""


class ActionPipeline:
    __slots__ = ("_handlers", "rejections", "executions", "last_rejections")

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}
        self.rejections = 0
        self.executions = 0
        self.last_rejections: list[ActionResult] = []

    def register(self, handler: ActionHandler) -> ActionHandler:
        if handler.action in self._handlers:
            raise ValueError(f"action {handler.action!r} already registered")
        self._handlers[handler.action] = handler
        return handler

    def known_actions(self) -> list[str]:
        return sorted(self._handlers)

    def submit(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        handler = self._handlers.get(intent.action)
        if handler is None:
            return self._reject(intent, "unknown_action", intent.action)
        try:
            handler.validate(ctx, intent)
        except ActionRejected as exc:
            return self._reject(intent, exc.reason, exc.detail)
        try:
            result = handler.execute(ctx, intent)
        except ActionRejected as exc:
            return self._reject(intent, exc.reason, exc.detail)
        self.executions += 1
        return result

    def _reject(self, intent: ActionIntent, reason: str, detail: str) -> ActionResult:
        self.rejections += 1
        result = ActionResult(intent=intent, accepted=False, reason=reason, detail=detail)
        self.last_rejections.append(result)
        if len(self.last_rejections) > 64:
            del self.last_rejections[:-64]
        return result
