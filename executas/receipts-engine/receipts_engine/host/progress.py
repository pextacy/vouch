"""``executa/progress`` notifications — the only thing driving the UI animation.

Best-effort by contract: the host rate-limits to 50 events/s per invoke, keeps
the latest 500, caps ``data`` at 8 KB, and drops everything during a plain
synchronous ``tools.invoke``. So this function never raises and never blocks the
pipeline — a lost progress event costs an animation frame, not a result.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, Literal, TextIO

from .context import current_invoke_id
from .frames import write_frame

METHOD: Final[str] = "executa/progress"

ProgressType = Literal["progress", "tool_update"]

#: Host stores at most 8 KB per event; stay well under it so a long partial
#: list is truncated here rather than rejected there.
_MAX_DATA_BYTES: Final[int] = 6 * 1024

Stage = Literal["normalize", "extract", "match", "guard", "summarize", "done"]


def emit_progress(
    stage: Stage,
    pct: int,
    partial: Mapping[str, Any] | None = None,
    *,
    type_: ProgressType = "tool_update",
    invoke_id: str | None = None,
    stdout: TextIO | None = None,
) -> bool:
    """Publish one stage update. Returns whether the frame was written."""
    resolved = invoke_id or current_invoke_id()
    if not resolved:
        return False

    data: dict[str, Any] = {"stage": stage, "pct": max(0, min(100, int(pct)))}
    if partial:
        trimmed = dict(partial)
        if len(json.dumps(trimmed, ensure_ascii=False).encode("utf-8")) > _MAX_DATA_BYTES:
            trimmed = _shrink(trimmed)
        data["partial"] = trimmed

    try:
        write_frame(
            {
                "jsonrpc": "2.0",
                "method": METHOD,
                "params": {"type": type_, "data": data, "context": {"invoke_id": resolved}},
            },
            stdout=stdout,
        )
    except Exception:  # noqa: BLE001 — progress must never break the tool
        return False
    return True


def _shrink(partial: dict[str, Any]) -> dict[str, Any]:
    """Halve every list in the payload until it fits the host's cap."""
    out = dict(partial)
    for _ in range(8):
        if len(json.dumps(out, ensure_ascii=False).encode("utf-8")) <= _MAX_DATA_BYTES:
            break
        shrunk = False
        for key, value in list(out.items()):
            if isinstance(value, list) and len(value) > 1:
                out[key] = value[: len(value) // 2]
                shrunk = True
        if not shrunk:
            break
    out["truncated"] = True
    return out
