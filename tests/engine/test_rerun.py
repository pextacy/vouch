"""Two runs of one posting: what moved, and who gets the credit.

This is the screen the whole answer loop points at, which makes its failures
the ones a user would feel most. Claiming a gap closed when it did not would
be the app congratulating someone into an interview they are not ready for.
Taking credit for a gain the user's own sentence did not cause would be the
same fabrication this product refuses, wearing a friendlier face. And hiding a
requirement that lost its evidence would make the screen a congratulation
rather than a record.

The lining-up is the hard part and is tested first: requirements are
re-extracted on every run, so `R3` in one run is not `R3` in the other, and
the two lists can be different lengths.

No model is involved anywhere in this file.
"""

from __future__ import annotations

from receipts_engine.rerun import MAX_ITEMS, compare_runs
from receipts_engine.schemas import (
    CVDoc,
    CVLine,
    Evidence,
    MatchResult,
    MatchSummary,
    PostingMeta,
    Requirement,
)

FIRST_RUN = "2026-09-10T09:00:00+00:00"
SECOND_RUN = "2026-09-24T09:00:00+00:00"


def _cv(*added: CVLine) -> CVDoc:
    return CVDoc(
        hash="h~e2",
        detected_language="en",
        lines=[
            CVLine(id="L2", text="Built payment services in Go at Northwind", section="experience"),
            *added,
        ],
    )


def _run(
    id_: str,
    created_at: str,
    *requirements: tuple[str, str, str, list[str]],
) -> MatchResult:
    """``requirements`` is (text, kind, status, line_ids)."""
    strong = sum(1 for _, _, status, _ in requirements if status == "strong")
    return MatchResult(
        id=id_,
        created_at=created_at,
        cv_hash="h",
        posting=PostingMeta(hash="p1", language="en", title="Backend Engineer"),
        requirements=[
            Requirement(id=f"R{index + 1}", text=text, kind=kind, category="skill", source_quote=text[:40])  # type: ignore[arg-type]
            for index, (text, kind, _, _) in enumerate(requirements)
        ],
        evidence=[
            Evidence(requirement_id=f"R{index + 1}", status=status, line_ids=lines, why="")  # type: ignore[arg-type]
            for index, (_, _, status, lines) in enumerate(requirements)
        ],
        summary=MatchSummary(
            total=len(requirements),
            strong=strong,
            partial=0,
            missing=len(requirements) - strong,
            must_missing=0,
            sentence="",
        ),
    )


def _surfaces(changes: list) -> list[str]:
    return [change.surface for change in changes]


# ─── Lining up two readings of one posting ────────────────────────────


def test_the_same_demand_worded_differently_is_one_row() -> None:
    """`R1` in one run is not `R1` in the other; the lexicon is what joins them."""
    diff = compare_runs(
        _cv(),
        _run(
            "m1",
            FIRST_RUN,
            ("Experience running services on Kubernetes", "must", "missing", []),
            ("Backend engineering", "must", "strong", ["L2"]),
        ),
        _run(
            "m2",
            SECOND_RUN,
            ("Backend engineering", "must", "strong", ["L2"]),
            ("Kubernetes in production", "must", "strong", ["L2"]),
        ),
    )

    assert _surfaces(diff.gained) == ["Kubernetes"]
    assert diff.gained[0].before == "missing"
    assert diff.gained[0].after == "strong"
    # And the wordings it joined are on the row, so the pairing can be argued
    # with rather than trusted.
    assert len(diff.gained[0].texts) == 1


def test_a_term_only_one_run_asked_about_is_neither_a_gain_nor_a_loss() -> None:
    diff = compare_runs(
        _cv(),
        _run("m1", FIRST_RUN, ("Kubernetes in production", "must", "missing", [])),
        _run("m2", SECOND_RUN, ("Terraform familiarity", "nice", "missing", [])),
    )

    assert diff.gained == []
    assert diff.lost == []
    assert sorted(_surfaces(diff.differed)) == ["Kubernetes", "Terraform"]
    assert {change.direction for change in diff.differed} == {"new_ask", "dropped_ask"}


def test_asked_twice_and_proved_once_reads_as_proved() -> None:
    """The same rule the match map reads: the best verdict any wording got."""
    diff = compare_runs(
        _cv(),
        _run("m1", FIRST_RUN, ("Kubernetes in production", "must", "missing", [])),
        _run(
            "m2",
            SECOND_RUN,
            ("Kubernetes in production", "must", "missing", []),
            ("Kubernetes and Helm", "nice", "strong", ["L2"]),
        ),
    )

    assert _surfaces(diff.gained) == ["Kubernetes"]


# ─── Credit, and the refusal to take it ───────────────────────────────


def test_a_gain_standing_on_a_line_written_since_is_credited() -> None:
    written = CVLine(
        id="L9",
        text="Owned the Kafka consumer rewrite at Northwind.",
        section="experience",
        added_at="2026-09-18T10:00:00Z",
    )
    diff = compare_runs(
        _cv(written),
        _run("m1", FIRST_RUN, ("Production experience with Kafka", "must", "missing", [])),
        _run("m2", SECOND_RUN, ("Kafka in production", "must", "strong", ["L9"])),
    )

    assert diff.gained[0].credited is True
    assert diff.gained[0].line_ids == ["L9"]
    assert diff.added_between == ["L9"]


def test_a_gain_the_users_sentence_did_not_cause_takes_no_credit() -> None:
    """It moved for a reason this comparison cannot see, so it says nothing."""
    written = CVLine(
        id="L9",
        text="Ran a reading group",
        section="experience",
        added_at="2026-09-18T10:00:00Z",
    )
    diff = compare_runs(
        _cv(written),
        _run("m1", FIRST_RUN, ("Backend engineering in production", "must", "missing", [])),
        _run("m2", SECOND_RUN, ("Backend engineering in production", "must", "strong", ["L2"])),
    )

    assert diff.gained[0].credited is False


def test_a_line_that_was_already_there_never_earns_credit() -> None:
    old = CVLine(
        id="L9",
        text="Owned the Kafka consumer rewrite.",
        section="experience",
        added_at="2026-09-01T10:00:00Z",
    )
    diff = compare_runs(
        _cv(old),
        _run("m1", FIRST_RUN, ("Kafka in production", "must", "missing", [])),
        _run("m2", SECOND_RUN, ("Kafka in production", "must", "strong", ["L9"])),
    )

    assert diff.added_between == []
    assert diff.gained[0].credited is False


# ─── The other direction, and the rest ────────────────────────────────


def test_evidence_that_went_the_other_way_is_reported() -> None:
    diff = compare_runs(
        _cv(),
        _run("m1", FIRST_RUN, ("Kubernetes in production", "must", "strong", ["L2"])),
        _run("m2", SECOND_RUN, ("Kubernetes in production", "must", "missing", [])),
    )

    assert _surfaces(diff.lost) == ["Kubernetes"]
    assert diff.gained == []


def test_what_is_still_unproved_is_kept_separate_from_what_moved() -> None:
    diff = compare_runs(
        _cv(),
        _run("m1", FIRST_RUN, ("Kubernetes in production", "must", "missing", [])),
        _run("m2", SECOND_RUN, ("Kubernetes and Helm", "must", "missing", [])),
    )

    assert _surfaces(diff.still) == ["Kubernetes"]
    assert diff.gained == [] and diff.lost == []


def test_a_requirement_still_proved_in_both_runs_is_not_news() -> None:
    diff = compare_runs(
        _cv(),
        _run("m1", FIRST_RUN, ("Kubernetes in production", "must", "strong", ["L2"])),
        _run("m2", SECOND_RUN, ("Kubernetes in production", "must", "strong", ["L2"])),
    )

    assert (diff.gained, diff.lost, diff.still, diff.differed) == ([], [], [], [])


def test_both_summaries_are_quoted_rather_than_recomputed() -> None:
    """The totals can differ — the posting is re-read — and that is the point."""
    diff = compare_runs(
        _cv(),
        _run("m1", FIRST_RUN, ("Kubernetes in production", "must", "missing", [])),
        _run(
            "m2",
            SECOND_RUN,
            ("Kubernetes in production", "must", "strong", ["L2"]),
            ("Terraform familiarity", "nice", "missing", []),
        ),
    )

    assert (diff.before_strong, diff.before_total) == (0, 1)
    assert (diff.after_strong, diff.after_total) == (1, 2)
    assert diff.days_between == 14


def test_must_haves_and_earned_gains_come_first() -> None:
    written = CVLine(id="L9", text="Owned the Kafka rewrite.", section="experience", added_at="2026-09-18T10:00:00Z")
    diff = compare_runs(
        _cv(written),
        _run(
            "m1",
            FIRST_RUN,
            ("Terraform familiarity", "nice", "missing", []),
            ("Kafka in production", "must", "missing", []),
        ),
        _run(
            "m2",
            SECOND_RUN,
            ("Terraform familiarity", "nice", "strong", ["L2"]),
            ("Kafka in production", "must", "strong", ["L9"]),
        ),
    )

    assert _surfaces(diff.gained) == ["Kafka", "Terraform"]
    assert MAX_ITEMS >= 2


def test_an_unreadable_date_leaves_the_gap_unstated() -> None:
    diff = compare_runs(
        _cv(),
        _run("m1", "whenever", ("Kafka in production", "must", "missing", [])),
        _run("m2", SECOND_RUN, ("Kafka in production", "must", "strong", ["L2"])),
    )

    assert diff.days_between is None
    # Without a boundary nothing can be shown to have arrived after it.
    assert diff.gained[0].credited is False
