"""Comparing applications: the ranking, and the silences it keeps.

This screen tells someone where to spend an evening, so the expensive failures
are the ones that sound authoritative. Ranking a posting ahead of another on a
number the user cannot check is the fit-score trap this product exists to
avoid; naming a shared gap that is only shared by two of three postings would
be the same overclaim `recurring.py` refuses.

No model is involved anywhere in this file.
"""

from __future__ import annotations

from receipts_engine.compare import (
    MAX_POSTINGS,
    MAX_TERMS,
    MIN_POSTINGS,
    compare_postings,
)
from receipts_engine.schemas import RecurringInput


def _item(
    match: str, text: str, status: str = "missing", kind: str = "must"
) -> RecurringInput:
    return RecurringInput(
        id=f"{match}#{abs(hash(text)) % 9999}",
        match=match,
        text=text,
        kind=kind,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )


def _order(result: object) -> list[str]:
    return [column.match for column in result.columns]  # type: ignore[attr-defined]


# ─── One posting is not a comparison ──────────────────────────────────


def test_a_single_application_returns_no_columns() -> None:
    result = compare_postings(
        [_item("m1", "Kubernetes in production"), _item("m1", "Go experience")]
    )
    assert result.postings == 1
    assert result.columns == []
    assert MIN_POSTINGS == 2


def test_nothing_at_all_is_handled() -> None:
    result = compare_postings([])
    assert result.postings == 0
    assert result.columns == []
    assert result.shared_gaps == []
    assert result.shared_proved == []


def test_more_postings_than_the_cap_are_dropped_whole() -> None:
    items = [
        _item(f"m{index}", "Go experience", status="strong")
        for index in range(MAX_POSTINGS + 3)
    ]
    result = compare_postings(items)
    assert result.postings == MAX_POSTINGS
    # Dropped whole, not truncated: every column still counts all of its own
    # requirements, because a column built from half a posting reports a
    # coverage number that is simply false.
    assert all(column.asked == 1 for column in result.columns)


# ─── The ranking ──────────────────────────────────────────────────────


def test_fewest_unproved_must_haves_ranks_first() -> None:
    result = compare_postings(
        [
            _item("weak", "Kubernetes in production"),
            _item("weak", "Kafka experience"),
            _item("strong", "Go experience", status="strong"),
            _item("strong", "PostgreSQL schema design", status="strong"),
        ]
    )
    assert _order(result) == ["strong", "weak"]


def test_a_tie_on_blockers_falls_to_what_is_proved() -> None:
    result = compare_postings(
        [
            _item("thin", "Go experience", status="strong"),
            _item("thin", "Docker", status="partial", kind="nice"),
            _item("rich", "Go experience", status="strong"),
            _item("rich", "PostgreSQL schema design", status="strong"),
        ]
    )
    assert _order(result) == ["rich", "thin"]


def test_an_exact_tie_keeps_the_order_the_user_picked() -> None:
    picked = [
        _item("second", "Go experience", status="strong"),
        _item("first", "Go experience", status="strong"),
    ]
    assert _order(compare_postings(picked)) == ["second", "first"]


# ─── What each column says ────────────────────────────────────────────


def test_counts_are_tallies_of_the_verdicts_that_were_sent() -> None:
    result = compare_postings(
        [
            _item("m1", "Go experience", status="strong"),
            _item("m1", "Kubernetes in production", status="partial"),
            _item("m1", "Kafka", status="missing", kind="nice"),
            _item("m2", "Go experience", status="strong"),
        ]
    )
    column = next(column for column in result.columns if column.match == "m1")
    assert (column.asked, column.proved, column.related) == (3, 1, 1)
    assert (column.must_asked, column.must_proved) == (2, 1)


def test_an_unproved_must_have_is_a_blocker_and_a_proved_one_is_not() -> None:
    result = compare_postings(
        [
            _item("m1", "Experience running services on Kubernetes"),
            _item("m1", "Go experience", status="strong"),
            _item("m2", "Go experience", status="strong"),
        ]
    )
    column = next(column for column in result.columns if column.match == "m1")
    assert any("ubernetes" in blocker for blocker in column.blockers)
    assert not any("Go" in blocker for blocker in column.blockers)


def test_a_nice_to_have_is_never_a_blocker() -> None:
    result = compare_postings(
        [
            _item("m1", "Kafka", kind="nice"),
            _item("m1", "Go experience", status="strong"),
            _item("m2", "Go experience", status="strong"),
        ]
    )
    column = next(column for column in result.columns if column.match == "m1")
    assert column.blockers == []


def test_blockers_are_capped() -> None:
    items = [_item("m1", f"Requirement number {index}") for index in range(MAX_TERMS + 4)]
    items.append(_item("m2", "Go experience", status="strong"))
    result = compare_postings(items)
    column = next(column for column in result.columns if column.match == "m1")
    assert len(column.blockers) == MAX_TERMS


def test_the_edge_is_what_this_posting_asks_for_and_another_does_not() -> None:
    result = compare_postings(
        [
            _item("m1", "Go experience", status="strong"),
            _item("m1", "PostgreSQL schema design", status="strong"),
            _item("m2", "Go experience", status="strong"),
        ]
    )
    column = next(column for column in result.columns if column.match == "m1")
    assert any("ostgre" in term.lower() for term in column.edge)
    # Both ask for Go, so proving it says nothing about which one to choose.
    assert not any(term.lower() == "go" for term in column.edge)


def test_an_edge_has_to_be_proved_not_merely_unique() -> None:
    result = compare_postings(
        [
            _item("m1", "Rust experience"),
            _item("m1", "Go experience", status="strong"),
            _item("m2", "Go experience", status="strong"),
        ]
    )
    column = next(column for column in result.columns if column.match == "m1")
    assert not any("ust" in term for term in column.edge)


# ─── What the set says ────────────────────────────────────────────────


def test_a_gap_every_posting_asks_for_and_none_proves_is_shared() -> None:
    result = compare_postings(
        [
            _item("m1", "Kubernetes in production"),
            _item("m2", "Experience running services on Kubernetes"),
            _item("m3", "Kubernetes and Helm"),
        ]
    )
    assert [group.surface for group in result.shared_gaps]
    shared = result.shared_gaps[0]
    assert shared.asked == 3
    assert shared.unproven == 3
    # The wordings it merged travel with it, so the user can disagree with the
    # grouping instead of trusting it.
    assert len(shared.texts) == 3


def test_a_gap_only_some_of_them_ask_for_is_not_shared() -> None:
    result = compare_postings(
        [
            _item("m1", "Kubernetes in production"),
            _item("m2", "Kubernetes in production"),
            _item("m3", "Go experience"),
        ]
    )
    assert result.shared_gaps == []


def test_a_mixed_record_is_reported_in_neither_list() -> None:
    result = compare_postings(
        [
            _item("m1", "Go experience", status="strong"),
            _item("m2", "Go experience", status="missing"),
        ]
    )
    assert result.shared_gaps == []
    assert result.shared_proved == []


def test_what_every_posting_asks_for_and_the_cv_proves_is_reported_too() -> None:
    result = compare_postings(
        [
            _item("m1", "Kubernetes in production", status="strong"),
            _item("m2", "Experience running services on Kubernetes", status="strong"),
        ]
    )
    assert [group.asked for group in result.shared_proved] == [2]
    assert result.shared_proved[0].unproven == 0


def test_an_ambiguous_one_word_term_does_not_merge_across_wordings() -> None:
    """The lexicon's documented limit, asserted so it stays visible.

    ``Go`` is a word before it is a language, so a bare one-word match is
    skipped and the two wordings fall back to text keys. The cost is a split
    the user can see on screen; the alternative — merging on a guess — would be
    a wrong row nobody can check, which is the trade `recurring.py` already
    made for the same reason.
    """
    result = compare_postings(
        [
            _item("m1", "Go experience", status="strong"),
            _item("m2", "Strong production experience with Go", status="strong"),
        ]
    )
    assert result.shared_proved == []
