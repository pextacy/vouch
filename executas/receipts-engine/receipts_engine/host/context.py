"""Per-invoke correlation.

Every reverse RPC and every progress notification must carry the parent
``invoke_id``; without it the host cannot attribute the frame and drops it
silently. Invokes run concurrently on a thread pool, so the binding lives in a
:class:`~contextvars.ContextVar` rather than a module global.
"""

from __future__ import annotations

import contextlib
import math
import time
from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

_CURRENT_INVOKE_ID: ContextVar[str | None] = ContextVar("receipts_invoke_id", default=None)


@dataclass(frozen=True)
class InvokeContext:
    """Typed view of ``params`` / ``params.context`` for one invocation."""

    invoke_id: str | None = None
    deadline_ms: int | None = None

    @classmethod
    def from_params(cls, params: Mapping[str, Any] | None) -> InvokeContext:
        if not isinstance(params, Mapping):
            return cls()
        raw_ctx = params.get("context")
        ctx: Mapping[str, Any] = raw_ctx if isinstance(raw_ctx, Mapping) else {}
        deadline = ctx.get("deadline_ms")
        try:
            deadline_ms = int(deadline) if deadline is not None else None
        except (TypeError, ValueError):
            deadline_ms = None
        invoke_id = ctx.get("invoke_id") or params.get("invoke_id")
        return cls(
            invoke_id=str(invoke_id) if invoke_id else None,
            deadline_ms=deadline_ms,
        )

    def remaining_s(self) -> float:
        """Seconds left in the host's budget, or ``inf`` when none was given."""
        if self.deadline_ms is None:
            return math.inf
        return max(0.0, (self.deadline_ms / 1000.0) - time.time())


def current_invoke_id() -> str | None:
    return _CURRENT_INVOKE_ID.get()


@contextlib.contextmanager
def bind_invoke(params_or_id: Mapping[str, Any] | str | None) -> Iterator[str | None]:
    """Bind the current invoke for the duration of the block."""
    if isinstance(params_or_id, str) or params_or_id is None:
        invoke_id = params_or_id or None
    else:
        invoke_id = InvokeContext.from_params(params_or_id).invoke_id
    token = _CURRENT_INVOKE_ID.set(invoke_id)
    try:
        yield invoke_id
    finally:
        _CURRENT_INVOKE_ID.reset(token)


def stamp_context(params: dict[str, Any]) -> dict[str, Any]:
    """Add ``context.invoke_id`` from the current binding, if any."""
    invoke_id = _CURRENT_INVOKE_ID.get()
    if not invoke_id:
        return params
    ctx = params.get("context")
    if not isinstance(ctx, dict):
        ctx = {}
        params["context"] = ctx
    ctx.setdefault("invoke_id", invoke_id)
    return params
