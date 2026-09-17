"""Reverse RPC ``sampling/createMessage`` — the host runs the model for us.

The plugin has no API key: it asks the host for a completion, and Anna handles
model choice, billing and the user's quota. The awkward part of the protocol is
that the *same* stdin reader receives both host→plugin requests and host
replies to our own reverse RPCs, so :meth:`SamplingClient.dispatch_response`
must be called from the reader loop for every frame without a ``method``.

Host-enforced caps worth remembering:
8 192 tokens per call · 8 calls per invoke · 32 000 cumulative tokens per
invoke. The cumulative cap is the one that bites — it is per ``invoke_id``, not
per call.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from .context import stamp_context
from .frames import write_frame

METHOD: Final[str] = "sampling/createMessage"

PROTOCOL_V1: Final[str] = "1.1"
PROTOCOL_V2: Final[str] = "2.0"

#: Per-call ceiling the host enforces.
MAX_TOKENS_PER_CALL: Final[int] = 8192

ERR_NOT_GRANTED: Final[int] = -32001
ERR_QUOTA_EXCEEDED: Final[int] = -32002
ERR_PROVIDER_ERROR: Final[int] = -32003
ERR_INVALID_REQUEST: Final[int] = -32004
ERR_TIMEOUT: Final[int] = -32005
ERR_MAX_CALLS_EXCEEDED: Final[int] = -32006
ERR_MAX_TOKENS_EXCEEDED: Final[int] = -32007
ERR_NOT_NEGOTIATED: Final[int] = -32008
ERR_USER_DENIED: Final[int] = -32009
ERR_UNSUPPORTED_RESPONSE_FORMAT: Final[int] = -32010


class SamplingError(Exception):
    """A JSON-RPC error returned by the host for a sampling call."""

    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data or {}


@dataclass
class _Pending:
    future: asyncio.Future[dict[str, Any]]
    loop: asyncio.AbstractEventLoop


class SamplingClient:
    """One instance per process; multiplexes outstanding calls by request id."""

    def __init__(self, *, writer: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._write = writer or write_frame
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()
        self._disabled_reason: str | None = None

    # — wiring —

    def disable(self, reason: str) -> None:
        """Mark sampling unavailable (host negotiated v1, or no grant)."""
        self._disabled_reason = reason

    @property
    def available(self) -> bool:
        return self._disabled_reason is None

    def dispatch_response(self, message: dict[str, Any]) -> bool:
        """Resolve the pending call this frame answers. Returns True if handled."""
        if not isinstance(message, dict) or "method" in message:
            return False
        req_id = message.get("id")
        if not isinstance(req_id, str):
            return False
        with self._lock:
            pending = self._pending.pop(req_id, None)
        if pending is None:
            return False

        def resolve() -> None:
            if pending.future.done():
                return
            err = message.get("error")
            if err:
                pending.future.set_exception(
                    SamplingError(
                        int(err.get("code", -32603)),
                        str(err.get("message", "unknown sampling error")),
                        err.get("data"),
                    )
                )
            else:
                pending.future.set_result(message.get("result") or {})

        try:
            pending.loop.call_soon_threadsafe(resolve)
        except RuntimeError:  # loop already closed — best effort
            resolve()
        return True

    # — public API —

    async def create_message(
        self,
        *,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        stop_sequences: list[str] | None = None,
        response_format: dict[str, Any] | None = None,
        on_unsupported: str | None = None,
        timeout: float = 75.0,
    ) -> dict[str, Any]:
        """Run one completion. Raises :class:`SamplingError` on host failure.

        ``temperature`` is always sent: the host substitutes 0.7 for ``None``
        rather than deferring to the provider default, and 0.7 is far too loose
        for structured extraction.
        """
        if self._disabled_reason:
            raise SamplingError(ERR_NOT_NEGOTIATED, self._disabled_reason)
        if not messages:
            raise ValueError("messages must be a non-empty list")
        if max_tokens <= 0 or max_tokens > MAX_TOKENS_PER_CALL:
            raise ValueError(f"max_tokens must be in 1..{MAX_TOKENS_PER_CALL}")

        loop = asyncio.get_running_loop()
        req_id = uuid.uuid4().hex
        params: dict[str, Any] = {
            "messages": messages,
            "maxTokens": max_tokens,
            "includeContext": "none",
            "temperature": temperature,
            # Tells the host how long we will wait, so matrix-agent and the
            # nexus gate can cap their own deadlines inside our budget and we
            # never pay for a completion we already gave up on.
            "_clientTimeoutS": float(timeout),
        }
        if system_prompt is not None:
            params["systemPrompt"] = system_prompt
        if stop_sequences:
            params["stopSequences"] = stop_sequences
        if response_format is not None:
            params["responseFormat"] = response_format
        if on_unsupported is not None:
            params["onUnsupported"] = on_unsupported

        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        with self._lock:
            self._pending[req_id] = _Pending(future=future, loop=loop)

        envelope = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": METHOD,
            "params": stamp_context(params),
        }
        try:
            self._write(envelope)
        except Exception:
            with self._lock:
                self._pending.pop(req_id, None)
            raise

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            with self._lock:
                self._pending.pop(req_id, None)
            raise SamplingError(ERR_TIMEOUT, f"sampling timed out after {timeout}s") from None


def text_of(result: dict[str, Any]) -> str:
    """Pull the completion text out of a host sampling result."""
    content = result.get("content")
    if isinstance(content, dict) and content.get("type") == "text":
        return str(content.get("text") or "")
    if isinstance(content, list):  # defensive: MCP allows a content array
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(parts)
    return ""
