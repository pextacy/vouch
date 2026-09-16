"""Stage 3–4 — decide a status per requirement, then guard the citations.

The guard is the important half. The model is asked to cite CV line ids, and
anything it cites that does not exist, or that it cites while claiming
"missing", is corrected here. A hallucinated citation downgrades the status
rather than being quietly dropped: a "strong" match whose only evidence was
imaginary is not a strong match.
"""

from __future__ import annotations

import re
from typing import Final

from ..llm import LlmClient
from ..schemas import CVDoc, Evidence, MatchingOutput, Requirement
from .prompts import language_name, render

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
                line_ids=[lid for lid in item.line_ids if _is_line_id(lid)][:3],
                why=item.why.strip()[:160],
            )
        )
    return evidence


def guard_citations(cv: CVDoc, evidence: list[Evidence]) -> tuple[list[Evidence], int]:
    """Drop citations to lines that do not exist and downgrade what they held up.

    Returns the corrected evidence and how many entries were changed — the
    caller logs the count (never the content) so a prompt regression that starts
    inventing ids is visible in the eval run.
    """
    known = set(cv.text_by_id())
    corrected: list[Evidence] = []
    downgrades = 0

    for item in evidence:
        real = [lid for lid in item.line_ids if lid in known]
        status = item.status
        why = item.why

        if status == "missing":
            real = []  # a citation on a "missing" verdict is a contradiction
        elif not real:
            # Every surviving id was invented — there is no evidence left.
            status = "missing"
            why = ""
            downgrades += 1
        elif len(real) != len(item.line_ids):
            downgrades += 1

        if status != item.status or real != item.line_ids or why != item.why:
            corrected.append(
                Evidence(
                    requirement_id=item.requirement_id,
                    status=status,
                    line_ids=real,
                    why=why,
                )
            )
        else:
            corrected.append(item)

    return corrected, downgrades
