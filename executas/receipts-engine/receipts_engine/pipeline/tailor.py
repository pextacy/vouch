"""Tailored bullets — generate, verify, repair once, then drop.

This is where "Invent nothing" stops being a slogan. Every suggestion is
checked against the exact CV lines it was built from. A suggestion with an
unsupported claim gets one repair attempt with the offending tokens named; if
it still fails it is dropped and the user is told why, in plain words, rather
than shown a softened version of a fabrication.
"""

from __future__ import annotations

from ..host.frames import log
from ..llm import LlmClient
from ..schemas import (
    CVDoc,
    LlmBullet,
    MatchResult,
    Requirement,
    TailoredBullet,
    TailorOutput,
    TailorResult,
)
from ..verify import DEFAULT_LEXICON, verify
from .prompts import language_name, render

#: Enough to cover a posting's must-haves without spending a second call.
DEFAULT_MAX_BULLETS = 8
HARD_MAX_BULLETS = 12

#: Rewriting a one-word skills entry is noise; there is nothing to tighten.
_MIN_SOURCE_CHARS = 25


async def tailor_bullets(
    llm: LlmClient,
    *,
    cv: CVDoc,
    match: MatchResult,
    max_bullets: int | None = None,
    locale: str = "en",
) -> TailorResult:
    limit = min(max_bullets or DEFAULT_MAX_BULLETS, HARD_MAX_BULLETS)
    targets = _candidate_lines(cv, match, limit)
    if not targets:
        return TailorResult(match_id=match.id, bullets=[])

    line_text = cv.text_by_id()
    requirements = {req.id: req for req in match.requirements}
    posting_vocab = [req.text for req in match.requirements]

    output = await _generate(llm, cv, match, targets, locale)
    bullets: list[TailoredBullet] = []
    repairs: list[tuple[LlmBullet, list[str]]] = []

    for item in output.bullets:
        source_ids = [lid for lid in item.source_line_ids if lid in line_text]
        if not source_ids:
            continue
        sources = [line_text[lid] for lid in source_ids]
        verdict = verify(
            item.suggestion, sources, lexicon=DEFAULT_LEXICON, posting_vocab=posting_vocab
        )
        if verdict.ok:
            bullets.append(_accepted(item, source_ids, sources, requirements))
        else:
            repairs.append((item, verdict.tokens))

    if repairs:
        bullets.extend(
            await _repair(llm, cv, repairs, line_text, requirements, posting_vocab, locale)
        )

    ordered = {bullet.source_line_ids[0]: bullet for bullet in bullets if bullet.source_line_ids}
    return TailorResult(
        match_id=match.id,
        bullets=[ordered[lid] for lid in targets if lid in ordered],
    )


async def _generate(
    llm: LlmClient,
    cv: CVDoc,
    match: MatchResult,
    targets: list[str],
    locale: str,
) -> TailorOutput:
    system = render("tailor.v1.md", output_language=language_name(locale))
    wanted = {req.id: req for req in match.requirements}
    relevant = [
        e for e in match.evidence if e.status in {"strong", "partial"} and e.line_ids
    ]
    requirement_block = "\n".join(
        f"{e.requirement_id} [{wanted[e.requirement_id].kind}] {wanted[e.requirement_id].text}"
        f"  ← evidence in {', '.join(e.line_ids)}"
        for e in relevant
        if e.requirement_id in wanted
    )
    user = (
        "REQUIREMENTS THIS CV ALREADY HAS EVIDENCE FOR\n"
        "---------------------------------------------\n"
        f"{requirement_block}\n\n"
        "SOURCE LINES TO REWRITE (use only these facts)\n"
        "----------------------------------------------\n"
        f"{cv.numbered(targets)}"
    )
    return await llm.structured(
        name="receipts_tailored_bullets",
        model=TailorOutput,
        system_prompt=system,
        user_prompt=user,
        max_tokens=2048,
    )


async def _repair(
    llm: LlmClient,
    cv: CVDoc,
    repairs: list[tuple[LlmBullet, list[str]]],
    line_text: dict[str, str],
    requirements: dict[str, Requirement],
    posting_vocab: list[str],
    locale: str,
) -> list[TailoredBullet]:
    """One repair call for every failed suggestion at once, then re-verify."""
    tokens = sorted({token for _, failed in repairs for token in failed})
    log(f"tailor: repairing {len(repairs)} suggestion(s) with unsupported claims")

    system = render("tailor.v1.md", output_language=language_name(locale))
    instruction = render("tailor_repair.v1.md", tokens=", ".join(tokens))
    target_ids = [lid for item, _ in repairs for lid in item.source_line_ids if lid in line_text]
    user = (
        f"{instruction}\n\n"
        "SOURCE LINES (use only these facts)\n"
        "-----------------------------------\n"
        f"{cv.numbered(target_ids)}"
    )

    try:
        output = await llm.structured(
            name="receipts_tailored_bullets",
            model=TailorOutput,
            system_prompt=system,
            user_prompt=user,
            max_tokens=1536,
        )
        repaired = {tuple(item.source_line_ids): item for item in output.bullets}
    except Exception as exc:  # noqa: BLE001 — a failed repair is a dropped bullet
        log(f"tailor: repair call failed ({type(exc).__name__}) — dropping suggestions")
        repaired = {}

    results: list[TailoredBullet] = []
    for item, failed_tokens in repairs:
        source_ids = [lid for lid in item.source_line_ids if lid in line_text]
        sources = [line_text[lid] for lid in source_ids]
        candidate = repaired.get(tuple(item.source_line_ids))
        if candidate is not None:
            verdict = verify(
                candidate.suggestion,
                sources,
                lexicon=DEFAULT_LEXICON,
                posting_vocab=posting_vocab,
            )
            if verdict.ok:
                results.append(_accepted(candidate, source_ids, sources, requirements))
                continue
            failed_tokens = verdict.tokens

        results.append(
            TailoredBullet(
                source_line_ids=source_ids,
                original=" ".join(sources),
                suggestion=None,
                targets=[tid for tid in item.targets if tid in requirements],
                dropped_reason="unsupported_claims",
                unsupported_tokens=failed_tokens,
            )
        )
    return results


def _accepted(
    item: LlmBullet,
    source_ids: list[str],
    sources: list[str],
    requirements: dict[str, Requirement],
) -> TailoredBullet:
    return TailoredBullet(
        source_line_ids=source_ids,
        original=" ".join(sources),
        suggestion=item.suggestion.strip()[:220],
        targets=[tid for tid in item.targets if tid in requirements],
    )


def _candidate_lines(cv: CVDoc, match: MatchResult, limit: int) -> list[str]:
    """CV lines worth rewriting: cited as evidence, long enough to tighten.

    Must-have evidence comes first — a bullet that speaks to a must-have is
    worth more to the user than a polished nice-to-have.
    """
    kind_of = {req.id: req.kind for req in match.requirements}
    line_text = cv.text_by_id()
    scored: dict[str, tuple[int, int]] = {}

    for evidence in match.evidence:
        if evidence.status not in {"strong", "partial"}:
            continue
        must = kind_of.get(evidence.requirement_id) == "must"
        strong = evidence.status == "strong"
        for position, line_id in enumerate(evidence.line_ids):
            text = line_text.get(line_id)
            if text is None or len(text) < _MIN_SOURCE_CHARS:
                continue
            score = (2 if must else 0) + (1 if strong else 0)
            previous = scored.get(line_id)
            rank = position
            if previous is None or score > previous[0]:
                scored[line_id] = (score, rank)

    ranked = sorted(scored.items(), key=lambda entry: (-entry[1][0], entry[1][1], entry[0]))
    return [line_id for line_id, _ in ranked[:limit]]
