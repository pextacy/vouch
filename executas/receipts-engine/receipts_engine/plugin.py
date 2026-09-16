#!/usr/bin/env python3
"""receipts-engine — the Executa stdio plugin behind Receipts.

One tool method, ``engine``, with an ``action`` discriminator. One Executa row
per app is the pattern the platform expects; adding a tool per behaviour would
mean a new catalogue entry every time the product grows a verb.

Three rules from ``docs/api-notes.md §2`` govern everything below:

1. **stdout is protocol-only.** Logs go to stderr through
   :func:`~receipts_engine.host.frames.log`. One stray ``print`` ends the
   process's usefulness.
2. **Never exit after a response.** The reader loop runs until stdin closes,
   because the host's replies to *our* reverse RPCs arrive on the same pipe.
3. **``describe`` returns the bare manifest; ``invoke`` returns
   ``{"success": true, "data": …}``.** The host's parser defaults ``success``
   to ``false``.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Final

from . import __version__
from .errors import EngineError
from .host.context import InvokeContext, bind_invoke
from .host.frames import error, log, response, write_frame
from .host.sampling import PROTOCOL_V2, SamplingClient
from .llm import LlmClient, TokenBudget
from .parse.cv import parse_cv
from .pipeline import run_match, tailor_bullets, write_letter
from .schemas import CVDoc, LetterResult, MatchResult, TailorResult
from .uploads import UploadBuffer

TOOL_NAME: Final[str] = "engine"

#: run_match may sit through two model calls; the UI drives it through
#: ``tools.invokeAsync``, whose job deadline is what really applies.
_LONG_TOOL_TIMEOUT_S: Final[int] = 900

_sampling = SamplingClient()
_uploads = UploadBuffer()

#: One event loop on its own thread. Invokes arrive on pool threads and hand
#: their coroutine to it, so a long sampling call never blocks the stdin reader
#: that has to deliver that call's reply.
_loop = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=_loop.run_forever, name="engine-loop", daemon=True)
_loop_thread.start()


# ─── Manifest ─────────────────────────────────────────────────────────


def _tool_id() -> str:
    """Read the tool id from ``executa.json`` beside the package.

    The Agent joins a running plugin to the user's installed Executa by exact
    string match on this name, and ``executa.json`` is the file the publish
    flow and ``scripts/set-tool-id.py`` both write. Reading it here means there
    is one source of truth instead of a constant that drifts.
    """
    candidate = Path(__file__).resolve().parent.parent / "executa.json"
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
        tool_id = data.get("tool_id")
        if isinstance(tool_id, str) and tool_id:
            return tool_id
    except (OSError, json.JSONDecodeError) as exc:
        log(f"could not read executa.json ({type(exc).__name__}); falling back")
    return "tool-dev-receipts-engine"


MANIFEST: Final[dict[str, Any]] = {
    "name": _tool_id(),
    "display_name": "Receipts Engine",
    "version": __version__,
    "description": (
        "Parses a CV into numbered lines, extracts the stated requirements from a job "
        "posting, matches each requirement to the CV lines that evidence it, and "
        "rewrites bullets and cover letters that a deterministic verifier has proved "
        "are grounded in the CV."
    ),
    "author": "Receipts",
    "license": "MIT",
    "tags": ["career", "cv", "resume", "job-search", "anna-app"],
    # Without this the host refuses every sampling/createMessage with -32008,
    # even after a successful v2 handshake.
    "host_capabilities": ["llm.sample"],
    "runtime": {"type": "uv"},
    "tools": [
        {
            "name": TOOL_NAME,
            "description": (
                "Receipts engine. Pick a behaviour with `action`: "
                "`health` (liveness), "
                "`upload_chunk` (stream a CV file in base64 pieces), "
                "`parse_cv` (turn a CV into numbered lines), "
                "`run_match` (check a job posting against the CV — the primary function), "
                "`tailor` (rewrite CV bullets for this posting), "
                "`letter` (write a grounded cover letter), "
                "`export_docx` (render the accepted output as a DOCX)."
            ),
            "parameters": [
                {
                    "name": "action",
                    "type": "string",
                    "description": "Which behaviour to run.",
                    "required": True,
                    "enum": [
                        "health",
                        "upload_chunk",
                        "parse_cv",
                        "run_match",
                        "tailor",
                        "letter",
                        "export_docx",
                    ],
                },
                {
                    "name": "source",
                    "type": "string",
                    "description": "parse_cv: where the CV came from.",
                    "required": False,
                    "enum": ["pdf", "docx", "text"],
                },
                {
                    "name": "text",
                    "type": "string",
                    "description": "parse_cv: the pasted CV text, when source is 'text'.",
                    "required": False,
                },
                {
                    "name": "upload_id",
                    "type": "string",
                    "description": "upload_chunk / parse_cv: id of the chunked upload.",
                    "required": False,
                },
                {
                    "name": "index",
                    "type": "integer",
                    "description": "upload_chunk: zero-based chunk number; chunks arrive in order.",
                    "required": False,
                },
                {
                    "name": "total",
                    "type": "integer",
                    "description": "upload_chunk: how many chunks the file was split into.",
                    "required": False,
                },
                {
                    "name": "data_b64",
                    "type": "string",
                    "description": "upload_chunk: base64 of this chunk's bytes.",
                    "required": False,
                },
                {
                    "name": "filename",
                    "type": "string",
                    "description": "upload_chunk: original file name, for the warning copy.",
                    "required": False,
                },
                {
                    "name": "cv",
                    "type": "object",
                    "description": "run_match / tailor / letter: the CVDoc returned by parse_cv.",
                    "required": False,
                },
                {
                    "name": "posting_text",
                    "type": "string",
                    "description": "run_match: the full job posting text.",
                    "required": False,
                },
                {
                    "name": "posting_url",
                    "type": "string",
                    "description": "run_match: the posting's URL, when the user supplied one.",
                    "required": False,
                },
                {
                    "name": "match",
                    "type": "object",
                    "description": "tailor / letter: the MatchResult run_match returned.",
                    "required": False,
                },
                {
                    "name": "max_bullets",
                    "type": "integer",
                    "description": "tailor: how many bullets to suggest (default 8, max 12).",
                    "required": False,
                },
                {
                    "name": "tone",
                    "type": "string",
                    "description": "letter: voice of the cover letter.",
                    "required": False,
                    "enum": ["plain", "warm", "formal"],
                },
                {
                    "name": "length",
                    "type": "string",
                    "description": "letter: about 150 words (short) or 250 (standard).",
                    "required": False,
                    "enum": ["short", "standard"],
                },
                {
                    "name": "company",
                    "type": "string",
                    "description": "letter / export_docx: company name, when known.",
                    "required": False,
                },
                {
                    "name": "role",
                    "type": "string",
                    "description": "letter / export_docx: role title, when known.",
                    "required": False,
                },
                {
                    "name": "tailor_result",
                    "type": "object",
                    "description": "export_docx: the TailorResult to render.",
                    "required": False,
                },
                {
                    "name": "letter_result",
                    "type": "object",
                    "description": "export_docx: the LetterResult to render.",
                    "required": False,
                },
                {
                    "name": "locale",
                    "type": "string",
                    "description": "Output language for generated text.",
                    "required": False,
                    "enum": ["en", "tr"],
                    "default": "en",
                },
            ],
            "timeout": _LONG_TOOL_TIMEOUT_S,
        }
    ],
}


# ─── Actions ──────────────────────────────────────────────────────────


def _action_health(_args: dict[str, Any]) -> dict[str, Any]:
    # Deliberately not `ok`: an RPC envelope is `{ok, result}`, and a payload
    # that shares the field name invites a caller to unwrap it by mistake.
    return {
        "healthy": True,
        "version": __version__,
        "tool_id": MANIFEST["name"],
        "sampling": _sampling.available,
        "pending_uploads": len(_uploads),
    }


def _action_upload_chunk(args: dict[str, Any]) -> dict[str, Any]:
    return dict(
        _uploads.add_chunk(
            upload_id=str(args.get("upload_id") or ""),
            index=_as_int(args.get("index"), "index"),
            total=_as_int(args.get("total"), "total"),
            data_b64=str(args.get("data_b64") or ""),
            filename=_as_str(args.get("filename")),
        )
    )


def _action_parse_cv(args: dict[str, Any]) -> dict[str, Any]:
    source = str(args.get("source") or "text")
    if source == "text":
        doc = parse_cv(source="text", text=_as_str(args.get("text")))
        return doc.model_dump()

    upload_id = _as_str(args.get("upload_id"))
    if not upload_id:
        raise EngineError("invalid_args", "parse_cv needs upload_id for a file source")
    data, filename = _uploads.take(upload_id)
    doc = parse_cv(source=source, data=data, filename=filename)
    return doc.model_dump()


async def _action_run_match(args: dict[str, Any]) -> dict[str, Any]:
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    result = await run_match(
        _client(),
        cv=cv,
        posting_text=_as_str(args.get("posting_text")) or "",
        posting_url=_as_str(args.get("posting_url")),
        locale=_locale(args),
    )
    return result.model_dump()


async def _action_tailor(args: dict[str, Any]) -> dict[str, Any]:
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    match = _as_model(args.get("match"), MatchResult, "match")
    _assert_same_cv(cv, match)
    result = await tailor_bullets(
        _client(),
        cv=cv,
        match=match,
        max_bullets=_as_optional_int(args.get("max_bullets")),
        locale=_locale(args),
    )
    return result.model_dump()


async def _action_letter(args: dict[str, Any]) -> dict[str, Any]:
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    match = _as_model(args.get("match"), MatchResult, "match")
    _assert_same_cv(cv, match)
    result = await write_letter(
        _client(),
        cv=cv,
        match=match,
        tone=str(args.get("tone") or "plain"),
        length=str(args.get("length") or "standard"),
        company=_as_str(args.get("company")),
        role=_as_str(args.get("role")),
        locale=_locale(args),
    )
    return result.model_dump()


def _action_export_docx(args: dict[str, Any]) -> dict[str, Any]:
    from .export import MIME, build_docx

    tailor = (
        _as_model(args.get("tailor_result"), TailorResult, "tailor_result")
        if args.get("tailor_result")
        else None
    )
    letter = (
        _as_model(args.get("letter_result"), LetterResult, "letter_result")
        if args.get("letter_result")
        else None
    )
    if tailor is None and letter is None:
        raise EngineError("invalid_args", "export_docx needs tailor_result or letter_result")

    filename, content_b64 = build_docx(
        tailor=tailor,
        letter=letter,
        company=_as_str(args.get("company")),
        role=_as_str(args.get("role")),
        locale=_locale(args),
    )
    return {"filename": filename, "content_b64": content_b64, "mime": MIME}


_SYNC_ACTIONS: Final[dict[str, Any]] = {
    "health": _action_health,
    "upload_chunk": _action_upload_chunk,
    "parse_cv": _action_parse_cv,
    "export_docx": _action_export_docx,
}
_ASYNC_ACTIONS: Final[dict[str, Any]] = {
    "run_match": _action_run_match,
    "tailor": _action_tailor,
    "letter": _action_letter,
}


# ─── Argument helpers ─────────────────────────────────────────────────


def _client() -> LlmClient:
    """A fresh budget per invoke — the host's token cap is per invoke_id."""
    return LlmClient(_sampling, TokenBudget())


def _locale(args: dict[str, Any]) -> str:
    value = str(args.get("locale") or "en")
    return value if value in {"en", "tr"} else "en"


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineError("invalid_args", f"{field} must be an integer")
    return value


def _as_optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_model(value: Any, model: type[Any], field: str) -> Any:
    if not isinstance(value, dict):
        raise EngineError("invalid_args", f"{field} must be an object")
    try:
        return model.model_validate(value)
    except Exception as exc:  # pydantic ValidationError
        raise EngineError("invalid_args", f"{field} did not match its schema") from exc


def _assert_same_cv(cv: CVDoc, match: MatchResult) -> None:
    """Refuse to tailor one CV against another CV's match.

    The UI can only get this wrong after the user replaces their CV mid-flow,
    and the failure mode — citations pointing at lines that no longer exist —
    is exactly the kind of quiet wrongness this product exists to prevent.
    """
    if match.cv_hash != cv.hash:
        raise EngineError(
            "invalid_args",
            "this match was made against a different CV — run the match again",
        )


# ─── JSON-RPC handlers ────────────────────────────────────────────────


def _handle_invoke(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    tool = params.get("tool")
    if tool != TOOL_NAME:
        return error(req_id, -32601, f"unknown tool: {tool!r}")

    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        return error(req_id, -32602, "`arguments` must be an object")

    action = args.get("action")
    if not isinstance(action, str):
        return error(req_id, -32602, "`action` is required")

    context = InvokeContext.from_params(params)
    with bind_invoke(params):
        try:
            if action in _SYNC_ACTIONS:
                data = _SYNC_ACTIONS[action](args)
            elif action in _ASYNC_ACTIONS:
                data = _run_coroutine(_ASYNC_ACTIONS[action](args), context)
            else:
                return error(req_id, -32602, f"unknown action: {action!r}")
        except EngineError as exc:
            # A user-visible failure, not a protocol failure: `success: False`
            # keeps the host from counting the run, which matters because the
            # primary function is what the programme measures.
            log(f"action {action} failed: {exc.code}")
            return response(req_id, _failure(exc))
        except Exception as exc:  # noqa: BLE001 — never kill the reader loop
            log(f"action {action} crashed: {type(exc).__name__}: {exc}")
            return response(req_id, _failure(EngineError("internal_error", type(exc).__name__)))

    return response(req_id, {"success": True, "tool": TOOL_NAME, "data": data})


def _failure(exc: EngineError) -> dict[str, Any]:
    """Shape a failed invoke so the error code survives the host.

    The host strips both envelope layers and reports an inner failure as
    `tool_failed`, keeping only `result.error` as the message and dropping
    `result.data` entirely. So `error` carries the machine-readable code and
    nothing else — the sentence the user reads is the UI's, in their language,
    and `data` stays for the plugin tests and the stderr log.
    """
    return {"success": False, "tool": TOOL_NAME, "error": exc.code, "data": exc.to_dict()}


def _run_coroutine(coro: Any, context: InvokeContext) -> Any:
    """Run an async action on the shared loop, bounded by the host's deadline."""
    future = asyncio.run_coroutine_threadsafe(_with_invoke_id(coro, context.invoke_id), _loop)
    remaining = context.remaining_s()
    timeout = None if remaining == float("inf") else max(5.0, remaining)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        raise EngineError("sampling_unavailable", "the host deadline elapsed") from None


async def _with_invoke_id(coro: Any, invoke_id: str | None) -> Any:
    """Re-bind the invoke id inside the event loop's own context.

    ``run_coroutine_threadsafe`` does not carry the calling thread's
    ``contextvars`` across, so without this the pipeline would emit progress
    with no parent id and the host would drop every event as uncorrelated.
    """
    with bind_invoke(invoke_id):
        return await coro


def _handle_initialize(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    protocol = str((params or {}).get("protocolVersion") or "1.1")
    if protocol != PROTOCOL_V2:
        _sampling.disable(
            f"host negotiated protocolVersion={protocol!r}; sampling needs 2.0"
        )
    return response(
        req_id,
        {
            "protocolVersion": protocol if protocol in {"1.1", "2.0"} else "2.0",
            "serverInfo": {"name": MANIFEST["display_name"], "version": __version__},
            "client_capabilities": {"sampling": {}} if protocol == PROTOCOL_V2 else {},
            "capabilities": {},
        },
    )


def _handle_message(line: str) -> None:
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        write_frame(error(None, -32700, f"parse error: {exc}"))
        return
    if not isinstance(message, dict):
        return

    # A frame without `method` is the host answering one of our reverse RPCs.
    if "method" not in message:
        if not _sampling.dispatch_response(message):
            log(f"unmatched response id={message.get('id')!r}")
        return

    method = message.get("method")
    req_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    if method == "initialize":
        reply = _handle_initialize(req_id, params)
    elif method == "describe":
        reply = response(req_id, MANIFEST)  # bare manifest, never wrapped
    elif method == "health":
        reply = response(
            req_id,
            {
                "status": "healthy",
                "version": __version__,
                "tools_count": len(MANIFEST["tools"]),
            },
        )
    elif method == "invoke":
        reply = _handle_invoke(req_id, params)
    elif method == "shutdown":
        reply = response(req_id, {"ok": True})
    else:
        # The host's v1/v2 fallback depends on getting -32601 here.
        reply = error(req_id, -32601, f"method not found: {method}")

    if req_id is not None:
        write_frame(reply)


def main() -> None:
    log(f"{MANIFEST['display_name']} v{__version__} ready ({MANIFEST['name']})")
    # Invokes block on sampling replies that arrive on this very loop, so they
    # must not run on the reader thread.
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="invoke")
    try:
        for raw in sys.stdin:
            line = raw.strip()
            if line:
                pool.submit(_handle_message, line)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        _loop.call_soon_threadsafe(_loop.stop)


if __name__ == "__main__":
    main()
