"""Cover letter — same verifier, paragraph by paragraph.

A letter is riskier than a bullet: it is longer, more fluent, and the fluent
parts are exactly where a model reaches for a number it was never given. Each
paragraph is verified against the CV lines it cites; a paragraph that fails is
repaired once and then dropped, and a letter with no surviving evidence
paragraph is not a letter — it raises rather than shipping three sentences of
enthusiasm.
"""

from __future__ import annotations

import re
from typing import Final

from ..errors import EngineError
from ..host.frames import log
from ..llm import LlmClient
from ..schemas import CVDoc, LetterOutput, LetterParagraph, LetterResult, MatchResult, Tone
from ..verify import DEFAULT_LEXICON, verify
from .prompts import language_name, render

LENGTH_WORDS: Final[dict[str, int]] = {"short": 150, "standard": 250}

#: Placeholders the prompt is told to use when a fact is genuinely unknown.
#: They are the honest alternative to a guessed company name, so the UI warns
#: about them instead of the verifier rejecting them.
_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"\[[A-Za-zÇĞİÖŞÜçğıöşü ]{2,30}\]")


async def write_letter(
    llm: LlmClient,
    *,
    cv: CVDoc,
    match: MatchResult,
    tone: str = "plain",
    length: str = "standard",
    company: str | None = None,
    role: str | None = None,
    locale: str = "en",
) -> LetterResult:
    evidence_lines = _evidence_lines(match)
    if not evidence_lines:
        raise EngineError(
            "no_requirements_found",
            "no evidenced requirement to build a letter from",
        )

    line_text = cv.text_by_id()
    posting_vocab = [req.text for req in match.requirements]
    all_sources = list(line_text.values())

    output = await _generate(
        llm,
        cv=cv,
        match=match,
        evidence_lines=evidence_lines,
        tone=tone,
        length=length,
        company=company,
        role=role,
        locale=locale,
    )

    paragraphs: list[LetterParagraph] = []
    failures: list[tuple[int, list[str]]] = []
    for index, item in enumerate(output.paragraphs):
        text = item.text.strip()
        if not text:
            continue
        cited = [lid for lid in item.line_ids if lid in line_text]
        sources = [line_text[lid] for lid in cited] if cited else all_sources
        verdict = verify(text, sources, lexicon=DEFAULT_LEXICON, posting_vocab=posting_vocab)
        if verdict.ok:
            paragraphs.append(LetterParagraph(text=text, line_ids=cited))
        else:
            failures.append((index, verdict.tokens))
            paragraphs.append(LetterParagraph(text="", line_ids=cited))

    if failures:
        paragraphs = await _repair(
            llm,
            cv=cv,
            match=match,
            paragraphs=paragraphs,
            failures=failures,
            line_text=line_text,
            all_sources=all_sources,
            posting_vocab=posting_vocab,
            tone=tone,
            length=length,
            company=company,
            role=role,
            locale=locale,
        )

    kept = [para for para in paragraphs if para.text.strip()]
    if not any(para.line_ids for para in kept):
        raise EngineError(
            "model_output_invalid",
            "no paragraph survived verification with evidence attached",
        )

    return LetterResult(
        match_id=match.id,
        tone=_as_tone(tone),
        paragraphs=kept,
        placeholders=sorted(
            {hit.group(0) for para in kept for hit in _PLACEHOLDER_RE.finditer(para.text)}
        ),
    )


async def _generate(
    llm: LlmClient,
    *,
    cv: CVDoc,
    match: MatchResult,
    evidence_lines: list[str],
    tone: str,
    length: str,
    company: str | None,
    role: str | None,
    locale: str,
    extra_instruction: str = "",
) -> LetterOutput:
    system = render(
        "letter.v1.md",
        tone=tone,
        length_words=str(LENGTH_WORDS.get(length, 250)),
        output_language=language_name(locale),
    )
    must_haves = "\n".join(
        f"- {req.text}"
        for req in match.requirements
        if req.kind == "must"
        and any(
            e.requirement_id == req.id and e.status in {"strong", "partial"}
            for e in match.evidence
        )
    )
    header = (
        f"ROLE: {role or match.posting.title or '[Role]'}\n"
        f"COMPANY: {company or match.posting.company or '[Company]'}\n"
    )
    user = (
        f"{header}\n"
        "MUST-HAVE REQUIREMENTS WITH EVIDENCE\n"
        "------------------------------------\n"
        f"{must_haves or '(none)'}\n\n"
        "CV LINES YOU MAY USE\n"
        "--------------------\n"
        f"{cv.numbered(evidence_lines)}"
    )
    if extra_instruction:
        user = f"{extra_instruction}\n\n{user}"

    return await llm.structured(
        name="receipts_cover_letter",
        model=LetterOutput,
        system_prompt=system,
        user_prompt=user,
        max_tokens=1536,
    )


async def _repair(
    llm: LlmClient,
    *,
    cv: CVDoc,
    match: MatchResult,
    paragraphs: list[LetterParagraph],
    failures: list[tuple[int, list[str]]],
    line_text: dict[str, str],
    all_sources: list[str],
    posting_vocab: list[str],
    tone: str,
    length: str,
    company: str | None,
    role: str | None,
    locale: str,
) -> list[LetterParagraph]:
    tokens = sorted({token for _, failed in failures for token in failed})
    log(f"letter: repairing {len(failures)} paragraph(s) with unsupported claims")
    instruction = (
        "Your previous draft used facts the CV lines do not support: "
        f"{', '.join(tokens)}. Rewrite the whole letter without them, using only "
        "what the lines below actually say."
    )
    try:
        output = await _generate(
            llm,
            cv=cv,
            match=match,
            evidence_lines=_evidence_lines(match),
            tone=tone,
            length=length,
            company=company,
            role=role,
            locale=locale,
            extra_instruction=instruction,
        )
    except Exception as exc:  # noqa: BLE001 — keep whatever already verified
        log(f"letter: repair call failed ({type(exc).__name__}) — keeping verified paragraphs")
        return paragraphs

    rebuilt: list[LetterParagraph] = []
    for item in output.paragraphs:
        text = item.text.strip()
        if not text:
            continue
        cited = [lid for lid in item.line_ids if lid in line_text]
        sources = [line_text[lid] for lid in cited] if cited else all_sources
        verdict = verify(text, sources, lexicon=DEFAULT_LEXICON, posting_vocab=posting_vocab)
        if verdict.ok:
            rebuilt.append(LetterParagraph(text=text, line_ids=cited))

    # Only accept the repair if it actually produced a letter; otherwise keep
    # the paragraphs that passed the first time.
    if any(para.line_ids for para in rebuilt):
        return rebuilt
    return paragraphs


def _as_tone(value: str) -> Tone:
    return value if value in {"plain", "warm", "formal"} else "plain"  # type: ignore[return-value]


def _evidence_lines(match: MatchResult) -> list[str]:
    """CV lines cited as evidence, must-haves first, de-duplicated."""
    kind_of = {req.id: req.kind for req in match.requirements}
    ordered: list[str] = []
    for want_must in (True, False):
        for item in match.evidence:
            if item.status not in {"strong", "partial"}:
                continue
            if (kind_of.get(item.requirement_id) == "must") != want_must:
                continue
            for line_id in item.line_ids:
                if line_id not in ordered:
                    ordered.append(line_id)
    return ordered[:24]
