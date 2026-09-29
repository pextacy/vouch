"""The interview brief — the receipts, ordered by what will be pressed.

The app has been honest all the way up to the moment the application is sent,
and then it stops. The tracker lets someone mark a row *Interview* and nothing
happens; the one screen where the promise of this product is actually tested —
a room where a person is asked to back up what they wrote — is the one screen
it had nothing to say about.

This is that screen's data, and it is the only app that can produce it: it
already stores which CV line was accepted as evidence for which requirement,
and which of its own sentences the user accepted and sent. Nobody else holds
both halves, so nobody else can say *"this is the sentence they are holding,
and this is the line in your CV underneath it."*

**Nothing here is written.** Every sentence on the brief is either the user's
own CV line or a sentence the verifier already passed and the user already
accepted. A brief that generated an answer would be inventing the one thing
the user has to say out loud in their own voice — the failure mode `prd.md §2`
names, arriving at the exact moment it costs the most.

**No model, no tokens, no quota**, like `audit_cv` and `recurring_gaps`: this
is set arithmetic over records that already exist, so it is instant, free and
the same every time.

Six verdicts, and each one is about the *shape* of the evidence, never about
the person:

=================  =========================================================
no_evidence        the posting asked and the CV never answered. The honest
                   preparation is what to say instead — not a story invented
                   on the way to the building.
self_asserted      the match found nothing and the *user* said a line covers
                   it anyway. Admissible — it is their career — but it is the
                   one claim on the brief nobody except the candidate has
                   agreed with, so it is the one they have to make out loud.
listed_not_shown   every line cited for it is in the skills list. The match
                   was right that the word is there, and a skills list is the
                   weakest possible answer to "where did you use it?" — the
                   single most probed weakness on a CV (`audit.py`).
self_added         every line cited for it is one the user typed into
                   Vouch (`added_at`). It is admissible evidence here, but
                   it is almost certainly not in the document that was sent.
related_only       the match called it `partial`. Adjacent, not the same
                   thing, and the interviewer's job is to find the seam.
proved             a line from the document itself backs it. The receipt.
=================  =========================================================

Ranking is must-haves first, then that order. A must-have with nothing behind
it is the question that ends interviews, and a brief that opened with the
nice-to-haves would be sorted by the app's convenience rather than the user's
risk.
"""

from __future__ import annotations

from typing import Final

from .schemas import (
    Assertion,
    BriefClaim,
    BriefItem,
    BriefRisk,
    CVDoc,
    CVLine,
    Evidence,
    InterviewBrief,
    LetterResult,
    MatchResult,
    Status,
    TailorResult,
)

#: Enough to prepare with. A longer list is not preparation, it is a reading
#: exercise the night before — the same reason the audit caps at 12.
MAX_RISKS: Final[int] = 12

#: The strengths half is there so the brief is not only a list of weaknesses,
#: not so it can be exhaustive.
MAX_PROVED: Final[int] = 8

#: Per requirement. Three sentences about one requirement is already more than
#: anyone will hold in their head walking in.
MAX_CLAIMS: Final[int] = 3

#: Sentences that back no single requirement — the letter's opening and its
#: closing, usually.
MAX_LOOSE_CLAIMS: Final[int] = 3

#: Hardest question first, within a kind. `proved` is last by construction:
#: it never reaches the risk list.
_RISK_ORDER: Final[dict[BriefRisk, int]] = {
    "no_evidence": 0,
    # Second only to having nothing. A skills-list mention is at least a word
    # the match accepted; an assertion is a line the app never agreed backs
    # this, so it is the hardest thing on the brief the candidate can still
    # actually answer.
    "self_asserted": 1,
    "listed_not_shown": 2,
    "self_added": 3,
    "related_only": 4,
    "proved": 5,
}


def interview_brief(
    cv: CVDoc,
    match: MatchResult,
    tailor: TailorResult | None = None,
    letter: LetterResult | None = None,
    assertions: list[Assertion] | None = None,
) -> InterviewBrief:
    """Everything this application will be asked to back up.

    ``tailor`` should carry only the bullets the user accepted — those are the
    ones that were sent, and the brief is about what the interviewer is
    holding, not about what the app once suggested.

    Unlike ``tailor`` and ``letter``, this does **not** refuse a CV whose hash
    has moved since the match. Answering a gap question moves the hash, so
    refusing would lock the brief for exactly the users who prepared hardest.
    The drift is reported instead (``cv_changed``), because it is worth
    knowing on its own: the document the interviewer is holding is the older
    one.

    ``assertions`` are the requirements the user told the app it got wrong.
    They are read here rather than merged into ``match.evidence`` anywhere,
    because the point of recording them separately is that the app's verdict
    and the candidate's are never the same thing — and this is the screen
    where that distinction has to survive into the room.
    """
    lines = {line.id: line for line in cv.lines}
    evidence_by_id = {item.requirement_id: item for item in match.evidence}
    asserted = {
        item.requirement_id: [lid for lid in item.line_ids if lid in lines]
        for item in assertions or []
    }
    claims_by_requirement, loose = _claims(match, tailor, letter, lines)

    ranked: list[tuple[int, int, BriefItem]] = []
    for index, requirement in enumerate(match.requirements):
        evidence = evidence_by_id.get(requirement.id)
        claimed = asserted.get(requirement.id)
        if claimed:
            # The user's lines, not the match's: they are what will be pointed
            # at in the room, and the match pointed at nothing.
            cited = [lines[lid] for lid in claimed]
            risk: BriefRisk = "self_asserted"
        else:
            cited = _cited_lines(evidence, lines)
            risk = _risk(evidence.status if evidence else "missing", cited)
        item = BriefItem(
            requirement_id=requirement.id,
            kind=requirement.kind,
            risk=risk,
            line_ids=[line.id for line in cited],
            claims=claims_by_requirement.get(requirement.id, [])[:MAX_CLAIMS],
        )
        ranked.append((0 if requirement.kind == "must" else 1, index, item))

    ranked.sort(key=lambda row: (row[0], _RISK_ORDER[row[2].risk], row[1]))

    return InterviewBrief(
        match_id=match.id,
        cv_hash=cv.hash,
        cv_changed=match.cv_hash != cv.hash,
        risks=[item for _, _, item in ranked if item.risk != "proved"][:MAX_RISKS],
        proved=[item for _, _, item in ranked if item.risk == "proved"][:MAX_PROVED],
        loose_claims=loose[:MAX_LOOSE_CLAIMS],
    )


def _cited_lines(evidence: Evidence | None, lines: dict[str, CVLine]) -> list[CVLine]:
    """The cited lines that are still in the CV, in the order they were cited.

    A citation can outlive its line: the match is stored, the CV is editable,
    and this is the one action that accepts a CV the match was not made
    against. A dangling id is dropped rather than rendered, because the brief
    exists to be read next to the document and a line number pointing at
    nothing reads as the app having lost the evidence.
    """
    if evidence is None:
        return []
    return [lines[line_id] for line_id in evidence.line_ids if line_id in lines]


def _risk(status: Status, cited: list[CVLine]) -> BriefRisk:
    """What kind of question this requirement is going to be.

    Order matters. ``listed_not_shown`` is checked before the status is read
    at all, because a `strong` verdict whose only support is a skills line is
    the dangerous one: the app told the user they were covered, and the
    interviewer is about to find out what "covered" meant.
    """
    if status == "missing" or not cited:
        return "no_evidence"
    if all(line.section == "skills" for line in cited):
        return "listed_not_shown"
    if all(line.added_at for line in cited):
        return "self_added"
    if status == "partial":
        return "related_only"
    return "proved"


def _claims(
    match: MatchResult,
    tailor: TailorResult | None,
    letter: LetterResult | None,
    lines: dict[str, CVLine],
) -> tuple[dict[str, list[BriefClaim]], list[BriefClaim]]:
    """Attach every sentence that was sent to the requirement it speaks to.

    A bullet says which requirements it was written for, so it is filed under
    those. A letter paragraph does not, so it is filed under every requirement
    whose evidence it shares a line with — the same join the citations under
    the paragraph already make visible on the letter screen.

    A sentence that matches nothing is not dropped. It was still sent, and a
    brief that quietly omitted a paragraph would be telling the user they said
    less than they did.
    """
    cited_by_requirement = {
        item.requirement_id: {line for line in item.line_ids if line in lines}
        for item in match.evidence
    }
    known = {requirement.id for requirement in match.requirements}

    attached: dict[str, list[BriefClaim]] = {}
    loose: list[BriefClaim] = []

    def file_under(claim: BriefClaim, targets: set[str]) -> None:
        if not targets:
            loose.append(claim)
            return
        for requirement_id in sorted(targets):
            attached.setdefault(requirement_id, []).append(claim)

    for bullet in tailor.bullets if tailor else []:
        # A dropped suggestion was never shown as something to send, so it is
        # not something the interviewer can be holding.
        if not bullet.suggestion:
            continue
        claim = BriefClaim(
            source="bullet",
            text=bullet.suggestion,
            line_ids=[line for line in bullet.source_line_ids if line in lines],
        )
        targets = {target for target in bullet.targets if target in known}
        file_under(claim, targets or _overlapping(claim.line_ids, cited_by_requirement))

    for paragraph in letter.paragraphs if letter else []:
        if not paragraph.text.strip():
            continue
        claim = BriefClaim(
            source="letter",
            text=paragraph.text,
            line_ids=[line for line in paragraph.line_ids if line in lines],
        )
        file_under(claim, _overlapping(claim.line_ids, cited_by_requirement))

    return attached, loose


def _overlapping(line_ids: list[str], cited: dict[str, set[str]]) -> set[str]:
    """Requirements whose evidence shares a line with this sentence."""
    wanted = set(line_ids)
    if not wanted:
        return set()
    return {
        requirement_id
        for requirement_id, evidence_lines in cited.items()
        if wanted & evidence_lines
    }
