"""What changed since the application went out — and the care around "changed".

This is the screen that tells someone an application is worth running again,
so its two ways of being wrong both cost the user something real. Reporting a
line that was already in the CV when the match ran would send them back to
re-run an application over evidence the match had already seen and rejected.
And matching on a coincidence of wording would do the same for a sentence that
has nothing to do with what the posting asked for.

The module is also the app's only date arithmetic, and the two halves of the
product write their timestamps differently — `Date.toISOString()` in the UI
and `datetime.isoformat()` in the engine — so the parsing is tested rather
than assumed.

No model is involved anywhere in this file.
"""

from __future__ import annotations

from datetime import UTC, datetime

from receipts_engine.schemas import (
    CVDoc,
    CVLine,
    Evidence,
    MatchResult,
    MatchSummary,
    PostingMeta,
    Requirement,
)
from receipts_engine.since import MAX_ANSWERS, since_applied

SENT = "2026-09-12T09:00:00Z"
NOW = datetime(2026, 9, 23, tzinfo=UTC)


def _cv(*added: CVLine, hash_: str = "h2") -> CVDoc:
    return CVDoc(
        hash=hash_,
        detected_language="en",
        lines=[
            CVLine(id="L1", text="Ada Lovelace", section="header"),
            CVLine(id="L2", text="Built payment services in Go at Northwind", section="experience"),
            *added,
        ],
    )


def _added(id_: str, text: str, at: str) -> CVLine:
    return CVLine(id=id_, text=text, section="experience", added_at=at)


def _match(
    *requirements: tuple[str, str, str, str],
    created_at: str = "2026-09-10T09:00:00+00:00",
    cv_hash: str = "h1",
) -> MatchResult:
    """``requirements`` is (id, text, kind, status)."""
    return MatchResult(
        id="m1",
        created_at=created_at,
        cv_hash=cv_hash,
        posting=PostingMeta(hash="p1", language="en", title="Backend Engineer"),
        requirements=[
            Requirement(id=rid, text=text, kind=kind, category="skill", source_quote=text[:40])  # type: ignore[arg-type]
            for rid, text, kind, _ in requirements
        ],
        evidence=[
            Evidence(requirement_id=rid, status=status, line_ids=[], why="")  # type: ignore[arg-type]
            for rid, _, _, status in requirements
        ],
        summary=MatchSummary(total=len(requirements), strong=0, partial=0, missing=0, must_missing=0, sentence=""),
    )


KAFKA = ("R1", "Production experience with Kafka", "must", "missing")


# ─── Only what arrived after the envelope ─────────────────────────────


def test_a_line_added_since_names_what_the_application_could_not_show() -> None:
    result = since_applied(
        _cv(_added("L3", "Owned the Kafka consumer rewrite, 2023", "2026-09-20T10:00:00Z")),
        _match(KAFKA),
        sent_at=SENT,
        now=NOW,
    )

    assert [answer.requirement_id for answer in result.answers] == ["R1"]
    answer = result.answers[0]
    assert answer.line_ids == ["L3"]
    # The CV's own spelling, because it is the user's sentence being quoted.
    assert answer.terms == ["Kafka"]
    assert answer.status == "missing"


def test_a_line_that_was_already_there_is_not_news() -> None:
    """The match read it and said what it said; re-running proves nothing new."""
    result = since_applied(
        _cv(_added("L3", "Owned the Kafka consumer rewrite", "2026-09-01T10:00:00Z")),
        _match(KAFKA),
        sent_at=SENT,
        now=NOW,
    )

    assert result.answers == []
    assert result.added == []


def test_a_requirement_the_application_already_proved_is_left_alone() -> None:
    result = since_applied(
        _cv(_added("L3", "More Kafka work at Northwind", "2026-09-20T10:00:00Z")),
        _match(("R1", "Production experience with Kafka", "must", "strong")),
        sent_at=SENT,
        now=NOW,
    )

    assert result.answers == []
    assert result.added == ["L3"], "the line is still new, it just changes nothing here"


def test_a_partial_verdict_counts_as_something_to_improve() -> None:
    result = since_applied(
        _cv(_added("L3", "Ran Kafka consumers in production", "2026-09-20T10:00:00Z")),
        _match(("R1", "Kafka in production", "nice", "partial")),
        sent_at=SENT,
        now=NOW,
    )

    assert [answer.status for answer in result.answers] == ["partial"]


def test_a_requirement_with_no_entry_at_all_counts_as_unproved() -> None:
    match = _match(KAFKA)
    match.evidence = []

    result = since_applied(
        _cv(_added("L3", "Owned the Kafka rewrite", "2026-09-20T10:00:00Z")),
        match,
        sent_at=SENT,
        now=NOW,
    )

    assert [answer.requirement_id for answer in result.answers] == ["R1"]


# ─── No hit without a term the lexicon vouches for ────────────────────


def test_a_requirement_the_lexicon_does_not_know_never_lights_up() -> None:
    """A shared ordinary word is a coincidence, and re-running costs a call."""
    result = since_applied(
        _cv(_added("L3", "Ran a reading group about good engineering", "2026-09-20T10:00:00Z")),
        _match(("R1", "A good sense of humour", "nice", "missing")),
        sent_at=SENT,
        now=NOW,
    )

    assert result.answers == []


def test_a_new_line_about_something_else_is_not_reported() -> None:
    result = since_applied(
        _cv(_added("L3", "Mentored two interns through their first release", "2026-09-20T10:00:00Z")),
        _match(KAFKA),
        sent_at=SENT,
        now=NOW,
    )

    assert result.answers == []
    assert result.added == ["L3"]


def test_must_haves_come_first() -> None:
    result = since_applied(
        _cv(_added("L3", "Kafka and Terraform work at Northwind", "2026-09-20T10:00:00Z")),
        _match(
            ("R1", "Familiarity with Terraform", "nice", "missing"),
            ("R2", "Production experience with Kafka", "must", "missing"),
        ),
        sent_at=SENT,
        now=NOW,
    )

    assert [answer.requirement_id for answer in result.answers] == ["R2", "R1"]
    assert MAX_ANSWERS >= 2


# ─── Dates, written by two different halves of the app ────────────────


def test_it_counts_from_the_day_the_user_said_they_sent_it() -> None:
    result = since_applied(_cv(), _match(KAFKA), sent_at=SENT, now=NOW)

    # Whole days elapsed, not calendar days crossed: "sent 10 days ago" is a
    # claim about time passing, and the screen's nudge leans on it.
    assert (result.days, result.dated_from) == (10, "sent")


def test_without_a_sent_date_it_counts_from_the_match_and_says_so() -> None:
    """Records written before the tracker stamped its statuses have only that."""
    result = since_applied(_cv(), _match(KAFKA), now=NOW)

    assert (result.days, result.dated_from) == (12, "checked")


def test_both_timestamp_spellings_are_read_as_instants() -> None:
    zulu = since_applied(
        _cv(_added("L3", "Kafka rewrite", "2026-09-20T10:00:00Z")),
        _match(KAFKA, created_at="2026-09-10T09:00:00+00:00"),
        sent_at="2026-09-12T09:00:00+00:00",
        now=NOW,
    )
    offset = since_applied(
        _cv(_added("L3", "Kafka rewrite", "2026-09-20T10:00:00+00:00")),
        _match(KAFKA, created_at="2026-09-10T09:00:00Z"),
        sent_at=SENT,
        now=NOW,
    )

    assert zulu.model_dump() == offset.model_dump()


def test_a_date_it_cannot_read_is_never_called_new() -> None:
    result = since_applied(
        _cv(_added("L3", "Owned the Kafka consumer rewrite", "last thursday")),
        _match(KAFKA),
        sent_at=SENT,
        now=NOW,
    )

    assert result.added == []
    assert result.answers == []


def test_an_undatable_application_reports_no_age_rather_than_a_guess() -> None:
    result = since_applied(_cv(), _match(KAFKA, created_at="whenever"), now=NOW)

    assert result.days is None


def test_the_cv_moving_is_reported_on_its_own() -> None:
    same = since_applied(_cv(hash_="h1"), _match(KAFKA, cv_hash="h1"), sent_at=SENT, now=NOW)
    moved = since_applied(_cv(hash_="h1~e2"), _match(KAFKA, cv_hash="h1"), sent_at=SENT, now=NOW)

    assert same.cv_changed is False
    assert moved.cv_changed is True
