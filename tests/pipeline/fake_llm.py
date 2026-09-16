"""A scripted sampling client, so the pipeline can be tested without a host.

It answers in the order responses are queued and records every request, which
is how the budget, the retry and the repair paths get asserted on. Anything the
real client would reject (an over-cap ``max_tokens``, a missing temperature) is
rejected here too, so a test passing against the fake means something.
"""

from __future__ import annotations

import json
from typing import Any

from receipts_engine.host.sampling import MAX_TOKENS_PER_CALL, SamplingError


class FakeSampling:
    """Stands in for :class:`receipts_engine.host.sampling.SamplingClient`."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self.responses: list[Any] = list(responses or [])
        self.requests: list[dict[str, Any]] = []
        self.available = True

    def queue(self, payload: Any) -> None:
        """Queue one reply: a dict/list is JSON-encoded, a str is sent verbatim."""
        self.responses.append(payload)

    def queue_error(self, code: int, message: str = "boom") -> None:
        self.responses.append(SamplingError(code, message))

    async def create_message(self, **kwargs: Any) -> dict[str, Any]:
        if not self.available:
            raise SamplingError(-32008, "sampling disabled")
        max_tokens = kwargs.get("max_tokens")
        if not isinstance(max_tokens, int) or not 0 < max_tokens <= MAX_TOKENS_PER_CALL:
            raise AssertionError(f"max_tokens out of range: {max_tokens!r}")
        if kwargs.get("temperature") is None:
            raise AssertionError("temperature must always be sent explicitly")
        self.requests.append(kwargs)

        if not self.responses:
            raise AssertionError("FakeSampling ran out of queued responses")
        payload = self.responses.pop(0)
        if isinstance(payload, SamplingError):
            raise payload
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return {
            "content": {"type": "text", "text": text},
            "model": "fake-model",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "_meta": {"responseFormat": {"structuredValid": True, "downgraded": False}},
        }
