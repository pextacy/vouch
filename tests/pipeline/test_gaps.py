"""Gap questions: what may be asked, and what may never be assumed.

The feature exists because the app used to state a gap and stop. Its whole
safety argument is that the *answer* comes from the user, so the only things
that can go wrong here are the two generated artefacts:

* a **question** that assumes an experience puts words in the candidate's
  mouth — the thing every other AI resume tool does, one layer earlier;
* an **angle** that stretches what the CV says is an ordinary fabrication and
  gets the ordinary rule.

Both directions are tested, and so is the floor: a model that returns nothing
usable must still leave the user with something to answer.
"""

from __future__ import annotations

import pytest

from receipts_engine.llm import LlmClient, TokenBudget
from receipts_engine.parse.cv import parse_cv
from receipts_engine.pipeline import plan_gaps
from receipts_engine.pipeline.gaps import DEFAULT_MAX_GAPS, HARD_MAX_GAPS
from receipts_engine.schemas import (
    CVDoc,
    Evidence,
    MatchResult,
    MatchSummary,
    PostingMeta,
    Requirement,
)

from .fake_llm import FakeSampling

CV_TEXT = "\n".join(
    [
        "Maya Collins",
        "Backend Engineer - Berlin",
        "",
        "Experience",
        "Acme Payments - Backend Engineer, 2018-2024",
        "Built payment reconciliation services in Go for 1,200 merchant accounts.",
        "Migrated the reporting pipeline from MySQL to PostgreSQL with zero downtime.",
        "Led a team of 4 engineers and owned the on-call rotation.",
        "",
        "Education",
        "MSc Computer Science, University of Edinburgh, 2016",
    ]
)


def _client(sampling: FakeSampling) -> LlmClient:
    return LlmClient(sampling, TokenBudget())  # type: ignore[arg-type]


@pytest.fixture
def cv() -> CVDoc:
    return parse_cv(source="text", text=CV_TEXT)


def _match(cv: CVDoc, *specs: tuple[str, str, str, str]) -> MatchResult:
    """Build a match from ``(id, kind, status, text)`` tuples."""
    requirements = [
        Requirement(id=rid, text=text, kind=kind, category="skill", source_quote="")  # type: ignore[arg-type]
        for rid, kind, _status, text in specs
    ]
    evidence = [
        Evidence(requirement_id=rid, status=status, line_ids=[], why="")  # type: ignore[arg-type]
        for rid, _kind, status, _text in specs
    ]
    strong = sum(1 for _, _, status, _ in specs if status == "strong")
    partial = sum(1 for _, _, status, _ in specs if status == "partial")
    missing = sum(1 for _, _, status, _ in specs if status == "missing")
    return MatchResult(
        id="match-1",
        created_at="2026-09-19T10:00:00+00:00",
        posting=PostingMeta(title="Backend Engineer", company="Northwind", hash="h", language="en"),
        requirements=requirements,
        evidence=evidence,
        summary=MatchSummary(
            total=len(specs),
            strong=strong,
            partial=partial,
            missing=missing,
            must_missing=0,
            sentence="…",
        ),
        cv_hash=cv.hash,
    )


# ─── Selection ────────────────────────────────────────────────────────


async def test_a_match_with_nothing_unproven_asks_nothing(cv: CVDoc) -> None:
    """The best outcome the product has is not an empty state to apologise for."""
    match = _match(cv, ("R1", "must", "strong", "Go"))
    sampling = FakeSampling()
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert result.items == []
    assert sampling.requests == [], "a match with no gaps must not cost a model call"


async def test_partial_requirements_are_asked_about_too(cv: CVDoc) -> None:
    """"Related" is where a career switcher lives, and one sentence often moves it."""
    match = _match(
        cv,
        ("R1", "must", "partial", "Kubernetes in production"),
        ("R2", "must", "strong", "Go"),
    )
    sampling = FakeSampling([{"gaps": []}])
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert [item.requirement_id for item in result.items] == ["R1"]


async def test_must_haves_come_first_and_missing_before_partial(cv: CVDoc) -> None:
    match = _match(
        cv,
        ("R1", "nice", "missing", "Rust"),
        ("R2", "must", "partial", "Kubernetes in production"),
        ("R3", "must", "missing", "Terraform"),
        ("R4", "nice", "partial", "GraphQL"),
    )
    sampling = FakeSampling([{"gaps": []}])
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert [item.requirement_id for item in result.items] == ["R3", "R2", "R1", "R4"]


async def test_the_list_is_capped(cv: CVDoc) -> None:
    match = _match(cv, *[(f"R{n}", "must", "missing", f"Skill {n}") for n in range(1, 13)])
    sampling = FakeSampling([{"gaps": []}])
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert len(result.items) == DEFAULT_MAX_GAPS

    sampling = FakeSampling([{"gaps": []}])
    result = await plan_gaps(_client(sampling), cv=cv, match=match, max_gaps=99)
    assert len(result.items) == HARD_MAX_GAPS


# ─── The question may not assume an experience ────────────────────────


async def test_a_question_may_name_what_the_posting_asked_for(cv: CVDoc) -> None:
    """The requirement's own words are legitimate — the question is about it.

    "Kubernetes" is in neither the CV nor the lexicon's reach here; it is in the
    requirement, which is exactly why the question is allowed to say it.
    """
    match = _match(cv, ("R1", "must", "missing", "Kubernetes in production"))
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        "question": "Have you ever run anything on Kubernetes, even a side project?",
                        "angle": "",
                        "line_ids": [],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert result.items[0].question.startswith("Have you ever run anything on Kubernetes")
    assert result.items[0].templated is False


async def test_a_question_that_assumes_an_employer_is_replaced(cv: CVDoc) -> None:
    """The failure this feature could have introduced, one layer earlier."""
    match = _match(cv, ("R1", "must", "missing", "Terraform"))
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        "question": "You used Terraform at Globex — how large was that estate?",
                        "angle": "",
                        "line_ids": [],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    item = result.items[0]
    assert "Globex" not in item.question
    assert item.templated is True
    assert "Terraform" in item.question, "the template still quotes the requirement"


async def test_a_question_that_invents_a_number_is_replaced(cv: CVDoc) -> None:
    match = _match(cv, ("R1", "must", "missing", "Mentoring"))
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        "question": "You mentored 12 engineers — what did that look like?",
                        "angle": "",
                        "line_ids": [],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert result.items[0].templated is True
    assert "12" not in result.items[0].question


# ─── The angle gets the ordinary rule ─────────────────────────────────


async def test_a_grounded_angle_survives_with_its_citation(cv: CVDoc) -> None:
    go_line = next(line.id for line in cv.lines if "Go" in line.text)
    match = _match(cv, ("R1", "must", "partial", "Backend services at scale"))
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        "question": "Have you run any of those services under real load?",
                        "angle": "You built payment reconciliation services in Go.",
                        "line_ids": [go_line],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert result.items[0].angle == "You built payment reconciliation services in Go."
    assert result.items[0].line_ids == [go_line]


async def test_an_angle_that_stretches_is_dropped_not_softened(cv: CVDoc) -> None:
    go_line = next(line.id for line in cv.lines if "Go" in line.text)
    match = _match(cv, ("R1", "must", "partial", "High traffic systems"))
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        "question": "Have you handled a traffic spike on those services?",
                        "angle": "You served 40 million requests a day at Globex.",
                        "line_ids": [go_line],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    item = result.items[0]
    assert item.angle is None
    assert item.line_ids == []
    # The question was clean, so it is kept: one bad artefact does not cost the other.
    assert item.templated is False


async def test_an_angle_with_no_citation_is_dropped(cv: CVDoc) -> None:
    """An angle is a claim about the candidate; an uncited claim has no source."""
    match = _match(cv, ("R1", "must", "partial", "Backend services"))
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        "question": "Have you run those services yourself?",
                        "angle": "You have done plenty of this already.",
                        "line_ids": [],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert result.items[0].angle is None


async def test_an_angle_citing_a_line_that_does_not_exist_is_dropped(cv: CVDoc) -> None:
    match = _match(cv, ("R1", "must", "partial", "Backend services"))
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        "question": "Have you run those services yourself?",
                        "angle": "You built reconciliation services in Go.",
                        "line_ids": ["L999"],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert result.items[0].angle is None
    assert result.items[0].line_ids == []


# ─── The floor ────────────────────────────────────────────────────────


async def test_a_model_failure_still_leaves_every_gap_answerable(cv: CVDoc) -> None:
    """A bad model call costs phrasing, not the feature."""
    match = _match(
        cv,
        ("R1", "must", "missing", "Terraform"),
        ("R2", "nice", "missing", "Rust"),
    )
    sampling = FakeSampling()
    sampling.queue_error(-32003, "provider exploded")
    sampling.queue_error(-32003, "provider exploded again")

    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert len(result.items) == 2
    assert all(item.templated for item in result.items)
    assert all(item.question for item in result.items)
    assert "Terraform" in result.items[0].question


async def test_a_requirement_the_model_skipped_still_gets_a_question(cv: CVDoc) -> None:
    match = _match(
        cv,
        ("R1", "must", "missing", "Terraform"),
        ("R2", "must", "missing", "Rust"),
    )
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        "question": "Have you written any Terraform, even once?",
                        "angle": "",
                        "line_ids": [],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert [item.templated for item in result.items] == [False, True]


async def test_an_id_the_model_invented_is_ignored(cv: CVDoc) -> None:
    match = _match(cv, ("R1", "must", "missing", "Terraform"))
    sampling = FakeSampling(
        [
            {
                "gaps": [
                    {
                        "requirement_id": "R9",
                        "question": "Have you written any Terraform?",
                        "angle": "",
                        "line_ids": [],
                    }
                ]
            }
        ]
    )
    result = await plan_gaps(_client(sampling), cv=cv, match=match)
    assert [item.requirement_id for item in result.items] == ["R1"]
    assert result.items[0].templated is True


async def test_turkish_falls_back_in_turkish(cv: CVDoc) -> None:
    match = _match(cv, ("R1", "must", "missing", "Terraform"))
    sampling = FakeSampling()
    sampling.queue_error(-32003, "boom")
    sampling.queue_error(-32003, "boom")
    result = await plan_gaps(_client(sampling), cv=cv, match=match, locale="tr")
    assert "gösterebileceğiniz" in result.items[0].question
