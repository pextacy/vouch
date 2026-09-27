"""The line ledger: whose receipt is it, and how many applications is it out of.

This screen tells someone which sentences of their CV to lead with and which
have never been needed, so it is trusted with the document itself. Two failure
modes would do real damage and both are tested here.

The first is counting a citation from **another parse of the CV**. A line id is
a position, not a sentence: after a re-upload, `L12` is a different line, and
putting an old application's receipt under it would praise the wrong sentence —
or worse, send someone to cut a line that has carried five applications.

The second is calling a line idle when the ledger simply could not see its
work: a `missing` verdict cites nothing, an unknown id proves nothing, and a
header line is a phone number rather than evidence.

No model is involved anywhere in this file.
"""

from __future__ import annotations

from receipts_engine.ledger import (
    MAX_IDLE,
    MAX_WORKING,
    MIN_MATCHES,
    base_hash,
    line_ledger,
)
from receipts_engine.schemas import CVDoc, CVLine, RecurringInput

CV_HASH = "sha-of-the-parsed-cv"


def _cv(hash_: str = CV_HASH, *, extra: list[CVLine] | None = None) -> CVDoc:
    return CVDoc(
        hash=hash_,
        detected_language="en",
        lines=[
            CVLine(id="L1", text="Ada Lovelace — Istanbul", section="header"),
            CVLine(id="L2", text="Built payment services in Go at Northwind", section="experience"),
            CVLine(id="L3", text="Ran services on Kubernetes for three years", section="experience"),
            CVLine(id="L4", text="Volunteer chess coach, 2016", section="other"),
            *(extra or []),
        ],
    )


def _item(
    match: str,
    text: str,
    lines: list[str],
    *,
    status: str = "strong",
    kind: str = "must",
    cv_hash: str = CV_HASH,
) -> RecurringInput:
    return RecurringInput(
        id=f"{match}#{abs(hash(text)) % 9999}",
        match=match,
        text=text,
        kind=kind,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        line_ids=lines,  # type: ignore[arg-type]
        cv_hash=cv_hash,
    )


def _ids(lines: list) -> list[str]:
    return [line.id for line in lines]


# ─── Too little data is an answer, not a ranking ──────────────────────


def test_two_applications_do_not_rank_a_cv() -> None:
    """Two postings say which lines the last two jobs asked about, nothing more."""
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m2", "Kubernetes and Helm", ["L3"]),
        ],
    )

    assert result.applications == 2
    assert result.working == []
    assert result.idle == [], "no list at all, rather than a list drawn from two"
    assert MIN_MATCHES == 3


def test_nothing_at_all_is_handled() -> None:
    result = line_ledger(_cv(), [])

    assert (result.applications, result.cited, result.skipped) == (0, 0, 0)
    # The denominator survives an empty feed: the screen still knows how long
    # the CV is, which is what its first sentence is about.
    assert result.eligible == 3


# ─── The citations have to be about this document ─────────────────────


def test_an_application_checked_against_another_parse_is_not_counted() -> None:
    """`L3` in a re-uploaded CV is a different sentence, so its receipt is not ours."""
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m2", "Kubernetes and Helm", ["L3"]),
            _item("m3", "Go experience", ["L2"]),
            _item("old", "Kubernetes everywhere", ["L3"], cv_hash="a-different-parse"),
        ],
    )

    assert result.applications == 3, "the stranger is not in the denominator"
    assert result.skipped == 1, "and it is reported, not swallowed"
    kubernetes = next(line for line in result.working if line.id == "L3")
    assert kubernetes.applications == 2


def test_lines_added_since_the_applications_do_not_break_the_match() -> None:
    """Answering a gap moves the hash; it does not renumber a single line."""
    result = line_ledger(
        _cv(f"{CV_HASH}~e3"),
        [
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m2", "Kubernetes and Helm", ["L3"]),
            _item("m3", "Go experience", ["L2"]),
        ],
    )

    assert (result.applications, result.skipped) == (3, 0)
    assert base_hash(f"{CV_HASH}~e3") == CV_HASH


def test_an_application_from_before_the_first_edit_still_counts() -> None:
    result = line_ledger(
        _cv(f"{CV_HASH}~e1"),
        [
            _item("m1", "Kubernetes in production", ["L3"], cv_hash=f"{CV_HASH}~e1"),
            _item("m2", "Kubernetes and Helm", ["L3"], cv_hash=CV_HASH),
            _item("m3", "Go experience", ["L2"], cv_hash=f"{CV_HASH}~e9"),
        ],
    )

    assert (result.applications, result.skipped) == (3, 0)


# ─── What a line is credited with ─────────────────────────────────────


def test_the_line_that_carried_the_most_applications_comes_first() -> None:
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m1", "Go experience", ["L2"]),
            _item("m2", "Experience running services on Kubernetes", ["L3"]),
            _item("m3", "Kubernetes and Helm", ["L3"]),
        ],
    )

    assert _ids(result.working) == ["L3", "L2"]
    kubernetes = result.working[0]
    assert (kubernetes.applications, kubernetes.citations) == (3, 3)
    assert kubernetes.proves[0] == "Kubernetes", "grouped the way the other screens group"


def test_a_line_can_be_cited_twice_in_one_application() -> None:
    """Two requirements, one line: two citations, still one application."""
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m1", "Container orchestration", ["L3"], kind="nice"),
            _item("m2", "Kubernetes and Helm", ["L3"]),
            _item("m3", "Go experience", ["L2"]),
        ],
    )

    kubernetes = next(line for line in result.working if line.id == "L3")
    assert (kubernetes.applications, kubernetes.citations) == (2, 3)
    assert kubernetes.must == 2, "the nice-to-have is counted, but not as a must"


def test_the_only_line_behind_a_must_have_is_marked_decisive() -> None:
    result = line_ledger(
        _cv(),
        [
            # L3 alone answers the must-have: the application rests on it.
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m2", "Kubernetes and Helm", ["L3"]),
            # Two lines share this one, so neither is carrying it alone.
            _item("m3", "Backend services at scale", ["L2", "L3"]),
        ],
    )

    kubernetes = next(line for line in result.working if line.id == "L3")
    assert (kubernetes.must, kubernetes.decisive) == (3, 2)
    shared = next(line for line in result.working if line.id == "L2")
    assert shared.decisive == 0


def test_a_nice_to_have_is_never_decisive() -> None:
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3"], kind="nice"),
            _item("m2", "Kubernetes and Helm", ["L3"], kind="nice"),
            _item("m3", "Helm charts", ["L3"], kind="nice"),
        ],
    )

    kubernetes = result.working[0]
    assert (kubernetes.must, kubernetes.decisive) == (0, 0)


def test_a_verdict_of_missing_proves_nothing_even_if_it_cites_lines() -> None:
    """The match already said the CV does not show it; a ledger cannot overrule that."""
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3"], status="missing"),
            _item("m2", "Kubernetes and Helm", ["L3"], status="missing"),
            _item("m3", "Go experience", ["L2"]),
        ],
    )

    assert _ids(result.working) == ["L2"]
    assert "L3" in _ids(result.idle)


def test_a_citation_of_a_line_this_cv_does_not_have_is_dropped() -> None:
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3", "L99"]),
            _item("m2", "Kubernetes and Helm", ["L3"]),
            _item("m3", "Go experience", ["L2"]),
        ],
    )

    assert "L99" not in _ids(result.working)
    # And dropping it does not cost L3 the credit: it is the only line this CV
    # actually has behind that must-have.
    kubernetes = result.working[0]
    assert (kubernetes.id, kubernetes.must, kubernetes.decisive) == ("L3", 2, 2)


# ─── What has never been asked for ────────────────────────────────────


def test_an_uncited_line_is_listed_and_the_header_is_not() -> None:
    """A name and a city are not evidence, and never will be."""
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m2", "Kubernetes and Helm", ["L3"]),
            _item("m3", "Go experience", ["L2"]),
        ],
    )

    assert _ids(result.idle) == ["L4"]
    assert result.eligible == 3, "the header is not part of the count either"
    assert result.cited == 2


def test_the_lists_are_capped() -> None:
    long_cv = CVDoc(
        hash=CV_HASH,
        detected_language="en",
        lines=[
            CVLine(id=f"L{n}", text=f"Line {n}", section="experience") for n in range(1, 46)
        ],
    )
    items = [
        _item(f"m{n % 3}", f"Requirement {n}", [f"L{n}"], kind="nice")
        for n in range(1, 30)
    ]

    result = line_ledger(long_cv, items)

    assert len(result.working) == MAX_WORKING
    assert len(result.idle) == MAX_IDLE
    # Capped, but the screen can still say how many it is not showing: 45 lines
    # in the CV, 29 of them cited, so 16 idle behind a list of 12.
    assert result.eligible == 45
    assert result.cited == 29


# ─── What the user's own sentences have proved since ──────────────────


def test_a_line_the_user_added_reports_what_it_has_proved() -> None:
    added = CVLine(
        id="L5",
        text="Owned the Kafka consumer rewrite at Northwind",
        section="experience",
        added_at="2026-09-01",
    )
    result = line_ledger(
        _cv(f"{CV_HASH}~e1", extra=[added]),
        [
            _item("m1", "Kafka in production", ["L5"]),
            _item("m2", "Event streaming with Kafka", ["L5"]),
            _item("m3", "Go experience", ["L2"]),
        ],
    )

    answered = next(line for line in result.added if line.id == "L5")
    assert answered.applications == 2
    assert answered.added is True
    assert answered.proves == ["Kafka"]
    # It is in both lists on purpose: the working list ranks the whole CV, and
    # this one answers a different question — did answering that gap pay off.
    assert "L5" in _ids(result.working)


def test_an_added_line_nothing_has_asked_for_yet_is_still_reported() -> None:
    added = CVLine(id="L5", text="Ran a reading group", section="experience", added_at="2026-09-01")
    result = line_ledger(
        _cv(f"{CV_HASH}~e1", extra=[added]),
        [
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m2", "Kubernetes and Helm", ["L3"]),
            _item("m3", "Go experience", ["L2"]),
        ],
    )

    answered = next(line for line in result.added if line.id == "L5")
    assert (answered.applications, answered.citations) == (0, 0)
    assert "L5" in _ids(result.idle), "and it is honestly idle, like any other line"


def test_a_parsed_line_never_appears_as_one_the_user_added() -> None:
    result = line_ledger(
        _cv(),
        [
            _item("m1", "Kubernetes in production", ["L3"]),
            _item("m2", "Kubernetes and Helm", ["L3"]),
            _item("m3", "Go experience", ["L2"]),
        ],
    )

    assert result.added == []
    assert all(line.added is False for line in result.working + result.idle)
