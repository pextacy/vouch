"""The whole shelf, asked the question `since.py` asks about one application.

A row on this screen sends someone to spend a model call and a few minutes, so
the two ways of being wrong are the same two, at thirty times the volume.
Naming an application whose CV line was already in front of the match when it
ran would send them to re-run something that cannot move. And matching on a
word two sentences happen to share would do it for a sentence that has nothing
to do with the posting.

The sharing with `since.naming_lines` is deliberate and tested from both
sides: the screen that says "worth reopening" and the screen the user lands on
when they do must never disagree about what counts as naming something.

No model is involved anywhere in this file.
"""

from __future__ import annotations

from receipts_engine.schemas import CVDoc, CVLine, RecurringInput
from receipts_engine.worth import MAX_ROWS, worth_rerunning

SENT_EARLY = "2026-09-10T09:00:00+00:00"
SENT_LATE = "2026-09-22T09:00:00+00:00"
WRITTEN = "2026-09-20T10:00:00Z"


def _cv(*added: CVLine) -> CVDoc:
    return CVDoc(
        hash="h~e1",
        detected_language="en",
        lines=[
            CVLine(id="L2", text="Built payment services in Go at Northwind", section="experience"),
            *added,
        ],
    )


def _written(id_: str, text: str, at: str = WRITTEN) -> CVLine:
    return CVLine(id=id_, text=text, section="experience", added_at=at)


def _item(
    match: str,
    text: str,
    *,
    kind: str = "must",
    status: str = "missing",
    created_at: str = SENT_EARLY,
) -> RecurringInput:
    return RecurringInput(
        id=f"{match}#{abs(hash(text)) % 9999}",
        match=match,
        text=text,
        kind=kind,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
    )


KAFKA = "Owned the Kafka consumer rewrite at Northwind"


# ─── What counts as worth reopening ───────────────────────────────────


def test_an_application_the_cv_has_since_answered_is_named() -> None:
    result = worth_rerunning(
        _cv(_written("L9", KAFKA)),
        [
            _item("m1", "Production experience with Kafka"),
            _item("m1", "Go experience", status="strong"),
        ],
    )

    assert [item.match for item in result.items] == ["m1"]
    row = result.items[0]
    assert row.terms == ["Kafka"]
    assert row.line_ids == ["L9"]
    assert (row.requirements, row.must) == (1, 1)
    # The denominator: one of the one thing it could not show.
    assert row.unproved == 1
    assert (result.applications, result.written) == (1, 1)


def test_a_line_the_application_already_read_changes_nothing() -> None:
    """It was in front of that match when it ran, and the match ruled on it."""
    result = worth_rerunning(
        _cv(_written("L9", KAFKA, at="2026-09-01T10:00:00Z")),
        [_item("m1", "Production experience with Kafka")],
    )

    assert result.items == []
    assert result.applications == 1


def test_an_application_sent_after_the_line_was_written_is_left_alone() -> None:
    result = worth_rerunning(
        _cv(_written("L9", KAFKA)),
        [_item("m2", "Kafka in production", created_at=SENT_LATE)],
    )

    assert result.items == []


def test_an_application_with_nothing_unproved_is_never_listed() -> None:
    result = worth_rerunning(
        _cv(_written("L9", KAFKA)),
        [_item("m3", "Kafka in production", status="strong")],
    )

    assert result.items == []
    assert result.applications == 1, "still read, just not worth reopening"


def test_a_partial_verdict_counts_as_room_to_improve() -> None:
    result = worth_rerunning(
        _cv(_written("L9", KAFKA)),
        [_item("m1", "Kafka in production", status="partial")],
    )

    assert [item.match for item in result.items] == ["m1"]


def test_a_requirement_with_no_lexicon_term_never_lights_up() -> None:
    result = worth_rerunning(
        _cv(_written("L9", "Ran a reading group about good engineering")),
        [_item("m1", "A good sense of humour", kind="nice")],
    )

    assert result.items == []


def test_an_application_with_an_unreadable_date_is_not_guessed_at() -> None:
    # Without a date there is no "after", and the whole claim of a row here is
    # that the sentence arrived after the application went out.
    result = worth_rerunning(
        _cv(_written("L9", KAFKA)),
        [_item("m1", "Kafka in production", created_at="whenever")],
    )

    assert result.items == []
    assert result.applications == 1


def test_nothing_written_means_nothing_to_check() -> None:
    result = worth_rerunning(_cv(), [_item("m1", "Kafka in production")])

    assert result.items == []
    # The screen says something different in this case: there is nothing new
    # to check against yet, and answering a gap question is what starts it.
    assert result.written == 0


# ─── The order, and the limits ────────────────────────────────────────


def test_must_haves_decide_the_order() -> None:
    result = worth_rerunning(
        _cv(_written("L9", "Owned the Kafka rewrite and ran Terraform for staging")),
        [
            _item("m1", "Terraform familiarity", kind="nice"),
            _item("m2", "Kafka in production", kind="must"),
        ],
    )

    assert [item.match for item in result.items] == ["m2", "m1"]


def test_more_newly_named_requirements_comes_next() -> None:
    result = worth_rerunning(
        _cv(_written("L9", "Owned the Kafka rewrite and ran Terraform for staging")),
        [
            _item("m1", "Kafka in production"),
            _item("m2", "Kafka in production"),
            _item("m2", "Terraform for infrastructure"),
        ],
    )

    assert [item.match for item in result.items] == ["m2", "m1"]
    assert result.items[0].requirements == 2


def test_the_list_is_capped_and_the_denominator_is_not() -> None:
    line = _written("L9", KAFKA)
    items = [_item(f"m{n}", "Kafka in production") for n in range(20)]

    result = worth_rerunning(_cv(line), items)

    assert len(result.items) == MAX_ROWS
    assert result.applications == 20, "the screen can still say 10 of 20"


def test_one_row_per_application_however_many_requirements_it_names() -> None:
    result = worth_rerunning(
        _cv(_written("L9", "Owned the Kafka rewrite and ran Terraform for staging")),
        [
            _item("m1", "Kafka in production"),
            _item("m1", "Event streaming with Kafka"),
            _item("m1", "Terraform for infrastructure", kind="nice"),
        ],
    )

    assert len(result.items) == 1
    row = result.items[0]
    assert (row.requirements, row.must, row.unproved) == (3, 2, 3)
    assert row.line_ids == ["L9"], "one line, named once"
    assert sorted(row.terms) == ["Kafka", "Terraform"]
