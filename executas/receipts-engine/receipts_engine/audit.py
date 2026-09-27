"""The CV audit — what an interviewer will probe, found without a model.

`prd.md §2` names the harm this product exists to prevent: *"Existing AI resume
tools improve CVs by inventing experience — fake metrics, tools never used. It
surfaces in interviews and burns the candidate."* Every verifier in this
codebase protects the text the app **generates**. Nothing has ever looked at
the CV the user already has, and that is where their real interview risk lives
— usually put there by a previous tool, or by themselves at 1 a.m.

So this reads the user's own document and reports what a recruiter will ask
about. Three questions, all of them answerable by set arithmetic:

=================  =========================================================
skill_unevidenced  a tool in the skills list that no experience, project or
                   certification line ever shows being used. The single most
                   probed weakness on a CV: "I see Kubernetes here — where
                   did you use it?"
title_unevidenced  a seniority word claimed in the header or the summary that
                   no experience line carries. "You call yourself senior; the
                   roles below do not."
date_conflict      a range that ends before it starts, or two experience
                   ranges overlapping by years. Often innocent — consulting,
                   a part-time role — which is exactly why it gets asked.
=================  =========================================================

**No model, no tokens, no quota.** It is pure set arithmetic over the parsed
CV, so it is instant, free, deterministic, and it works before the user has a
posting to check — the only thing in this app that does.

It also states no opinion. A finding carries a `kind` and a `subject`; the
sentence the user reads comes from the UI's string table, in their language,
the same way error codes do (`docs.md §3`). The engine's job is to find the
thing, not to phrase the accusation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from .schemas import CvAudit, CVDoc, CvFinding, Section
from .text import normalize
from .verify import (
    CANONICAL,
    DEFAULT_LEXICON,
    title_surfaces,
    titles_in,
    year_ranges_in,
)

#: Sections whose lines can *show* a skill being used, as opposed to listing it.
_EVIDENCING_SECTIONS: Final[frozenset[Section]] = frozenset(
    {"experience", "projects", "certifications", "summary"}
)

#: Where a title is claimed about the person rather than about a job they held.
_CLAIMING_SECTIONS: Final[frozenset[Section]] = frozenset({"header", "summary"})

#: Two roles overlapping by a year is ordinary — a notice period, a handover.
#: By two it is a question worth being ready for.
MIN_OVERLAP_YEARS: Final[int] = 2

#: A wall of findings reads as a verdict on the person. Enough to act on.
MAX_FINDINGS: Final[int] = 12


def audit_cv(cv: CVDoc) -> CvAudit:
    """Everything in this CV that an interviewer is likely to press on."""
    findings: list[CvFinding] = [
        *_unevidenced_skills(cv),
        *_unevidenced_titles(cv),
        *_date_conflicts(cv),
    ]
    return CvAudit(cv_hash=cv.hash, findings=findings[:MAX_FINDINGS])


# ─── Skills listed but never shown ────────────────────────────────────


def _unevidenced_skills(cv: CVDoc) -> list[CvFinding]:
    """Tools in the skills list that no other section shows in use."""
    listed: dict[str, list[str]] = {}
    # How the CV spells each term, so the finding can say it back in the
    # user's own words rather than in the lexicon's.
    written: dict[str, str] = {}
    for line in cv.lines:
        if line.section != "skills":
            continue
        normalized = normalize(line.text)
        spellings = DEFAULT_LEXICON.surfaces(line.text)
        for term in DEFAULT_LEXICON.matches(normalized):
            if _negated(term, normalized):
                continue
            listed.setdefault(term, []).append(line.id)
            if term in spellings:
                written.setdefault(term, spellings[term])

    if not listed:
        return []

    evidencing = [line for line in cv.lines if line.section in _EVIDENCING_SECTIONS]
    if not evidencing:
        # A CV that is only a skills list has one problem, and it is not this
        # one. Reporting every term would be noise dressed up as insight.
        return []

    shown: set[str] = set()
    for line in evidencing:
        shown |= DEFAULT_LEXICON.matches(normalize(line.text))

    return [
        CvFinding(
            kind="skill_unevidenced",
            subject=term,
            surface=written.get(term, term),
            line_ids=listed[term][:3],
        )
        for term in sorted(listed.keys() - shown)
    ]


#: Ways a skills line names a technology in order to say it is *not* used.
#: "Terraform-free infra" is a claim about architecture, not a skill — and
#: telling someone they cannot back a claim they never made is the worst
#: mistake this feature can make.
_NEGATIONS: Final[tuple[str, ...]] = ("{term} free", "no {term}", "without {term}", "{term}siz", "{term}suz")


def _negated(term: str, normalized_line: str) -> bool:
    """Whether the line mentions ``term`` only to rule it out."""
    spellings = {normalize(term), *(normalize(alt) for alt in CANONICAL.get(term, ()))}
    return any(
        pattern.format(term=spelling) in normalized_line
        for spelling in spellings
        if spelling
        for pattern in _NEGATIONS
    )


# ─── Titles claimed but not carried by a role ─────────────────────────


def _unevidenced_titles(cv: CVDoc) -> list[CvFinding]:
    """Seniority claimed at the top that the roles below do not carry."""
    claimed: dict[str, list[str]] = {}
    written: dict[str, str] = {}
    for line in cv.lines:
        if line.section not in _CLAIMING_SECTIONS:
            continue
        spellings = title_surfaces(line.text)
        for title in titles_in(line.text):
            claimed.setdefault(title, []).append(line.id)
            if title in spellings:
                written.setdefault(title, spellings[title])

    if not claimed:
        return []

    experience = [line for line in cv.lines if line.section == "experience"]
    if not experience:
        return []

    carried: set[str] = set()
    for line in experience:
        carried |= titles_in(line.text)

    return [
        CvFinding(
            kind="title_unevidenced",
            subject=title,
            surface=written.get(title, title),
            line_ids=claimed[title][:3],
        )
        for title in sorted(claimed.keys() - carried)
    ]


# ─── Dates that do not agree ──────────────────────────────────────────


def _date_conflicts(cv: CVDoc) -> list[CvFinding]:
    """Reversed ranges, and experience ranges that overlap for years."""
    findings: list[CvFinding] = []
    spans: list[tuple[int, int, str]] = []
    this_year = datetime.now(UTC).year

    for line in cv.lines:
        for start, end in year_ranges_in(line.text):
            if end is not None and end < start:
                findings.append(
                    CvFinding(
                        kind="date_conflict",
                        subject=f"{start}-{end}",
                        surface=f"{start}-{end}",
                        line_ids=[line.id],
                    )
                )
                continue
            if line.section == "experience":
                spans.append((start, end if end is not None else this_year, line.id))

    for index, (start, end, line_id) in enumerate(spans):
        for other_start, other_end, other_id in spans[index + 1 :]:
            if line_id == other_id:
                continue
            overlap = min(end, other_end) - max(start, other_start)
            if overlap >= MIN_OVERLAP_YEARS:
                findings.append(
                    CvFinding(
                        kind="date_conflict",
                        subject=f"{max(start, other_start)}-{min(end, other_end)}",
                        surface=f"{max(start, other_start)}-{min(end, other_end)}",
                        line_ids=sorted({line_id, other_id}),
                    )
                )

    return findings
