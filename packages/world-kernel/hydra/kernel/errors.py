"""Kernel error taxonomy."""

from __future__ import annotations


class KernelError(Exception):
    """Base class for all kernel failures."""


class DeterminismError(KernelError):
    """Raised when a replay or verification produces a different state hash."""


class SealedTimelineError(KernelError):
    """Raised on any attempt to mutate a sealed timeline's past."""


class ActionRejected(KernelError):
    """Raised when an action intent fails validation.

    Rejections are normal world behaviour (an agent tried to buy bread it cannot afford),
    so they are caught by the pipeline and turned into rejection events.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class SystemFailure(KernelError):
    """Raised when a domain system crashes during a tick."""


class ContractViolation(KernelError):
    """Raised when a system touches a domain it did not declare."""
