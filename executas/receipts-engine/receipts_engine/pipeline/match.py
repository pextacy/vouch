"""Stage 3–4 — decide a status per requirement, then guard the citations.

The guard is the important half, and for a long time it was only half a guard.
It checked that a cited line **exists**; it never checked that the line
*says the thing the posting asked for*. So the one verdict this product is
named after — a `strong` match, the receipt — was the only generated claim in
the app that no deterministic rule ever read. `tailor` and `letter` are
checked sentence by sentence; the map behind them was taken on trust, and
`scripts/eval_match.py` has been printing the cost of that all along as the
false-`strong` rate.

Two rules now, in order:

**Invented citations.** An id that is not in the CV is dropped, and a verdict
whose every id was invented falls to `missing`. Unchanged.

**Unshown demands.** When a requirement names a technology — a term the
lexicon knows, so "Kubernetes", "PostgreSQL", "k8s", not "stakeholder
management" — a `strong` verdict has to cite a line that actually contains it.
When it does not, one of two things is true and they are treated differently:

* the CV shows the term on **another** line: the evidence exists and the
  pointer was wrong, so the citation is **repaired** with the line that shows
  it and the verdict stands;
* the CV does not show it **anywhere**: the model matched on resemblance, so
  the verdict falls to `partial` — which is precisely what "related, not the
  same thing" means — the model's ``why`` is cleared, because it was a
  sentence about a strength that is not there, and the unshown terms are
  recorded for the UI to name.

Deliberately narrow, because a false downgrade is worse than the disease:

* only `strong` is checked. `partial` already claims adjacency and nothing
  more, and `missing` claims nothing;
* only **technologies** are demanded. A title would wreck it — "Lead a team"
  against "Led a team of 4 engineers" is the same fact and not the same word —
  and a duration lives in date ranges on lines nobody cited. Concepts are
  exactly what the model is better at than any lexicon, and they are left to
  it;
* the user can always disagree (`prd.md` F20). A guard that made the app
  stricter without giving the person a reply address would be trading one kind
  of wrong for another.
"""

from __future__ import annotations

import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Final

from ..llm import LlmClient
from ..schemas import CVDoc, Evidence, MatchingOutput, Requirement
from ..text import normalize
from ..verify import DEFAULT_LEXICON
from .prompts import language_name, render

#: Lines added to repair a citation. Two is enough to point at; more is the
#: guard writing the answer rather than correcting the pointer.
MAX_REPAIR_LINES: Final[int] = 2

#: What a verdict may cite, matching the cap `_to_evidence` already applies.
MAX_CITED_LINES: Final[int] = 3

_LINE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^L\d+$")


def _is_line_id(value: object) -> bool:
    """Shape check before the existence check — a malformed id is not a typo."""
    return isinstance(value, str) and bool(_LINE_ID_RE.match(value))


async def match_requirements(
    llm: LlmClient, cv: CVDoc, requirements: list[Requirement], locale: str
) -> list[Evidence]:
    """Ask the model for a status per requirement (ungated)."""
    system = render("match.v1.md", output_language=language_name(locale))
    listing = "\n".join(f"{req.id} [{req.kind}] {req.text}" for req in requirements)
    user = (
        "REQUIREMENTS\n------------\n"
        f"{listing}\n\n"
        "CANDIDATE CV LINES\n------------------\n"
        f"{cv.numbered()}"
    )

    output = await llm.structured(
        name="receipts_evidence",
        model=MatchingOutput,
        system_prompt=system,
        user_prompt=user,
        max_tokens=3072,
    )
    return _to_evidence(output, requirements)


def _to_evidence(output: MatchingOutput, requirements: list[Requirement]) -> list[Evidence]:
    by_id = {item.requirement_id: item for item in output.evidence}
    evidence: list[Evidence] = []
    for req in requirements:
        item = by_id.get(req.id)
        if item is None:
            # Silence is not evidence. A requirement the model skipped is
            # unproven, which is exactly what "missing" means.
            evidence.append(
                Evidence(
                    requirement_id=req.id,
                    status="missing",
                    line_ids=[],
                    why="",
                )
            )
            continue
        evidence.append(
            Evidence(
                requirement_id=req.id,
                status=item.status,
                line_ids=[lid for lid in item.line_ids if _is_line_id(lid)][:MAX_CITED_LINES],
                why=item.why.strip()[:160],
            )
        )
    return evidence


@dataclass(frozen=True)
class GuardReport:
    """What the guard had to correct. Counts only — never CV content."""

    #: Citations to lines that do not exist.
    invented: int = 0
    #: `strong` verdicts whose citation was pointed at the wrong line.
    repaired: int = 0
    #: `strong` verdicts the CV cannot back, downgraded to `partial`.
    unproven: int = 0

    @property
    def total(self) -> int:
        return self.invented + self.repaired + self.unproven


def guard_citations(
    cv: CVDoc, requirements: list[Requirement], evidence: list[Evidence]
) -> tuple[list[Evidence], GuardReport]:
    """Make every verdict's citation true, or make the verdict smaller."""
    lines = cv.text_by_id()
    known = set(lines)
    demanded = {req.id: _demanded_terms(req) for req in requirements}
    shown_by_line = {lid: DEFAULT_LEXICON.matches(normalize(text)) for lid, text in lines.items()}

    corrected: list[Evidence] = []
    invented = repaired = unproven = 0

    for item in evidence:
        real = [lid for lid in item.line_ids if lid in known]
        status = item.status
        why = item.why
        unshown: list[str] = []

        if status == "missing":
            real = []  # a citation on a "missing" verdict is a contradiction
        elif not real:
            # Every surviving id was invented — there is no evidence left.
            status = "missing"
            why = ""
            invented += 1
        elif len(real) != len(item.line_ids):
            invented += 1

        # Only the receipt is held to the second rule.
        if status == "strong":
            wanted = demanded.get(item.requirement_id, frozenset())
            cited_shows: set[str] = set()
            for lid in real:
                cited_shows |= shown_by_line.get(lid, set())
            missing_terms = wanted - cited_shows
            if missing_terms:
                elsewhere = _lines_showing(missing_terms, shown_by_line, exclude=real)
                if elsewhere:
                    # The proving lines are kept whole and the original
                    # citation gives up room for them: a repair that got
                    # truncated away would leave the verdict standing on the
                    # citation that failed.
                    room = max(0, MAX_CITED_LINES - len(elsewhere))
                    real = [*real[:room], *elsewhere]
                    repaired += 1
                else:
                    status = "partial"
                    # The sentence described a strength the lines do not show.
                    why = ""
                    unshown = sorted(_surface(term, requirements, item.requirement_id) for term in missing_terms)
                    unproven += 1

        if (
            status != item.status
            or real != item.line_ids
            or why != item.why
            or unshown != item.unshown
        ):
            corrected.append(
                Evidence(
                    requirement_id=item.requirement_id,
                    status=status,
                    line_ids=real,
                    why=why,
                    unshown=unshown,
                )
            )
        else:
            corrected.append(item)

    return corrected, GuardReport(invented=invented, repaired=repaired, unproven=unproven)


def _demanded_terms(requirement: Requirement) -> frozenset[str]:
    """Technologies the requirement asks for by name.

    Empty for most requirements, and that is the point: "Experience leading a
    small team" demands nothing a lexicon can check, so nothing here touches
    it. The check only fires where the posting named a thing.
    """
    return frozenset(DEFAULT_LEXICON.matches(normalize(requirement.text)))


def _lines_showing(
    terms: AbstractSet[str], shown_by_line: dict[str, set[str]], *, exclude: list[str]
) -> list[str]:
    """CV lines that do show the terms a citation missed, in reading order."""
    found: list[str] = []
    remaining = set(terms)
    for line_id, shown in shown_by_line.items():
        if line_id in exclude or not remaining & shown:
            continue
        found.append(line_id)
        remaining -= shown
        if not remaining or len(found) == MAX_REPAIR_LINES:
            break
    # A partial repair is not a repair: if some demanded term is still shown
    # nowhere, the verdict is not strong and the caller has to say so.
    return found if not remaining else []


def _surface(term: str, requirements: list[Requirement], requirement_id: str) -> str:
    """The term as the **posting** writes it, never the lexicon's own spelling.

    `CLAUDE.md` rule 9: showing someone "kubernetes" when the posting said
    "K8s" reads as the app not having looked properly.
    """
    for req in requirements:
        if req.id == requirement_id:
            written = DEFAULT_LEXICON.surfaces(req.text).get(term)
            if written:
                return written[:80]
    return term[:80]
