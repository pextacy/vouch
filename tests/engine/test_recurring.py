"""Recurring gaps: the denominator, and the refusal to see a pattern in two points.

This report tells someone what to go and learn, so its failure modes are
expensive in a particular way. Calling a strength a weakness — because the
count of unproven answers was read without the count of times it was asked —
would send a person to study the thing they are already best at. And declaring
a trend from a single application would be the app overclaiming from thin data,
which is the same sin as an invented CV bullet wearing a different hat.

No model is involved anywhere in this file.
"""

from __future__ import annotations

from receipts_engine.recurring import (
    MAX_GROUPS,
    MIN_MATCHES,
    MIN_OCCURRENCES,
    recurring_gaps,
)
from receipts_engine.schemas import RecurringInput


def _item(match: str, text: str, status: str = "missing", kind: str = "must") -> RecurringInput:
    return RecurringInput(
        id=f"{match}#{abs(hash(text)) % 9999}",
        match=match,
        text=text,
        kind=kind,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )


def _keys(groups: list) -> list[str]:
    return [g.key for g in groups]


# ─── Too little data is an answer, not a pattern ──────────────────────


def test_two_applications_are_not_a_trend() -> None:
    result = recurring_gaps(
        [
            _item("m1", "Kubernetes in production"),
            _item("m2", "Experience running services on Kubernetes"),
        ]
    )
    assert result.groups == []
    assert result.matches == 2
    assert MIN_MATCHES == 3


def test_nothing_at_all_is_handled() -> None:
    result = recurring_gaps([])
    assert result.matches == 0
    assert result.groups == []
    assert result.strengths == []


def test_a_gap_that_happened_once_is_not_reported() -> None:
    result = recurring_gaps(
        [
            _item("m1", "Kubernetes in production"),
            _item("m2", "Go experience", status="strong"),
            _item("m3", "Go experience", status="strong"),
        ]
    )
    assert _keys(result.groups) == []
    assert MIN_OCCURRENCES == 2


# ─── The denominator ──────────────────────────────────────────────────


def test_a_skill_asked_for_repeatedly_and_never_proved_is_the_headline() -> None:
    result = recurring_gaps(
        [
            _item("m1", "Kubernetes in production"),
            _item("m2", "Experience running services on Kubernetes"),
            _item("m3", "Kubernetes and Helm"),
        ]
    )
    assert _keys(result.groups) == ["kubernetes"]
    group = result.groups[0]
    assert (group.asked, group.unproven, group.must) == (3, 3, 3)
    assert group.surface == "Kubernetes"
    assert len(group.texts) == 3, "the screen shows what was merged"


def test_a_skill_mostly_proved_is_never_called_a_gap() -> None:
    """The failure that would send someone to study their own best skill.

    Read without the denominator this is "Terraform came back unproven twice" —
    a recurring gap. Read with it, it is a skill proved in four applications
    out of six, which is a strength with two ragged edges.
    """
    items = [_item(f"m{n}", "Terraform experience", status="strong") for n in range(1, 5)]
    items += [_item("m5", "Terraform experience"), _item("m6", "Terraform experience")]
    result = recurring_gaps(items)
    assert _keys(result.groups) == []
    assert _keys(result.strengths) == [], "not a clean strength either — it has misses"


def test_a_skill_always_proved_is_reported_as_a_strength() -> None:
    """A report that is only a list of failures stops being read."""
    result = recurring_gaps(
        [
            _item("m1", "Terraform experience", status="strong"),
            _item("m2", "Deep Terraform background", status="strong"),
            _item("m3", "Kubernetes in production"),
            _item("m4", "Kubernetes in production"),
        ]
    )
    assert _keys(result.strengths) == ["terraform"]
    assert result.strengths[0].asked == 2
    assert result.strengths[0].unproven == 0
    assert _keys(result.groups) == ["kubernetes"]


def test_partial_counts_as_unproven() -> None:
    """"Related" is not evidence — the match map already says so."""
    result = recurring_gaps(
        [
            _item("m1", "Kubernetes in production", status="partial"),
            _item("m2", "Kubernetes in production", status="partial"),
            _item("m3", "Go experience", status="strong"),
        ]
    )
    assert _keys(result.groups) == ["kubernetes"]
    assert result.groups[0].unproven == 2


def test_one_posting_asking_twice_counts_as_one_application() -> None:
    """`match` is counted, not the bullet points inside it."""
    result = recurring_gaps(
        [
            _item("m1", "Kubernetes in production"),
            _item("m1", "Experience with Kubernetes operators"),
            _item("m2", "Kubernetes and Helm"),
            _item("m3", "Go experience", status="strong"),
        ]
    )
    group = next(g for g in result.groups if g.key == "kubernetes")
    assert group.asked == 2, "two applications asked, not three requirements"
    assert len(group.ids) == 3, "but every member is still addressable"


# ─── Grouping is conservative ─────────────────────────────────────────


def test_a_requirement_naming_two_tools_counts_for_both() -> None:
    """An application asking for Terraform *and* Kubernetes asked for each."""
    result = recurring_gaps(
        [
            _item("m1", "Terraform and Kubernetes in production"),
            _item("m2", "Terraform and Kubernetes in production"),
            _item("m3", "Something else entirely"),
        ]
    )
    assert set(_keys(result.groups)) == {"terraform", "kubernetes"}


def test_an_ambiguous_tool_name_groups_by_wording_instead() -> None:
    """A known limit, inherited from the lexicon on purpose.

    "Go", "R", "Rest" and "Swift" are tools and ordinary words at once, so
    `AMBIGUOUS_SPELLINGS` makes the lexicon skip them as bare one-word matches
    — that is what stops "Shipped Go" being read as the language. Here the cost
    is that "Go experience" and "Strong Golang background" do not merge.

    Working around it would mean guessing from capitalisation, and a sentence
    starts with a capital: the same trap the verifier documents in `docs.md §6`.
    So the fallback takes it — identical wordings still group, which is the
    conservative answer rather than a wrong merge.
    """
    result = recurring_gaps(
        [
            _item("m1", "Go experience"),
            _item("m2", "Go experience"),
            _item("m3", "Strong Golang background"),
        ]
    )
    assert _keys(result.groups) == ["text:go experience"]
    assert result.groups[0].asked == 2


def test_wording_the_lexicon_does_not_know_groups_only_on_an_exact_match() -> None:
    """No fuzzy merging: a wrong merge is invisible, a split is only untidy."""
    result = recurring_gaps(
        [
            _item("m1", "Willingness to travel monthly"),
            _item("m2", "Willingness to travel monthly"),
            _item("m3", "Happy to travel now and then"),
        ]
    )
    assert _keys(result.groups) == ["text:willingness to travel monthly"]
    assert result.groups[0].asked == 2
    assert result.groups[0].surface == "Willingness to travel monthly"


def test_every_group_has_a_surface() -> None:
    """The UI renders it unconditionally; an empty one is a blank heading."""
    result = recurring_gaps(
        [
            _item("m1", "Kubernetes in production"),
            _item("m2", "Willingness to travel monthly"),
            _item("m3", "Kubernetes and Helm"),
            _item("m4", "Willingness to travel monthly"),
        ]
    )
    assert result.groups
    assert all(group.surface for group in result.groups)


# ─── Ranking and bounds ───────────────────────────────────────────────


def test_must_haves_rank_above_nice_to_haves() -> None:
    items = [
        _item(f"m{n}", "Rust experience", kind="nice") for n in range(1, 6)
    ] + [_item(f"m{n}", "Kubernetes in production", kind="must") for n in range(1, 4)]
    result = recurring_gaps(items)
    assert _keys(result.groups)[0] == "kubernetes", "a must-have decides whether to apply"
    assert result.groups[0].asked < result.groups[1].asked


def test_the_report_is_bounded() -> None:
    items = []
    for n in range(1, 31):
        for match in ("m1", "m2", "m3"):
            items.append(_item(match, f"Skill number {n} required"))
    result = recurring_gaps(items)
    assert len(result.groups) == MAX_GROUPS


def test_ids_come_back_so_the_caller_can_map_home() -> None:
    """`match` and `id` are opaque here — the UI maps them to its own records."""
    first = _item("m1", "Kubernetes in production")
    second = _item("m2", "Kubernetes and Helm")
    result = recurring_gaps([first, second, _item("m3", "Go", status="strong")])
    assert set(result.groups[0].ids) == {first.id, second.id}
