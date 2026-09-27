"""The note you send after the silence — and the one the app refuses to write.

An application goes out and nothing happens. Every other tool in this category
will write the follow-up anyway: a warm paragraph that says the candidate
remains very interested and adds nothing a recruiter did not already have.
That email is not a neutral act. It spends the one piece of attention a
candidate gets, on nothing.

This app already knows whether there is anything to say. `since.py` reports
what the CV has gained **after** an application went out; if that is empty,
there is no note here worth a stranger's minute, and the honest output is the
refusal — with the thing that would change it named on screen. It is the same
move `answer.py` makes when a form asks what the candidate *wants*: the
feature exists for the case where the rest of the category writes anyway.

When there **is** something new, the note is built the way every other
sentence in this product is built: from cited CV lines, through the verifier,
dropped rather than softened when it fails. The new lines are the only
material the model gets — a follow-up that re-lists the original application's
strengths is the same empty email with more words in it.

Three things this pipeline will not do:

* **No model call when there is nothing to say.** The refusal is decided
  before the call, from records that already exist, so declining costs the
  user nothing.
* **No dates.** The model is never told how long it has been and is forbidden
  from writing it; the screen says that, from the tracker's own record.
* **One repair attempt, then drop.** The same budget `tailor` and `letter`
  are given, and for the reason the adversarial eval made plain: without it,
  a single invented sentence in the one paragraph that matters turns the
  whole note into an error the user has to retry by hand — for the money the
  repair would have cost. What still cannot be grounded after the second
  attempt is dropped, and a note with no evidence left is an error, because
  a follow-up whose middle paragraph is gone is the empty email again.
"""

from __future__ import annotations

from typing import Final

from ..errors import EngineError
from ..host.frames import log
from ..llm import LlmClient
from ..schemas import (
    CVDoc,
    FollowupResult,
    LetterOutput,
    LetterParagraph,
    MatchResult,
)
from ..since import since_applied
from ..verify import DEFAULT_LEXICON, verify
from .letter import placeholders_left
from .prompts import language_name, render

#: A follow-up is read standing up. Past this it is a second cover letter.
MAX_PARAGRAPHS: Final[int] = 3

#: How many of the new lines the model is shown. More than this and the note
#: stops being about one thing.
MAX_NEW_LINES: Final[int] = 3


async def write_followup(
    llm: LlmClient,
    *,
    cv: CVDoc,
    match: MatchResult,
    sent_at: str | None = None,
    locale: str = "en",
) -> FollowupResult:
    """A grounded follow-up, or the reasoned refusal to write one."""
    since = since_applied(cv, match, sent_at=sent_at)

    # What the application could not show and the CV now names. Nothing here
    # means nothing to send — decided before any model call.
    new_line_ids = [line_id for answer in since.answers for line_id in answer.line_ids]
    seen: dict[str, None] = {}
    for line_id in new_line_ids:
        seen.setdefault(line_id, None)
    new_lines = [line for line in cv.lines if line.id in seen][:MAX_NEW_LINES]

    if not new_lines:
        return FollowupResult(
            match_id=match.id,
            kind="nothing_new",
            days=since.days,
            dated_from=since.dated_from,
        )

    terms = sorted({term for answer in since.answers for term in answer.terms})
    line_text = {line.id: line.text for line in cv.lines}
    output = await _generate(
        llm,
        cv=cv,
        match=match,
        new_lines=[f"{line.id}: {line.text}" for line in new_lines],
        answered=[answer.requirement_id for answer in since.answers],
        locale=locale,
    )

    # The same rule the letter is held to, minus the repair pass: sources are
    # the lines a paragraph cites, or every new line when it cites none.
    all_sources = [line.text for line in new_lines]
    posting_vocab = [req.text for req in match.requirements]
    paragraphs, failed = _keep_verified(
        output, line_text=line_text, all_sources=all_sources, posting_vocab=posting_vocab
    )

    if failed and not any(para.line_ids for para in paragraphs):
        # Nothing grounded survived. One more attempt, told exactly which
        # words it may not use — the same budget `letter` and `tailor` get.
        log(f"followup: repairing a note that used {', '.join(failed)}")
        try:
            output = await _generate(
                llm,
                cv=cv,
                match=match,
                new_lines=[f"{line.id}: {line.text}" for line in new_lines],
                answered=[answer.requirement_id for answer in since.answers],
                locale=locale,
                extra_instruction=(
                    "Your previous draft used facts the CV lines do not support: "
                    f"{', '.join(failed)}. Write the note again without them, "
                    "using only what the lines below actually say."
                ),
            )
        except Exception as exc:  # noqa: BLE001 — a failed repair keeps the verdict
            log(f"followup: repair call failed ({type(exc).__name__})")
        else:
            paragraphs, _ = _keep_verified(
                output,
                line_text=line_text,
                all_sources=all_sources,
                posting_vocab=posting_vocab,
            )

    if not any(para.line_ids for para in paragraphs):
        # A note whose evidence paragraph did not survive is not a shorter
        # note; it is the note failing to exist. Retrying is one call.
        raise EngineError(
            "model_output_invalid",
            "no follow-up paragraph survived verification with evidence attached",
        )

    return FollowupResult(
        match_id=match.id,
        kind="new_evidence",
        days=since.days,
        dated_from=since.dated_from,
        paragraphs=paragraphs,
        # Only the ones the user has to replace by hand: `[Company]` and
        # `[Role]` are filled from the posting at the point of use, exactly as
        # the cover letter fills them (`letter.resolve_placeholders`).
        placeholders=placeholders_left(paragraphs, match),
        line_ids=[line.id for line in new_lines],
        terms=terms[:5],
    )


def _keep_verified(
    output: LetterOutput,
    *,
    line_text: dict[str, str],
    all_sources: list[str],
    posting_vocab: list[str],
) -> tuple[list[LetterParagraph], list[str]]:
    """The paragraphs the verifier passed, and the words that sank the rest."""
    kept: list[LetterParagraph] = []
    failed: list[str] = []
    for item in output.paragraphs[:MAX_PARAGRAPHS]:
        text = item.text.strip()
        if not text:
            continue
        cited = [lid for lid in item.line_ids if lid in line_text]
        sources = [line_text[lid] for lid in cited] if cited else all_sources
        verdict = verify(text, sources, lexicon=DEFAULT_LEXICON, posting_vocab=posting_vocab)
        if verdict.ok:
            kept.append(LetterParagraph(text=text, line_ids=cited))
        else:
            failed.extend(verdict.tokens)
    return kept, sorted(set(failed))


async def _generate(
    llm: LlmClient,
    *,
    cv: CVDoc,
    match: MatchResult,
    new_lines: list[str],
    answered: list[str],
    locale: str,
    extra_instruction: str = "",
) -> LetterOutput:
    system = render("followup.v1.md", output_language=language_name(locale))
    wanted = "\n".join(
        f"- {req.text}"
        for req in match.requirements
        if req.id in set(answered)
    )
    user = (
        "The application was sent some time ago. These CV lines were written "
        "AFTER it went out and are the only new material:\n"
        f"{chr(10).join(new_lines)}\n\n"
        "They speak to what the posting asked for here:\n"
        f"{wanted}\n"
    )
    # The model is never told the real role or employer, for the reason the
    # letter gives: it cannot leak a name it was not given, and the verifier
    # is never asked to ground one.
    user = f"ROLE: [Role]\nCOMPANY: [Company]\n\n{user}"
    if extra_instruction:
        user = f"{extra_instruction}\n\n{user}"
    return await llm.structured(
        name="receipts_followup",
        model=LetterOutput,
        system_prompt=system,
        user_prompt=user,
        max_tokens=768,
    )
