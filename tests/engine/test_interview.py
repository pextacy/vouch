"""The interview brief: what gets called a risk, and in what order.

Two failure modes matter here, and they are opposites.

Calling something proved when the only evidence is a word in a skills list
sends someone into a room believing they are covered — the app's own promise
failing at the one moment it is tested out loud. And calling something a risk
when a real experience line backs it fills the brief with noise until nobody
reads the three lines that mattered.

No model is involved anywhere in this file.
"""

from __future__ import annotations

from receipts_engine.interview import MAX_CLAIMS, MAX_PROVED, MAX_RISKS, interview_brief
from receipts_engine.schemas import (
    Assertion,
    CVDoc,
    CVLine,
    Evidence,
    LetterParagraph,
    LetterResult,
    MatchResult,
    MatchSummary,
    PostingMeta,
    Requirement,
    TailoredBullet,
    TailorResult,
)

ADDED = "2026-09-18T10:00:00+00:00"


def _cv(*lines: CVLine, hash_: str = "cv-1") -> CVDoc:
    return CVDoc(hash=hash_, lines=list(lines), detected_language="en")


def _line(id_: str, text: str, section: str = "experience", added: str | None = None) -> CVLine:
    return CVLine(id=id_, text=text, section=section, added_at=added)  # type: ignore[arg-type]


def _match(
    requirements: list[Requirement],
    evidence: list[Evidence],
    *,
    cv_hash: str = "cv-1",
) -> MatchResult:
    return MatchResult(
        id="m1",
        created_at="2026-09-19T09:00:00+00:00",
        posting=PostingMeta(hash="p1", language="en", title="Backend Engineer"),
        requirements=requirements,
        evidence=evidence,
        summary=MatchSummary(
            total=len(requirements),
            strong=sum(1 for item in evidence if item.status == "strong"),
            partial=sum(1 for item in evidence if item.status == "partial"),
            missing=sum(1 for item in evidence if item.status == "missing"),
            must_missing=0,
            sentence="",
        ),
        cv_hash=cv_hash,
    )


def _requirement(id_: str, text: str, kind: str = "must") -> Requirement:
    return Requirement(
        id=id_,
        text=text,
        kind=kind,  # type: ignore[arg-type]
        category="skill",
        source_quote=text,
    )


def _risk_of(brief, requirement_id: str) -> str | None:
    for item in [*brief.risks, *brief.proved]:
        if item.requirement_id == requirement_id:
            return item.risk
    return None


# ─── What counts as a receipt ─────────────────────────────────────────


def test_an_experience_line_is_a_receipt() -> None:
    cv = _cv(_line("L1", "Built payment services in Go for 1,200 merchants."))
    match = _match(
        [_requirement("R1", "Production Go")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )
    brief = interview_brief(cv, match)

    assert [item.requirement_id for item in brief.proved] == ["R1"]
    assert brief.risks == []
    assert brief.proved[0].line_ids == ["L1"]


def test_a_skills_list_is_not_a_receipt() -> None:
    """The dangerous case: the match said strong, and the proof is a word."""
    cv = _cv(_line("L1", "Go, Kubernetes, PostgreSQL", section="skills"))
    match = _match(
        [_requirement("R1", "Running services on Kubernetes")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )
    brief = interview_brief(cv, match)

    assert _risk_of(brief, "R1") == "listed_not_shown"
    assert brief.proved == []


def test_one_real_line_beside_a_skills_line_is_still_a_receipt() -> None:
    cv = _cv(
        _line("L1", "Go, Kubernetes, PostgreSQL", section="skills"),
        _line("L2", "Ran the settlement workers on Kubernetes across two regions."),
    )
    match = _match(
        [_requirement("R1", "Kubernetes")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1", "L2"], why="")],
    )
    assert _risk_of(interview_brief(cv, match), "R1") == "proved"


def test_a_line_the_user_added_here_is_flagged_as_not_in_the_sent_document() -> None:
    cv = _cv(_line("L1", "I ran the Kafka consumers for the payout feed.", added=ADDED))
    match = _match(
        [_requirement("R1", "Kafka")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )
    assert _risk_of(interview_brief(cv, match), "R1") == "self_added"


def test_partial_evidence_reads_as_related_only() -> None:
    cv = _cv(_line("L1", "Ran RabbitMQ consumers for the payout feed."))
    match = _match(
        [_requirement("R1", "Kafka")],
        [Evidence(requirement_id="R1", status="partial", line_ids=["L1"], why="")],
    )
    assert _risk_of(interview_brief(cv, match), "R1") == "related_only"


def test_nothing_cited_is_no_evidence_whatever_the_status_says() -> None:
    """A status of `strong` with no lines is a record from a worse version."""
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match(
        [_requirement("R1", "Kafka")],
        [Evidence(requirement_id="R1", status="strong", line_ids=[], why="")],
    )
    assert _risk_of(interview_brief(cv, match), "R1") == "no_evidence"


def test_a_requirement_with_no_evidence_entry_at_all_is_no_evidence() -> None:
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match([_requirement("R1", "Kafka")], [])
    assert _risk_of(interview_brief(cv, match), "R1") == "no_evidence"


def test_a_citation_whose_line_is_gone_is_dropped_not_rendered() -> None:
    """The CV is editable and the match is stored; ids can outlive lines."""
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match(
        [_requirement("R1", "Kafka")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L9"], why="")],
    )
    brief = interview_brief(cv, match)
    assert brief.risks[0].line_ids == []
    assert brief.risks[0].risk == "no_evidence"


# ─── Order ────────────────────────────────────────────────────────────


def test_must_haves_come_before_nice_to_haves_however_bad_the_nice_one_is() -> None:
    cv = _cv(_line("L1", "Ran RabbitMQ consumers for the payout feed."))
    match = _match(
        [
            _requirement("R1", "Terraform", kind="nice"),
            _requirement("R2", "Kafka", kind="must"),
        ],
        [
            Evidence(requirement_id="R1", status="missing", line_ids=[], why=""),
            Evidence(requirement_id="R2", status="partial", line_ids=["L1"], why=""),
        ],
    )
    assert [item.requirement_id for item in interview_brief(cv, match).risks] == ["R2", "R1"]


def test_the_hardest_question_in_a_kind_comes_first() -> None:
    cv = _cv(
        _line("L1", "Go, Kubernetes", section="skills"),
        _line("L2", "Ran RabbitMQ consumers for the payout feed."),
    )
    match = _match(
        [
            _requirement("R1", "Kubernetes"),
            _requirement("R2", "Kafka"),
            _requirement("R3", "Terraform"),
        ],
        [
            Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why=""),
            Evidence(requirement_id="R2", status="partial", line_ids=["L2"], why=""),
            Evidence(requirement_id="R3", status="missing", line_ids=[], why=""),
        ],
    )
    assert [item.risk for item in interview_brief(cv, match).risks] == [
        "no_evidence",
        "listed_not_shown",
        "related_only",
    ]


# ─── What was actually sent ───────────────────────────────────────────


def test_an_accepted_bullet_is_filed_under_the_requirement_it_targets() -> None:
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match(
        [_requirement("R1", "Production Go")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )
    tailor = TailorResult(
        match_id="m1",
        bullets=[
            TailoredBullet(
                source_line_ids=["L1"],
                original="Built payment services in Go.",
                suggestion="Built production payment services in Go.",
                targets=["R1"],
            )
        ],
    )
    brief = interview_brief(cv, match, tailor=tailor)

    claim = brief.proved[0].claims[0]
    assert claim.source == "bullet"
    assert claim.text == "Built production payment services in Go."
    assert brief.loose_claims == []


def test_a_dropped_suggestion_was_never_sent_so_it_is_not_a_claim() -> None:
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match(
        [_requirement("R1", "Production Go")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )
    tailor = TailorResult(
        match_id="m1",
        bullets=[
            TailoredBullet(
                source_line_ids=["L1"],
                original="Built payment services in Go.",
                suggestion=None,
                targets=["R1"],
                dropped_reason="unsupported_claims",
            )
        ],
    )
    brief = interview_brief(cv, match, tailor=tailor)
    assert brief.proved[0].claims == []
    assert brief.loose_claims == []


def test_a_letter_paragraph_is_filed_by_the_lines_it_cites() -> None:
    cv = _cv(
        _line("L1", "Built payment services in Go."),
        _line("L2", "Led a team of 4 engineers."),
    )
    match = _match(
        [_requirement("R1", "Production Go"), _requirement("R2", "Leading a team")],
        [
            Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why=""),
            Evidence(requirement_id="R2", status="strong", line_ids=["L2"], why=""),
        ],
    )
    letter = LetterResult(
        match_id="m1",
        tone="plain",
        paragraphs=[
            LetterParagraph(text="I built the Go services and led the team.", line_ids=["L1", "L2"])
        ],
    )
    brief = interview_brief(cv, match, letter=letter)

    assert [item.claims[0].source for item in brief.proved] == ["letter", "letter"]
    assert brief.loose_claims == []


def test_a_paragraph_that_backs_nothing_is_still_reported() -> None:
    """It was sent. A brief that hid it would understate what was said."""
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match(
        [_requirement("R1", "Production Go")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )
    letter = LetterResult(
        match_id="m1",
        tone="plain",
        paragraphs=[LetterParagraph(text="Thank you for your time.", line_ids=[])],
    )
    brief = interview_brief(cv, match, letter=letter)

    assert brief.proved[0].claims == []
    assert [claim.text for claim in brief.loose_claims] == ["Thank you for your time."]


def test_claims_are_capped_per_requirement() -> None:
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match(
        [_requirement("R1", "Production Go")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )
    tailor = TailorResult(
        match_id="m1",
        bullets=[
            TailoredBullet(
                source_line_ids=["L1"],
                original="Built payment services in Go.",
                suggestion=f"Variant {index}",
                targets=["R1"],
            )
            for index in range(MAX_CLAIMS + 3)
        ],
    )
    assert len(interview_brief(cv, match, tailor=tailor).proved[0].claims) == MAX_CLAIMS


# ─── The document the interviewer is holding ──────────────────────────


def test_a_cv_that_moved_since_the_application_is_reported_not_refused() -> None:
    """Answering a gap question moves the hash. That must not lock the brief."""
    cv = _cv(_line("L1", "Built payment services in Go."), hash_="cv-2")
    match = _match(
        [_requirement("R1", "Production Go")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
        cv_hash="cv-1",
    )
    brief = interview_brief(cv, match)

    assert brief.cv_changed is True
    assert brief.cv_hash == "cv-2"
    assert len(brief.proved) == 1


def test_an_unchanged_cv_says_so() -> None:
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match(
        [_requirement("R1", "Production Go")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )
    assert interview_brief(cv, match).cv_changed is False


# ─── Bounds ───────────────────────────────────────────────────────────


def test_both_halves_are_capped() -> None:
    cv = _cv(_line("L1", "Built payment services in Go."))
    requirements = [_requirement(f"R{index}", f"Thing {index}") for index in range(40)]
    evidence = [
        Evidence(
            requirement_id=requirement.id,
            status="strong" if index % 2 else "missing",
            line_ids=["L1"] if index % 2 else [],
            why="",
        )
        for index, requirement in enumerate(requirements)
    ]
    brief = interview_brief(cv, _match(requirements, evidence))

    assert len(brief.risks) == MAX_RISKS
    assert len(brief.proved) == MAX_PROVED


def test_a_match_with_no_requirements_is_an_empty_brief_not_a_crash() -> None:
    brief = interview_brief(_cv(_line("L1", "Anything at all.")), _match([], []))
    assert brief.risks == []
    assert brief.proved == []
    assert brief.loose_claims == []


# ─── When the user says the match got it wrong ────────────────────────
#
# The app's verdict and the candidate's are never the same thing, and this is
# the screen where that distinction has to survive into the room. An assertion
# is admissible — it is their career — but it is the one claim on the brief
# that nobody except the candidate has agreed with.


def test_an_asserted_requirement_is_named_as_the_candidates_own_claim() -> None:
    cv = _cv(
        _line("L1", "Backend Engineer, Volta Systems, 2019-2023"),
        _line("L2", "Ran the nightly batch on our own scheduler."),
    )
    match = _match(
        [_requirement("R1", "Job scheduling at scale")],
        [Evidence(requirement_id="R1", status="missing", line_ids=[], why="")],
    )

    brief = interview_brief(
        cv, match, assertions=[Assertion(requirement_id="R1", line_ids=["L2"])]
    )

    item = next(row for row in brief.risks if row.requirement_id == "R1")
    assert item.risk == "self_asserted"
    assert item.line_ids == ["L2"]


def test_an_assertion_never_reaches_the_proved_half() -> None:
    """A line only the candidate says counts is not a receipt."""
    cv = _cv(_line("L1", "Ran the nightly batch on our own scheduler."))
    match = _match(
        [_requirement("R1", "Job scheduling at scale")],
        [Evidence(requirement_id="R1", status="missing", line_ids=[], why="")],
    )

    brief = interview_brief(
        cv, match, assertions=[Assertion(requirement_id="R1", line_ids=["L1"])]
    )

    assert brief.proved == []
    assert [row.risk for row in brief.risks] == ["self_asserted"]


def test_an_assertion_ranks_above_everything_but_having_nothing() -> None:
    cv = _cv(
        _line("L1", "Kafka", section="skills"),
        _line("L2", "Ran the nightly batch on our own scheduler."),
    )
    match = _match(
        [
            _requirement("R1", "Kafka in production"),
            _requirement("R2", "Terraform"),
            _requirement("R3", "Job scheduling at scale"),
        ],
        [
            Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why=""),
            Evidence(requirement_id="R2", status="missing", line_ids=[], why=""),
            Evidence(requirement_id="R3", status="missing", line_ids=[], why=""),
        ],
    )

    brief = interview_brief(
        cv, match, assertions=[Assertion(requirement_id="R3", line_ids=["L2"])]
    )

    assert [row.risk for row in brief.risks] == [
        "no_evidence",
        "self_asserted",
        "listed_not_shown",
    ]


def test_an_assertion_pointing_at_a_line_that_is_gone_is_dropped() -> None:
    """The CV moved under it, and a citation nobody can follow is not one."""
    cv = _cv(_line("L1", "Ran the nightly batch on our own scheduler."))
    match = _match(
        [_requirement("R1", "Job scheduling at scale")],
        [Evidence(requirement_id="R1", status="missing", line_ids=[], why="")],
    )

    brief = interview_brief(
        cv, match, assertions=[Assertion(requirement_id="R1", line_ids=["L99"])]
    )

    item = next(row for row in brief.risks if row.requirement_id == "R1")
    assert item.risk == "no_evidence"
    assert item.line_ids == []


def test_a_brief_without_assertions_is_unchanged() -> None:
    cv = _cv(_line("L1", "Built payment services in Go."))
    match = _match(
        [_requirement("R1", "Go in production")],
        [Evidence(requirement_id="R1", status="strong", line_ids=["L1"], why="")],
    )

    assert interview_brief(cv, match) == interview_brief(cv, match, assertions=[])
