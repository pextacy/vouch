"""stdout framing.

stdout is the JSON-RPC channel and nothing else. Every write goes through
:func:`write_frame`, which holds a lock (invokes run on a thread pool, and two
interleaved partial lines would corrupt the stream) and flushes, because a
buffered response is a response the host never sees.

A response above the host's 512 KiB soft cap is refused rather than spilled to a
temp file: every payload this engine produces is bounded well below the cap,
and a CV-derived body on disk would break the one
storage rule the product makes — CV content lives in the user's Anna storage and
nowhere else.
"""

from __future__ import annotations

import json
import sys
import threading
from typing import Any, Final, TextIO

#: Per-message soft cap enforced by the Agent.
MAX_STDIO_MESSAGE_BYTES: Final[int] = 512 * 1024

_LOCK: Final[threading.Lock] = threading.Lock()


def log(message: str) -> None:
    """Developer log. stderr only — never CV content, never token values."""
    print(f"[receipts-engine] {message}", file=sys.stderr, flush=True)


def write_frame(message: dict[str, Any], *, stdout: TextIO | None = None) -> None:
    out = stdout if stdout is not None else sys.stdout
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    size = len(payload.encode("utf-8"))
    if size > MAX_STDIO_MESSAGE_BYTES:
        replacement = _oversized(message, size)
        if replacement is None:
            return  # a notification nobody is waiting for: drop it
        payload = json.dumps(replacement, ensure_ascii=False, separators=(",", ":"))
    with _LOCK:
        out.write(payload + "\n")
        out.flush()


def _oversized(message: dict[str, Any], size: int) -> dict[str, Any] | None:
    """Replace a too-large frame with an error the caller can act on.

    Writing the body to a temp file would put CV-derived text on disk, which
    this engine never does. The size itself is the bug — every action's payload
    is bounded — so it is reported as one instead of being worked around.
    """
    log(f"response of {size} B exceeds the {MAX_STDIO_MESSAGE_BYTES} B stdio cap — refusing")
    req_id = message.get("id")
    if req_id is None:
        return None
    return error(req_id, -32603, "response exceeded the host's 512 KiB message cap")


def response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def error(req_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if data:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": body}
