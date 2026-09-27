"""Gap questions — the only honest way to close a gap.

`prd.md §4` principle 3 says a gap is a plan, not a shame. Until now the app
only *stated* the gap: a requirement came back "No evidence yet", the screen
ended there, and the user was left with a diagnosis rather than a plan.

The plan cannot be generated. Anything a model wrote to fill a gap would be an
invention by construction — the gap *is* the absence of evidence. So the app
asks instead. One question per unproven requirement, answered by the user in
their own words, and the answer becomes a CV line the next match can cite. The
only generated artefacts are the question and the angle, and neither of them
ever becomes evidence.

Three rules keep it honest:

* **The question is verified against the CV plus the text of the requirement it
  asks about.** That is what lets "Have you used Kubernetes in production?"
  through when the posting asked for Kubernetes, while still catching "You led
  a team of 12 at Globex — tell me more", which assumes an experience nobody
  mentioned.
* **The angle is verified the ordinary way**, against the CV lines it cites and
  nothing else. It is the "you already have something adjacent" sentence, so it
  makes a claim about the candidate and gets the strict rule. It is dropped
  when it fails, never softened — ``angle=None`` is a normal outcome.
* **Every selected requirement gets an item either way.** A deterministic
  template is the floor, so a model having a bad day costs phrasing, not the
  feature. Those items carry ``templated=True`` so a prompt regression shows up
  as a count instead of quietly flattening every question into one sentence.

Partial requirements are included alongside missing ones. "Related" is where a
career switcher lives, and one remembered sentence is what most often turns it
into real evidence.
"""

from __future__ import annotations

from typing import Final

from ..host.frames import log
from ..llm import LlmClient
from ..schemas import (
    CVDoc,
    GapItem,
    GapOutput,
    GapResult,
    MatchResult,
    Requirement,
)
from ..verify import DEFAULT_LEXICON, verify
from .prompts import language_name, render

#: Enough to be worth a screen, few enough to be worth finishing. A list of
#: twenty gaps reads as a rejection letter rather than as something to work
#: through, and a match with twenty gaps is a match against the wrong job.
DEFAULT_MAX_GAPS: Final[int] = 6
HARD_MAX_GAPS: Final[int] = 10

#: Grounded by construction: it quotes the requirement and says nothing else.
_TEMPLATES: Final[dict[str, str]] = {
    "en": 'Have you done anything that shows "{requirement}"? Even informally — a side project, or one task in an old job.',
    "tr": '"{requirement}" için gösterebileceğiniz bir iş var mı? Gayriresmî de olsa — bir yan proje ya da eski bir işte yaptığınız tek bir görev.',
}


async def plan_gaps(
    llm: LlmClient,
    *,
    cv: CVDoc,
    match: MatchResult,
    max_gaps: int | None = None,
    locale: str = "en",
) -> GapResult:
    """One question per unproven requirement, must-haves first."""
    limit = min(max_gaps or DEFAULT_MAX_GAPS, HARD_MAX_GAPS)
    gaps = _unproven(match, limit)
    if not gaps:
        # Not an error, and not an empty state to apologise for: a match with
        # nothing unproven is the best outcome this product has.
        return GapResult(match_id=match.id, items=[])

    output_locale = locale if locale in {"en", "tr"} else "en"
    phrased = await _generate(llm, cv=cv, gaps=gaps, locale=output_locale)
    line_text = cv.text_by_id()

    items: list[GapItem] = []
    templated = 0
    for requirement in gaps:
        draft = phrased.get(requirement.id)
        question = draft.question if draft else None
        if question is None or not _question_is_grounded(question, cv, requirement):
            templated += 1
            question = _template(requirement, output_locale)
            item_templated = True
        else:
            item_templated = False

        angle, cited = _checked_angle(draft, line_text) if draft else (None, [])
        items.append(
            GapItem(
                requirement_id=requirement.id,
                question=question[:200],
                angle=angle,
                line_ids=cited,
                templated=item_templated,
            )
        )

    if templated:
        log(f"gaps: {templated} of {len(gaps)} questions fell back to the template")
    return GapResult(match_id=match.id, items=items)


def _unproven(match: MatchResult, limit: int) -> list[Requirement]:
    """Requirements the CV does not prove, in the order attention runs out.

    Must-haves first, because they decide whether the application is worth
    sending at all; within each kind, a missing requirement before a partial
    one, because that is the bigger hole.
    """
    status = {e.requirement_id: e.status for e in match.evidence}
    unproven = [
        req for req in match.requirements if status.get(req.id, "missing") != "strong"
    ]
    unproven.sort(
        key=lambda req: (
            0 if req.kind == "must" else 1,
            0 if status.get(req.id, "missing") == "missing" else 1,
        )
    )
    return unproven[:limit]


async def _generate(
    llm: LlmClient, *, cv: CVDoc, gaps: list[Requirement], locale: str
) -> dict[str, _Draft]:
    """Ask for the phrasing. A failure here is not fatal — the template is."""
    system = render("gaps.v1.md", output_language=language_name(locale))
    listing = "\n".join(f"{req.id} [{req.kind}] {req.text}" for req in gaps)
    user = (
        "REQUIREMENTS THE CV DOES NOT PROVE\n"
        "----------------------------------\n"
        f"{listing}\n\n"
        "THE CANDIDATE'S CV LINES\n"
        "------------------------\n"
        f"{cv.numbered()}"
    )

    try:
        output = await llm.structured(
            name="receipts_gaps",
            model=GapOutput,
            system_prompt=system,
            user_prompt=user,
            max_tokens=1536,
        )
    except Exception as exc:  # noqa: BLE001 — the template covers every gap
        log(f"gaps: phrasing call failed ({type(exc).__name__}) — using templates")
        return {}

    wanted = {req.id for req in gaps}
    drafts: dict[str, _Draft] = {}
    for item in output.gaps:
        question = item.question.strip()
        if item.requirement_id in wanted and question and item.requirement_id not in drafts:
            drafts[item.requirement_id] = _Draft(
                question=question,
                angle=item.angle.strip(),
                line_ids=list(item.line_ids),
            )
    return drafts


class _Draft:
    """What the model proposed for one requirement, before any of it is trusted."""

    __slots__ = ("angle", "line_ids", "question")

    def __init__(self, *, question: str, angle: str, line_ids: list[str]) -> None:
        self.question = question
        self.angle = angle
        self.line_ids = line_ids


def _question_is_grounded(question: str, cv: CVDoc, requirement: Requirement) -> bool:
    """A question may use the CV's words and the requirement's own words.

    The requirement belongs in the sources because the question is *about* it:
    naming the technology the posting asked for is the whole point, not a leak.
    What the rule still catches is the employer, the number or the tool that
    appears in neither — the shape of a question that assumes an experience.
    """
    sources = [line.text for line in cv.lines] + [requirement.text]
    verdict = verify(question, sources, lexicon=DEFAULT_LEXICON)
    if not verdict.ok:
        log(f"gaps: dropped phrasing for {requirement.id} ({len(verdict.unsupported)} claims)")
    return verdict.ok


def _checked_angle(draft: _Draft, line_text: dict[str, str]) -> tuple[str | None, list[str]]:
    """The "you already have something adjacent" sentence, or nothing.

    Unlike the question, the angle makes a claim about the candidate, so it gets
    the strict rule every other generated sentence gets: checked against the CV
    lines it cites, and dropped rather than softened when it fails.
    """
    if not draft.angle:
        return None, []
    cited = [lid for lid in draft.line_ids if lid in line_text]
    if not cited:
        return None, []
    sources = [line_text[lid] for lid in cited]
    if not verify(draft.angle, sources, lexicon=DEFAULT_LEXICON).ok:
        log("gaps: dropped an angle the cited lines do not support")
        return None, []
    return draft.angle[:200], cited[:3]


def _template(requirement: Requirement, locale: str) -> str:
    return _TEMPLATES.get(locale, _TEMPLATES["en"]).format(requirement=requirement.text)
