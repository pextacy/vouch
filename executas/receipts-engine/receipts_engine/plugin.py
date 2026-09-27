#!/usr/bin/env python3
"""receipts-engine — the Executa stdio plugin behind Receipts.

One tool method, ``engine``, with an ``action`` discriminator. One Executa row
per app is the pattern the platform expects; adding a tool per behaviour would
mean a new catalogue entry every time the product grows a verb.

Three rules of the Executa protocol govern everything below:

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
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Final

from . import __version__
from .audit import audit_cv
from .check import check_document
from .compare import MAX_ITEMS as MAX_COMPARE_ITEMS
from .compare import compare_postings
from .errors import EngineError
from .host.context import InvokeContext, bind_invoke
from .host.frames import error, log, response, write_frame
from .host.sampling import PROTOCOL_V1, PROTOCOL_V2, SamplingClient
from .interview import interview_brief
from .ledger import MAX_ITEMS as MAX_LEDGER_ITEMS
from .ledger import line_ledger
from .limits import Limiter
from .llm import LlmClient, TokenBudget
from .parse.cv import parse_cv
from .pipeline import (
    answer_questions,
    clear_requirement_cache,
    plan_gaps,
    run_match,
    tailor_bullets,
    write_followup,
    write_letter,
    write_profile,
)
from .recurring import MAX_ITEMS, recurring_gaps
from .rerun import compare_runs
from .schemas import Assertion, CVDoc, LetterResult, MatchResult, RecurringInput, TailorResult
from .since import since_applied
from .uploads import UploadBuffer
from .worth import MAX_ITEMS as MAX_WORTH_ITEMS
from .worth import worth_rerunning

TOOL_NAME: Final[str] = "engine"

#: run_match may sit through two model calls; the UI drives it through
#: ``tools.invokeAsync``, whose job deadline is what really applies.
_LONG_TOOL_TIMEOUT_S: Final[int] = 900

#: Concurrent invokes. Each one may park on a sampling reply, so the reader
#: thread keeps dispatching those replies itself (see :func:`main`).
_INVOKE_WORKERS: Final[int] = 4

_sampling = SamplingClient()
_uploads = UploadBuffer()
_limits = Limiter()

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
                "`discard_upload` (drop one buffered upload by id), "
                "`parse_cv` (turn a CV into numbered lines), "
                "`audit_cv` (find what an interviewer will probe in the CV itself — no model), "
                "`check_document` (read a document the app did not write against the CV — no model), "
                "`recurring_gaps` (what keeps coming up across past applications — no model), "
                "`compare_postings` (which saved application the CV can prove most of — no model), "
                "`interview_brief` (what this application will be asked to back up — no model), "
                "`line_ledger` (which CV lines have been evidence, across past applications — no model), "
                "`since_applied` (what the CV has gained since one application went out — no model), "
                "`compare_runs` (what changed between two runs of the same posting — no model), "
                "`worth_rerunning` (which saved applications the CV has since gained an answer for — no model), "
                "`run_match` (check a job posting against the CV — the primary function), "
                "`gaps` (one question per requirement the CV cannot prove yet), "
                "`answer_question` (answer an application form's free-text questions from the CV alone), "
                "`tailor` (rewrite CV bullets for this posting), "
                "`letter` (write a grounded cover letter), "
                "`followup` (the note after the silence — or the refusal to write one), "
                "`profile` (a headline and an About section the CV can back, no posting involved), "
                "`export_docx` (render the accepted output as a DOCX), "
                "`export_cv` (render the stored CV, or only the lines the user added, as a DOCX), "
                "`forget` (drop everything this process still holds in memory)."
            ),
            "parameters": [
                {
                    "name": "action",
                    "type": "string",
                    "description": "Which behaviour to run.",
                    "required": True,
                    "enum": [
                        "health",
                        "forget",
                        "discard_upload",
                        "upload_chunk",
                        "parse_cv",
                        "audit_cv",
                        "check_document",
                        "recurring_gaps",
                        "compare_postings",
                        "interview_brief",
                        "line_ledger",
                        "since_applied",
                        "compare_runs",
                        "worth_rerunning",
                        "run_match",
                        "tailor",
                        "letter",
                        "followup",
                        "profile",
                        "gaps",
                        "answer_question",
                        "export_docx",
                        "export_cv",
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
                    "description": (
                        "upload_chunk / parse_cv / discard_upload: id of the "
                        "chunked upload. Unguessable by construction — it is "
                        "the only thing that entitles a caller to those bytes."
                    ),
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
                    "description": (
                        "run_match / tailor / letter / gaps / interview_brief / "
                        "line_ledger / since_applied / compare_runs / worth_rerunning: "
                        "the CVDoc returned by "
                        "parse_cv. export_docx: "
                        "optional, re-checks hand-edited lines against it."
                    ),
                    "required": False,
                },
                {
                    "name": "document",
                    "type": "string",
                    "description": (
                        "check_document: a CV or cover letter the user is about "
                        "to send, as text. Read once and never stored."
                    ),
                    "required": False,
                },
                {
                    "name": "assertions",
                    "type": "array",
                    "description": (
                        "interview_brief: requirements the user told the app it "
                        "got wrong, as {requirement_id, line_ids}. Recorded "
                        "beside the match's own verdict, never merged into it."
                    ),
                    "required": False,
                },
                {
                    "name": "questions",
                    "type": "array",
                    "description": (
                        "answer_question: the free-text questions an employer "
                        "asked, in the order the form asks them. At most five; "
                        "they are never used as a source, only as the question."
                    ),
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
                    "description": (
                        "answer_question: optional — its requirements lend general "
                        "concepts the way they do for a letter, and nothing else. "
                        "tailor / letter / gaps / interview_brief / since_applied: "
                        "the MatchResult "
                        "run_match returned. check_document: optional — its company "
                        "and role are the envelope, so they are not read as claims."
                    ),
                    "required": False,
                },
                {
                    "name": "items",
                    "type": "array",
                    "description": (
                        "recurring_gaps / compare_postings / line_ledger / "
                        "worth_rerunning: past "
                        "requirements as {id, match, text, kind, status}, plus "
                        "{line_ids, cv_hash} which only line_ledger reads and "
                        "{created_at} which only worth_rerunning reads. `match` "
                        "is an opaque grouping key — it is only counted, never "
                        "read. compare_postings reads at most four distinct "
                        "`match` values and compares them against each other."
                    ),
                    "required": False,
                },
                {
                    "name": "before",
                    "type": "object",
                    "description": (
                        "compare_runs: the older MatchResult for this posting. "
                        "`match` is the newer one."
                    ),
                    "required": False,
                },
                {
                    "name": "sent_at",
                    "type": "string",
                    "description": (
                        "since_applied / followup: ISO timestamp of the day the "
                        "user marked this application sent. Absent on records "
                        "written before the tracker stamped its statuses — the "
                        "match's own date is used instead, and the payload says "
                        "which."
                    ),
                    "required": False,
                },
                {
                    "name": "max_gaps",
                    "type": "integer",
                    "description": "gaps: how many unproven requirements to ask about (default 6, max 10).",
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
                    "description": "letter / export_docx / check_document: company name, when known.",
                    "required": False,
                },
                {
                    "name": "role",
                    "type": "string",
                    "description": "letter / export_docx / check_document: role title, when known.",
                    "required": False,
                },
                {
                    "name": "tailor_result",
                    "type": "object",
                    "description": (
                        "export_docx: the TailorResult to render. interview_brief: "
                        "optional, the bullets the user accepted and sent."
                    ),
                    "required": False,
                },
                {
                    "name": "letter_result",
                    "type": "object",
                    "description": (
                        "export_docx: the LetterResult to render. interview_brief: "
                        "optional, the letter that was sent."
                    ),
                    "required": False,
                },
                {
                    "name": "mode",
                    "type": "string",
                    "description": (
                        "export_cv: the whole CV, or only the lines the user "
                        "added answering a gap, an audit finding or a "
                        "recurring gap."
                    ),
                    "required": False,
                    "enum": ["full", "additions"],
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
        "in_flight": _limits.in_flight,
    }


def _action_discard_upload(args: dict[str, Any]) -> dict[str, Any]:
    """Drop one buffered upload — the id is the only thing that names it.

    The failure path used to call ``forget``, which empties every buffer and
    the requirement cache to clean up after a single half-sent file. Knowing
    the id is what entitles a caller to the bytes, so it is also what entitles
    them to delete them.
    """
    upload_id = _as_str(args.get("upload_id"))
    if not upload_id:
        raise EngineError("invalid_args", "discard_upload needs upload_id")
    return {"dropped": _uploads.discard(upload_id)}


def _action_forget(_args: dict[str, Any]) -> dict[str, Any]:
    """Drop everything the process is still holding for this user.

    "Delete all my data" removes the CV and the matches from storage, but an
    abandoned upload lives in this process for another ten minutes and the
    requirement cache keeps a posting's wording for a month. Neither survives
    a restart, and neither is written to disk — but "deleted" has to mean
    deleted now, not deleted eventually.
    """
    uploads = len(_uploads)
    cached = clear_requirement_cache()
    _uploads.clear()
    log(f"forget: dropped {uploads} pending upload(s) and {cached} cached posting(s)")
    return {"uploads_dropped": uploads, "cached_postings_dropped": cached}


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


async def _action_gaps(args: dict[str, Any]) -> dict[str, Any]:
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    match = _as_model(args.get("match"), MatchResult, "match")
    _assert_same_cv(cv, match)
    result = await plan_gaps(
        _client(),
        cv=cv,
        match=match,
        max_gaps=_as_optional_int(args.get("max_gaps")),
        locale=_locale(args),
    )
    return result.model_dump()


async def _action_answer_question(args: dict[str, Any]) -> dict[str, Any]:
    """Answer the form's questions from the CV alone.

    Deliberately without `_assert_same_cv`: the questions arrive from a form or
    an email and have no CV hash of their own, and the match — when one is
    passed at all — is context rather than the subject, exactly as in
    `check_document`. Answering is done against the CV on screen, which is the
    one the citations will point at.
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    match = _as_model(args.get("match"), MatchResult, "match") if args.get("match") else None
    raw = args.get("questions")
    if not isinstance(raw, list):
        raise EngineError("invalid_args", "answer_question needs a questions list")
    result = await answer_questions(
        _client(),
        cv=cv,
        questions=[str(entry) for entry in raw if isinstance(entry, str)],
        match=match,
        locale=_locale(args),
    )
    return result.model_dump()


async def _action_followup(args: dict[str, Any]) -> dict[str, Any]:
    """The follow-up note, or the refusal — one model call, or none at all.

    `_assert_same_cv` is deliberately absent: the whole point is that the CV
    has moved since this application went out, and the lines it gained after
    that day are the only material the note is allowed to use.
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    match = _as_model(args.get("match"), MatchResult, "match")
    result = await write_followup(
        _client(),
        cv=cv,
        match=match,
        sent_at=_as_str(args.get("sent_at")),
        locale=_locale(args),
    )
    return result.model_dump()


async def _action_profile(args: dict[str, Any]) -> dict[str, Any]:
    """A headline and an About section, from the CV alone.

    The only generated action with no `match`: there is no posting, which
    also means there is no posting vocabulary to lend a concept. Everything
    in the output has to come from the CV.
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    result = await write_profile(_client(), cv=cv, locale=_locale(args))
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


def _action_audit_cv(args: dict[str, Any]) -> dict[str, Any]:
    """No model, no tokens: set arithmetic over the CV the user already has."""
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    return audit_cv(cv).model_dump()


def _action_check_document(args: dict[str, Any]) -> dict[str, Any]:
    """The verifier turned on a document the app did not write. No model.

    Deliberately without `_assert_same_cv`: the document being checked has no
    CV hash and no reason to match one. The match, when it comes at all, is
    only here so the employer the letter is addressed to is not read as a
    claim about the candidate.
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    match = _as_model(args.get("match"), MatchResult, "match") if args.get("match") else None
    result = check_document(
        cv,
        _as_str(args.get("document")) or "",
        match=match,
        company=_as_str(args.get("company")),
        role=_as_str(args.get("role")),
    )
    return result.model_dump()


def _action_recurring_gaps(args: dict[str, Any]) -> dict[str, Any]:
    """Across applications, not within one. No model, no tokens."""
    raw = args.get("items")
    if not isinstance(raw, list):
        raise EngineError("invalid_args", "recurring_gaps needs an items list")
    items = [_as_model(entry, RecurringInput, "items[]") for entry in raw[:MAX_ITEMS]]
    return recurring_gaps(items).model_dump()


def _action_compare_postings(args: dict[str, Any]) -> dict[str, Any]:
    """Between applications, before one of them is worth an hour. No model.

    Takes the same replay feed `recurring_gaps` does — every requirement with
    the verdict it got — because it is the same evidence asked a different
    question, and a second input shape would be a second thing to keep true.
    """
    raw = args.get("items")
    if not isinstance(raw, list):
        raise EngineError("invalid_args", "compare_postings needs an items list")
    items = [_as_model(entry, RecurringInput, "items[]") for entry in raw[:MAX_COMPARE_ITEMS]]
    return compare_postings(items).model_dump()


def _action_interview_brief(args: dict[str, Any]) -> dict[str, Any]:
    """What this application will be asked to back up. No model, no tokens.

    Deliberately without `_assert_same_cv`: answering a gap question moves the
    CV hash, so requiring the match's own CV would refuse the brief to exactly
    the people who prepared hardest. The mismatch is reported in the payload
    instead — the interviewer is holding the older document, which is worth
    saying rather than worth refusing over.
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    match = _as_model(args.get("match"), MatchResult, "match")
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
    raw = args.get("assertions")
    assertions = (
        [_as_model(entry, Assertion, "assertions[]") for entry in raw]
        if isinstance(raw, list)
        else None
    )
    return interview_brief(
        cv, match, tailor=tailor, letter=letter, assertions=assertions
    ).model_dump()


def _action_line_ledger(args: dict[str, Any]) -> dict[str, Any]:
    """Which CV lines have carried an application, and which never have.

    No model, no tokens: every number is a citation a match already made. The
    CV comes too, because the answer is about lines the postings never asked
    about — and only the document knows those exist.

    Like `interview_brief`, and unlike `tailor`, it does not refuse a CV whose
    hash has moved: answering a gap question moves it, and the whole point of
    the screen is to report what those answers have proved since. Applications
    checked against a *different parse* of the CV are the ones dropped, and
    counted in `skipped` (`ledger.base_hash`).
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    raw = args.get("items")
    if not isinstance(raw, list):
        raise EngineError("invalid_args", "line_ledger needs an items list")
    items = [_as_model(entry, RecurringInput, "items[]") for entry in raw[:MAX_LEDGER_ITEMS]]
    return line_ledger(cv, items).model_dump()


def _action_since_applied(args: dict[str, Any]) -> dict[str, Any]:
    """What the CV has gained since this application went out. No model.

    Like `interview_brief` and `line_ledger`, and unlike `tailor`, it does not
    refuse a CV whose hash has moved: that movement *is* the question here. It
    comes back as `cv_changed`.
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    match = _as_model(args.get("match"), MatchResult, "match")
    return since_applied(cv, match, sent_at=_as_str(args.get("sent_at"))).model_dump()


def _action_compare_runs(args: dict[str, Any]) -> dict[str, Any]:
    """What the second run of a posting changed. No model, no tokens.

    Four screens ask the user to write a sentence into their CV and the last
    of them tells them to run the posting again; this is the only place the
    app ever reports back on whether that worked. Both runs are records it
    already holds, so the answer is a comparison rather than an analysis.

    No `_assert_same_cv`: the CV is *expected* to have moved between the two
    runs — that movement is what the screen is about — and the lines written
    in between are what `credited` is read from.
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    before = _as_model(args.get("before"), MatchResult, "before")
    after = _as_model(args.get("match"), MatchResult, "match")
    return compare_runs(cv, before, after).model_dump()


def _action_worth_rerunning(args: dict[str, Any]) -> dict[str, Any]:
    """Which saved applications the CV has since gained an answer for.

    `since_applied` asks this of one application; someone who applies thirty
    times a month will not open thirty of them to find out. No model, no
    tokens: the same replay feed the other cross-application screens read,
    with the date each application was run.

    No CV-hash filtering, unlike `line_ledger`: nothing here is read off a
    citation, so a re-parsed CV does not invalidate the comparison — only the
    dates matter, and those are the application's own.
    """
    cv = _as_model(args.get("cv"), CVDoc, "cv")
    raw = args.get("items")
    if not isinstance(raw, list):
        raise EngineError("invalid_args", "worth_rerunning needs an items list")
    items = [_as_model(entry, RecurringInput, "items[]") for entry in raw[:MAX_WORTH_ITEMS]]
    return worth_rerunning(cv, items).model_dump()


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

    # The CV is optional: without it the document still renders, it just cannot
    # re-check a line the user edited before accepting.
    cv = _as_model(args.get("cv"), CVDoc, "cv") if args.get("cv") else None

    filename, content_b64, unverified = build_docx(
        tailor=tailor,
        letter=letter,
        company=_as_str(args.get("company")),
        role=_as_str(args.get("role")),
        locale=_locale(args),
        cv=cv,
    )
    return {
        "filename": filename,
        "content_b64": content_b64,
        "mime": MIME,
        "unverified": unverified,
    }


def _action_export_cv(args: dict[str, Any]) -> dict[str, Any]:
    """The CV back out, with the lines the user added inside it.

    Every answer loop in this app writes into the stored CV — a gap question,
    an audit finding, a recurring gap — and until this action existed none of
    those sentences could reach the document an employer actually reads. The
    interview brief says so out loud (`self_added`); this is what makes that
    warning fixable rather than just true.

    No verifier and no model: the document is the CV, so it cannot contain a
    claim the CV does not.
    """
    from .export import MIME, build_cv_docx

    cv = _as_model(args.get("cv"), CVDoc, "cv")
    mode = str(args.get("mode") or "full")
    if mode not in {"full", "additions"}:
        raise EngineError("invalid_args", "mode must be 'full' or 'additions'")

    filename, content_b64, lines = build_cv_docx(cv=cv, mode=mode, locale=_locale(args))
    return {"filename": filename, "content_b64": content_b64, "mime": MIME, "lines": lines}


_SYNC_ACTIONS: Final[dict[str, Any]] = {
    "health": _action_health,
    "forget": _action_forget,
    "discard_upload": _action_discard_upload,
    "upload_chunk": _action_upload_chunk,
    "parse_cv": _action_parse_cv,
    "audit_cv": _action_audit_cv,
    "check_document": _action_check_document,
    "recurring_gaps": _action_recurring_gaps,
    "compare_postings": _action_compare_postings,
    "interview_brief": _action_interview_brief,
    "line_ledger": _action_line_ledger,
    "since_applied": _action_since_applied,
    "compare_runs": _action_compare_runs,
    "worth_rerunning": _action_worth_rerunning,
    "export_docx": _action_export_docx,
    "export_cv": _action_export_cv,
}
_ASYNC_ACTIONS: Final[dict[str, Any]] = {
    "run_match": _action_run_match,
    "gaps": _action_gaps,
    "tailor": _action_tailor,
    "letter": _action_letter,
    "followup": _action_followup,
    "profile": _action_profile,
    "answer_question": _action_answer_question,
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
            # Before the work, not inside it: a throttled run should cost the
            # user nothing, least of all a sampling call.
            _limits.check(action)
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
            # The type, not the message. An unexpected pydantic error quotes
            # the input that failed, and the input here is CV-derived — rule 5
            # says that never reaches a log, and stderr on the user's machine
            # is still a log. `RECEIPTS_DEBUG=1` opts back in, locally.
            log(f"action {action} crashed: {type(exc).__name__}{_detail(exc)}")
            return response(req_id, _failure(EngineError("internal_error", type(exc).__name__)))

    return response(req_id, {"success": True, "tool": TOOL_NAME, "data": data})


def _detail(exc: Exception) -> str:
    """The exception message, only when a developer asked for it by hand."""
    return f": {exc}" if os.environ.get("RECEIPTS_DEBUG") else ""


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
            "protocolVersion": protocol if protocol in {PROTOCOL_V1, PROTOCOL_V2} else PROTOCOL_V2,
            "serverInfo": {"name": MANIFEST["display_name"], "version": __version__},
            "client_capabilities": {"sampling": {}} if protocol == PROTOCOL_V2 else {},
            "capabilities": {},
        },
    )


def _read_message(line: str) -> dict[str, Any] | None:
    """Parse one stdin line, answering the host directly if it is unparsable."""
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        write_frame(error(None, -32700, f"parse error: {exc}"))
        return None
    return message if isinstance(message, dict) else None


def _is_response(message: dict[str, Any]) -> bool:
    """A frame without ``method`` is the host answering one of our reverse RPCs."""
    return "method" not in message


def _dispatch_response(message: dict[str, Any]) -> None:
    if not _sampling.dispatch_response(message):
        log(f"unmatched response id={message.get('id')!r}")


def _handle_message(message: dict[str, Any]) -> None:
    if _is_response(message):
        _dispatch_response(message)
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


def _handle_bounded(message: dict[str, Any]) -> None:
    """Run one invoke and release its in-flight slot, whatever happens."""
    try:
        _handle_message(message)
    finally:
        _limits.leave()


def _refuse_saturated(message: dict[str, Any]) -> None:
    req_id = message.get("id")
    if req_id is None:
        return  # a notification has nowhere to hear the refusal
    log("refusing invoke: too many in flight")
    write_frame(
        response(
            req_id,
            _failure(EngineError("rate_limited", "too many invokes in flight")),
        )
    )


def main() -> None:
    log(f"{MANIFEST['display_name']} v{__version__} ready ({MANIFEST['name']})")
    # Invokes block on sampling replies that arrive on this very pipe, so they
    # must not run on the reader thread. The replies themselves must not run on
    # the pool either: with every worker parked on a sampling future, a queued
    # reply would wait behind the very calls it is there to release, and the
    # whole process would sit idle until each one timed out.
    pool = ThreadPoolExecutor(max_workers=_INVOKE_WORKERS, thread_name_prefix="invoke")
    try:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            message = _read_message(line)
            if message is None:
                continue
            if _is_response(message):
                _dispatch_response(message)
            elif message.get("method") == "invoke":
                # The pool's queue is unbounded, so without this a client that
                # never waits for a reply turns backlog into memory until the
                # process dies — and a dead plugin fails every other window the
                # Agent has open, not just the one that caused it.
                if not _limits.enter():
                    _refuse_saturated(message)
                    continue
                pool.submit(_handle_bounded, message)
            else:
                pool.submit(_handle_message, message)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        _loop.call_soon_threadsafe(_loop.stop)


if __name__ == "__main__":
    main()
