"""The profile — the one thing this app writes that no posting asked for.

Everything else here is written *at* an employer: a tailored bullet, a cover
letter, a form answer, a follow-up. A professional profile is the opposite
shape. Nobody commissions it, it has to be true of the person on any day to
any reader, and it is the text recruiters search before a candidate has
applied to anything at all.

Which is exactly why the category fills it with invention. "Passionate
engineer with a proven track record of driving impact" is written by a model
that was given a job title and nothing else; the harm `prd.md §2` names,
moved from the CV to the paragraph above it.

So the profile is written from the CV and **nothing** else. There is no
posting to lend vocabulary — the one licence `tailor` and `letter` have — so
the rule is stricter here than anywhere else in the app: a term survives only
if a cited CV line contains it. A headline that cannot be grounded is
returned empty, because a profile with an invented headline is worse than a
profile without one, and the screen says so rather than quietly printing
something the CV cannot back.
"""

from __future__ import annotations

from typing import Final

from ..errors import EngineError
from ..host.frames import log
from ..llm import LlmClient
from ..schemas import CVDoc, CVLine, LetterParagraph, ProfileOutput, ProfileResult
from ..verify import DEFAULT_LEXICON, verify
from .prompts import language_name, render

#: LinkedIn allows 220. A headline that long is a paragraph with commas in it,
#: and every extra clause is another claim to ground.
MAX_HEADLINE_CHARS: Final[int] = 120

#: Two or three short paragraphs. An About nobody finishes reading is an About
#: that did not say the thing.
MAX_PARAGRAPHS: Final[int] = 3

#: The CV lines the model is shown. The whole document, minus the header: a
#: name and a phone number are not material for a profile.
MAX_SOURCE_LINES: Final[int] = 40


async def write_profile(
    llm: LlmClient,
    *,
    cv: CVDoc,
    locale: str = "en",
) -> ProfileResult:
    """A headline and an About section that the CV can back, line by line."""
    body = [line for line in cv.lines if line.section != "header"][:MAX_SOURCE_LINES]
    if not body:
        raise EngineError("cv_too_short", "there is nothing in this CV to write a profile from")

    line_text = {line.id: line.text for line in body}
    all_sources = [line.text for line in body]

    output = await _generate(llm, cv=cv, body=body, locale=locale)
    headline, headline_ids, about, failed = _keep_verified(
        output, line_text=line_text, all_sources=all_sources
    )

    if failed and not (headline and about):
        # One more attempt, told exactly which words the CV could not back —
        # the budget `letter`, `tailor` and `followup` are all given.
        log(f"profile: repairing text that used {', '.join(failed)}")
        try:
            output = await _generate(
                llm,
                cv=cv,
                body=body,
                locale=locale,
                extra_instruction=(
                    "Your previous draft used facts the CV lines do not support: "
                    f"{', '.join(failed)}. Write it again without them, using only "
                    "what the lines below actually say."
                ),
            )
        except Exception as exc:  # noqa: BLE001 — a failed repair keeps the verdict
            log(f"profile: repair call failed ({type(exc).__name__})")
        else:
            headline, headline_ids, about, _ = _keep_verified(
                output, line_text=line_text, all_sources=all_sources
            )

    if not about:
        raise EngineError(
            "model_output_invalid",
            "no profile paragraph survived verification with evidence attached",
        )

    return ProfileResult(
        cv_hash=cv.hash,
        headline=headline,
        headline_line_ids=headline_ids,
        about=about,
    )


def _keep_verified(
    output: ProfileOutput,
    *,
    line_text: dict[str, str],
    all_sources: list[str],
) -> tuple[str, list[str], list[LetterParagraph], list[str]]:
    """What the verifier passed, and the words that sank the rest.

    No `posting_vocab`: there is no posting. A profile is the one surface in
    this app with no employer's wording to lend it a concept, so every term in
    it has to come from the CV itself.
    """
    failed: list[str] = []

    headline = output.headline.strip()[:MAX_HEADLINE_CHARS]
    headline_ids = [lid for lid in output.headline_line_ids if lid in line_text]
    if headline:
        sources = [line_text[lid] for lid in headline_ids] if headline_ids else all_sources
        verdict = verify(headline, sources, lexicon=DEFAULT_LEXICON)
        if not verdict.ok:
            failed.extend(verdict.tokens)
            headline, headline_ids = "", []

    about: list[LetterParagraph] = []
    for item in output.about[:MAX_PARAGRAPHS]:
        text = item.text.strip()
        if not text:
            continue
        cited = [lid for lid in item.line_ids if lid in line_text]
        sources = [line_text[lid] for lid in cited] if cited else all_sources
        verdict = verify(text, sources, lexicon=DEFAULT_LEXICON)
        if verdict.ok:
            about.append(LetterParagraph(text=text, line_ids=cited))
        else:
            failed.extend(verdict.tokens)

    return headline, headline_ids, about, sorted(set(failed))


async def _generate(
    llm: LlmClient,
    *,
    cv: CVDoc,
    body: list[CVLine],
    locale: str,
    extra_instruction: str = "",
) -> ProfileOutput:
    system = render("profile.v1.md", output_language=language_name(locale))
    user = (
        "CV LINES YOU MAY USE\n"
        "--------------------\n"
        f"{cv.numbered([line.id for line in body])}"
    )
    if extra_instruction:
        user = f"{extra_instruction}\n\n{user}"

    return await llm.structured(
        name="receipts_profile",
        model=ProfileOutput,
        system_prompt=system,
        user_prompt=user,
        max_tokens=1024,
    )
