"""One typed call: prompt in, validated Pydantic model out.

Structured output is requested at the protocol level (``responseFormat``), but
the host only *asks* the provider for JSON — it returns a string either way and
reports validity informationally. So the contract here is: extract JSON
defensively, validate against the model, and on failure retry **once** with the
validation error fed back. A second failure is `model_output_invalid`, which the
UI shows as "The analysis didn't finish cleanly. Run it again."

The retry is what keeps `run_match` inside its budget: two pipeline calls plus
at most two repairs stays under the host's 8-calls-per-invoke cap.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Final, TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import EngineError
from ..host.frames import log
from ..host.sampling import (
    ERR_MAX_CALLS_EXCEEDED,
    ERR_MAX_TOKENS_EXCEEDED,
    ERR_NOT_GRANTED,
    ERR_NOT_NEGOTIATED,
    ERR_PROVIDER_ERROR,
    ERR_QUOTA_EXCEEDED,
    ERR_TIMEOUT,
    ERR_UNSUPPORTED_RESPONSE_FORMAT,
    SamplingClient,
    SamplingError,
    text_of,
)
from .json_schema import response_format

T = TypeVar("T", bound=BaseModel)

#: Cumulative token cap the host enforces per invoke_id. We track our own
#: estimate and stop early with a clear error rather than letting the host
#: reject the third call with -32007 mid-pipeline.
INVOKE_TOKEN_BUDGET: Final[int] = 30_000
INVOKE_CALL_BUDGET: Final[int] = 7

#: A provider blip or a slow completion is not the user's fault and not a
#: reason to throw away a run they have already waited a minute for. One retry
#: is all the per-invoke budget can carry without risking the later stages.
_TRANSIENT_RETRIES: Final[int] = 1
_RETRY_BACKOFF_S: Final[float] = 1.5

_FENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*(?P<body>[\[{].*?[\]}])\s*```", re.DOTALL
)


class TokenBudget:
    """Per-invoke accounting for the host's cumulative sampling caps."""

    def __init__(
        self, *, tokens: int = INVOKE_TOKEN_BUDGET, calls: int = INVOKE_CALL_BUDGET
    ) -> None:
        self.tokens_left = tokens
        self.calls_left = calls

    def reserve(self, estimated: int) -> None:
        if self.calls_left <= 0:
            raise EngineError(
                "sampling_unavailable", "per-invoke sampling call budget exhausted"
            )
        if estimated > self.tokens_left:
            raise EngineError(
                "sampling_unavailable", "per-invoke sampling token budget exhausted"
            )

    def spend(self, estimated: int) -> None:
        self.calls_left -= 1
        self.tokens_left -= estimated

    def can_afford(self, estimated: int) -> bool:
        """Whether another call of this size still fits — used before a retry."""
        return self.calls_left > 0 and estimated <= self.tokens_left


class LlmClient:
    """Schema-validated wrapper over :class:`SamplingClient`."""

    def __init__(self, sampling: SamplingClient, budget: TokenBudget | None = None) -> None:
        self._sampling = sampling
        self.budget = budget or TokenBudget()

    async def structured(
        self,
        *,
        name: str,
        model: type[T],
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.1,
        timeout: float = 75.0,
    ) -> T:
        """Run one completion and return it parsed into ``model``."""
        fmt = response_format(name, model)
        messages = [{"role": "user", "content": {"type": "text", "text": user_prompt}}]

        raw = await self._call(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=fmt,
            timeout=timeout,
        )
        try:
            return _parse(raw, model)
        except _OutputInvalid as first:
            log(f"{name}: output rejected ({first.reason}) — retrying once")

        # Retry with the failure quoted back. A model that produced almost-valid
        # JSON usually fixes it when told exactly what was wrong.
        messages.append({"role": "assistant", "content": {"type": "text", "text": raw[:2000]}})
        messages.append(
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "That response did not match the required schema. "
                        "Return the corrected JSON object only — no prose, no code fence."
                    ),
                },
            }
        )
        raw = await self._call(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.0,
            response_format=fmt,
            timeout=timeout,
        )
        try:
            return _parse(raw, model)
        except _OutputInvalid as second:
            raise EngineError(
                "model_output_invalid",
                f"{name} did not match the schema after one repair",
                details={"reason": second.reason},
            ) from second

    async def _call(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        max_tokens: int,
        temperature: float,
        response_format: dict[str, Any],
        timeout: float,
    ) -> str:
        estimated = _estimate(messages, system_prompt) + max_tokens
        attempt = 0
        while True:
            self.budget.reserve(estimated)
            try:
                result = await self._sampling.create_message(
                    messages=messages,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    response_format=response_format,
                    # A model without strict-schema support should fall back to
                    # plain JSON mode, not fail the user's run.
                    on_unsupported="json_object",
                    timeout=timeout,
                )
                break
            except SamplingError as exc:
                if attempt >= _TRANSIENT_RETRIES or not _is_transient(exc):
                    raise _translate(exc) from exc
                attempt += 1
                log(f"sampling failed with {exc.code} — retrying ({attempt}/{_TRANSIENT_RETRIES})")
            finally:
                self.budget.spend(estimated)
            if not self.budget.can_afford(estimated):
                # Retrying would only trade one failure for a budget failure.
                raise EngineError(
                    "sampling_unavailable", "no budget left to retry the model call"
                )
            await asyncio.sleep(_RETRY_BACKOFF_S * attempt)

        meta = (result.get("_meta") or {}).get("responseFormat") or {}
        if meta.get("downgraded"):
            log("host downgraded structured output to json_object mode")
        return text_of(result)


class _OutputInvalid(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _parse[T: BaseModel](raw: str, model: type[T]) -> T:
    payload = extract_json(raw)
    if payload is None:
        raise _OutputInvalid("no JSON object found in the completion")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        errors = exc.errors()
        if not errors:  # pragma: no cover - pydantic always reports at least one
            raise _OutputInvalid("validation failed") from exc
        first = errors[0]
        location = ".".join(str(part) for part in first["loc"])
        raise _OutputInvalid(f"{location or '(root)'}: {first['msg']}") from exc


def extract_json(raw: str) -> Any:
    """Best-effort JSON extraction from a completion.

    Tries the whole string, then a fenced block, then the outermost balanced
    ``{...}``. Models in ``json_object`` fallback mode occasionally wrap the
    object in prose; a run should not fail for that alone.
    """
    text = raw.strip()
    if not text:
        return None
    for candidate in _candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _candidates(text: str) -> list[str]:
    out = [text]
    fenced = _FENCE_RE.search(text)
    if fenced:
        out.append(fenced.group("body"))
    balanced = _outermost_object(text)
    if balanced:
        out.append(balanced)
    return out


def _outermost_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _estimate(messages: list[dict[str, Any]], system_prompt: str) -> int:
    chars = len(system_prompt)
    for message in messages:
        content = message.get("content")
        if isinstance(content, dict):
            chars += len(str(content.get("text") or ""))
    return int(chars / 3.6) + 1


def _is_transient(exc: SamplingError) -> bool:
    """Whether the host failure is worth one more attempt.

    A provider error or a timeout says nothing about the request; a quota,
    a missing grant or a refused format says the next attempt fails the same
    way, and retrying those would burn the user's budget to no end.
    """
    return exc.code in {ERR_PROVIDER_ERROR, ERR_TIMEOUT}


def _translate(exc: SamplingError) -> EngineError:
    """Map a host sampling error to a code the UI has copy for."""
    if exc.code in {
        ERR_NOT_GRANTED,
        ERR_NOT_NEGOTIATED,
        ERR_QUOTA_EXCEEDED,
        ERR_MAX_CALLS_EXCEEDED,
        ERR_MAX_TOKENS_EXCEEDED,
    }:
        return EngineError("sampling_unavailable", exc.message, details={"host_code": exc.code})
    if exc.code == ERR_UNSUPPORTED_RESPONSE_FORMAT:
        # on_unsupported="json_object" should have prevented this; if the host
        # still refuses, it is not something the user can fix by retrying.
        return EngineError(
            "model_output_invalid",
            "the selected model cannot produce structured output",
            details={"host_code": exc.code},
        )
    return EngineError("sampling_unavailable", exc.message, details={"host_code": exc.code})
