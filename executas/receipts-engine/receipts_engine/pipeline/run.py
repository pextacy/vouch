"""``run_match`` — the primary function, and the only Qualified App Run.

Six stages, each emitting progress so the highlighter sweep in the UI is driven
by real work rather than a timer:

``normalize`` → ``extract`` → ``match`` → ``guard`` → ``summarize`` → ``done``

The success condition is narrow on purpose: at least one requirement extracted
**and** a status assigned to every one of them. Anything short of that raises,
because a run that returns an empty result while reporting success would both
mislead the user and pollute the MAU count the program is measured on.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from ..errors import EngineError
from ..host.frames import log
from ..host.progress import emit_progress
from ..llm import LlmClient
from ..parse.posting import normalize_posting
from ..schemas import CVDoc, Language, MatchResult, PostingMeta, Requirement
from .extract import extract_requirements
from .match import guard_citations, match_requirements
from .summarize import summarize

#: Requirement lists are stable for a given posting, so a re-run of the same
#: text skips the extraction call entirely. Keyed by (posting hash, locale).
_REQUIREMENT_CACHE: dict[tuple[str, str], tuple[float, list[Requirement], str | None, str | None]] = {}
_CACHE_TTL_S = 30 * 24 * 3600
_CACHE_MAX_ENTRIES = 64


async def run_match(
    llm: LlmClient,
    *,
    cv: CVDoc,
    posting_text: str,
    posting_url: str | None = None,
    locale: str = "en",
) -> MatchResult:
    started = time.monotonic()

    emit_progress("normalize", 5)
    posting = normalize_posting(posting_text)
    output_locale = locale if locale in {"en", "tr"} else "en"

    emit_progress("extract", 15)
    cached = _cache_get(posting.hash, output_locale)
    if cached is not None:
        requirements, title, company = cached
        log("requirement cache hit")
    else:
        requirements, title, company = await extract_requirements(llm, posting, output_locale)
        # Only a real extraction is worth remembering. Caching the empty one
        # would pin `no_requirements_found` on this posting for a month, and
        # the "Run it again" the error tells the user to try would never reach
        # the model — the retry would be answered by the cached failure.
        if requirements:
            _cache_put(posting.hash, output_locale, requirements, title, company)

    if not requirements:
        raise EngineError("no_requirements_found")

    emit_progress(
        "extract",
        30,
        {"requirements": [_requirement_preview(req) for req in requirements]},
    )

    emit_progress("match", 40)
    evidence = await match_requirements(llm, cv, requirements, output_locale)
    emit_progress(
        "match",
        70,
        {"matched": [{"id": e.requirement_id, "status": e.status, "line_ids": e.line_ids} for e in evidence]},
    )

    emit_progress("guard", 85)
    evidence, guard = guard_citations(cv, requirements, evidence)
    if guard.total:
        # Counts only, never content. A prompt regression that starts inventing
        # ids, or a model that starts matching on resemblance, shows up here as
        # a number in the eval run rather than as a quiet wrong verdict.
        log(
            f"guard: {guard.invented} invented citation(s), "
            f"{guard.repaired} repaired, {guard.unproven} cut back to partial"
        )

    if len(evidence) != len(requirements):
        raise EngineError("model_output_invalid", "evidence count does not match requirements")

    emit_progress("summarize", 95)
    summary = summarize(requirements, evidence, output_locale)

    result = MatchResult(
        id=uuid.uuid4().hex,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        posting=PostingMeta(
            title=title,
            company=company,
            url=posting_url,
            hash=posting.hash,
            language=_as_language(posting.language),
        ),
        requirements=requirements,
        evidence=evidence,
        summary=summary,
        cv_hash=cv.hash,
    )

    emit_progress("done", 100, {"summary": summary.model_dump()})
    log(f"run_match finished in {time.monotonic() - started:.1f}s ({summary.total} requirements)")
    return result


def _requirement_preview(req: Requirement) -> dict[str, str]:
    """Small enough to keep the whole list inside the host's 8 KB event cap."""
    return {"id": req.id, "text": req.text[:80], "kind": req.kind}


def _as_language(value: str) -> Language:
    return "tr" if value == "tr" else "en" if value == "en" else "other"


# ─── Requirement cache ────────────────────────────────────────────────


def _cache_get(
    posting_hash: str, locale: str
) -> tuple[list[Requirement], str | None, str | None] | None:
    entry = _REQUIREMENT_CACHE.get((posting_hash, locale))
    if entry is None:
        return None
    stored_at, requirements, title, company = entry
    if time.time() - stored_at > _CACHE_TTL_S:
        _REQUIREMENT_CACHE.pop((posting_hash, locale), None)
        return None
    # Copies, not the cached instances: two runs of the same posting must not
    # end up holding the same mutable objects inside two different results.
    return [requirement.model_copy(deep=True) for requirement in requirements], title, company


def _cache_put(
    posting_hash: str,
    locale: str,
    requirements: list[Requirement],
    title: str | None,
    company: str | None,
) -> None:
    if len(_REQUIREMENT_CACHE) >= _CACHE_MAX_ENTRIES:
        oldest = min(_REQUIREMENT_CACHE, key=lambda key: _REQUIREMENT_CACHE[key][0])
        _REQUIREMENT_CACHE.pop(oldest, None)
    _REQUIREMENT_CACHE[(posting_hash, locale)] = (time.time(), requirements, title, company)


def clear_requirement_cache() -> int:
    """Empty the process-wide cache. Returns how many postings it held."""
    held = len(_REQUIREMENT_CACHE)
    _REQUIREMENT_CACHE.clear()
    return held
