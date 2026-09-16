"""Stage 2 — pull the stated requirements out of a posting.

The requirement ids the model returns are renumbered here. A model that skips
R4 or repeats R2 would otherwise produce a `MatchResult` whose evidence cannot
be joined back to its requirements.
"""

from __future__ import annotations

from ..llm import LlmClient
from ..parse.posting import Posting
from ..schemas import ExtractionOutput, Requirement
from .prompts import language_name, render

MAX_REQUIREMENTS = 25


async def extract_requirements(
    llm: LlmClient, posting: Posting, locale: str
) -> tuple[list[Requirement], str | None, str | None]:
    """Return the requirements plus the role and company the posting states."""
    system = render("extract.v1.md", output_language=language_name(locale))
    user = f"JOB POSTING\n-----------\n{posting.text}"

    output = await llm.structured(
        name="receipts_requirements",
        model=ExtractionOutput,
        system_prompt=system,
        user_prompt=user,
        max_tokens=2048,
    )

    requirements: list[Requirement] = []
    seen: set[str] = set()
    for item in output.requirements[:MAX_REQUIREMENTS]:
        text = item.text.strip()
        if not text:
            continue
        # The same requirement worded twice is one requirement; a duplicate
        # would inflate the coverage denominator the user is shown.
        fingerprint = text.casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        requirements.append(
            Requirement(
                id=f"R{len(requirements) + 1}",
                text=text[:120],
                kind=item.kind,
                category=item.category,
                source_quote=_quote(item.source_quote, posting.text),
            )
        )

    title = _hint(output.posting_title) or posting.title_hint
    company = _hint(output.company) or posting.company_hint
    return requirements, title, company


def _hint(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"unknown", "n/a", "none", "-"}:
        return None
    return cleaned[:120]


def _quote(quote: str, posting_text: str) -> str:
    """Keep the quote only when it really is a substring of the posting.

    The quote is shown to the user as "this is where that came from", so a
    reworded one would be a small lie in a product whose whole claim is that it
    does not tell them.
    """
    candidate = quote.strip()[:200]
    if candidate and candidate in posting_text:
        return candidate
    collapsed = " ".join(candidate.split())
    haystack = " ".join(posting_text.split())
    if collapsed and collapsed in haystack:
        return collapsed
    return ""
