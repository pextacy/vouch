"""stdout framing.

stdout is the JSON-RPC channel and nothing else. Every write goes through
:func:`write_frame`, which holds a lock (invokes run on a thread pool, and two
interleaved partial lines would corrupt the stream) and flushes, because a
buffered response is a response the host never sees.

Responses above the host's 512 KiB soft cap are handed over as a file-transport
pointer instead of being pushed through the pipe.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from typing import Any, Final, TextIO

#: Per-message soft cap enforced by the Agent (docs/api-notes.md §2).
MAX_STDIO_MESSAGE_BYTES: Final[int] = 512 * 1024

_LOCK: Final[threading.Lock] = threading.Lock()


def log(message: str) -> None:
    """Developer log. stderr only — never CV content, never token values."""
    print(f"[receipts-engine] {message}", file=sys.stderr, flush=True)


def write_frame(message: dict[str, Any], *, stdout: TextIO | None = None) -> None:
    out = stdout if stdout is not None else sys.stdout
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_STDIO_MESSAGE_BYTES:
        payload = _spill_to_file(message, payload)
    with _LOCK:
        out.write(payload + "\n")
        out.flush()


def _spill_to_file(message: dict[str, Any], payload: str) -> str:
    """Write the body to a temp file and return the pointer envelope."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="receipts-resp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except Exception:
        os.close(fd)
        raise
    log(f"response exceeded {MAX_STDIO_MESSAGE_BYTES} B — using file transport")
    return json.dumps(
        {"jsonrpc": "2.0", "id": message.get("id"), "__file_transport": path},
        ensure_ascii=False,
    )


def response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def error(req_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if data:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": body}
