"""Tailor and letter: the generate → verify → repair → drop loop.

These are the tests that keep the promise honest. A suggestion carrying an
invented number must never reach the caller, whether it survives the repair or
not — and the drop must be visible, because silence would read as "your CV had
nothing worth saying".
"""

from __future__ import annotations

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.llm import LlmClient, TokenBudget
from receipts_engine.parse.cv import parse_cv
from receipts_engine.pipeline import tailor_bullets, write_letter
from receipts_engine.schemas import (
    CVDoc,
    Evidence,
    MatchResult,
    MatchSummary,
    PostingMeta,
    Requirement,
)

from .fake_llm import FakeSampling


@pytest.fixture
def cv(sample_cv_text: str) -> CVDoc:
    return parse_cv(source="text", text=sample_cv_text)


@pytest.fixture
def match(cv: CVDoc) -> MatchResult:
    go_line = _line_containing(cv, "Go")
    k8s_line = _line_containing(cv, "k8s")
    team_line = _line_containing(cv, "team of 4")
    requirements = [
        Requirement(
            id="R1",
            text="Production experience with Go",
            kind="must",
            category="skill",
            source_quote="Strong production experience with Go",
        ),
        Requirement(
            id="R2",
            text="Running services on Kubernetes",
            kind="must",
            category="skill",
            source_quote="Experience running services on Kubernetes",
        ),
        Requirement(
            id="R3",
            text="Leading a small team",
            kind="nice",
            category="experience",
            source_quote="Experience leading a small team",
        ),
    ]
    evidence = [
        Evidence(requirement_id="R1", status="strong", line_ids=[go_line], why="Built services in Go"),
        Evidence(requirement_id="R2", status="partial", line_ids=[k8s_line], why="Migrated to k8s"),
        Evidence(requirement_id="R3", status="strong", line_ids=[team_line], why="Led four engineers"),
    ]
    return MatchResult(
        id="match-1",
        created_at="2026-09-16T10:00:00+00:00",
        posting=PostingMeta(title="Senior Backend Engineer", company="Northwind", hash="h", language="en"),
        requirements=requirements,
        evidence=evidence,
        summary=MatchSummary(total=3, strong=2, partial=1, missing=0, must_missing=0, sentence="…"),
        cv_hash=cv.hash,
    )


def _line_containing(cv: CVDoc, needle: str) -> str:
    for line in cv.lines:
        if needle in line.text:
            return line.id
    raise AssertionError(f"fixture CV has no line containing {needle!r}")


def _client(sampling: FakeSampling) -> LlmClient:
    return LlmClient(sampling, TokenBudget())  # type: ignore[arg-type]


# ─── Tailor ───────────────────────────────────────────────────────────


async def test_a_grounded_suggestion_is_kept(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling(
        [
            {
                "bullets": [
                    {
                        "source_line_ids": [go_line],
                        "suggestion": "Built payment reconciliation services in Go.",
                        "targets": ["R1"],
                    }
                ]
            }
        ]
    )
    result = await tailor_bullets(_client(sampling), cv=cv, match=match)
    assert [b.suggestion for b in result.bullets] == [
        "Built payment reconciliation services in Go."
    ]
    assert result.bullets[0].dropped_reason is None


async def test_an_invented_metric_is_repaired_then_kept(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling(
        [
            {
                "bullets": [
                    {
                        "source_line_ids": [go_line],
                        "suggestion": "Built Go services that cut costs by 40%.",
                        "targets": ["R1"],
                    }
                ]
            },
            {
                "bullets": [
                    {
                        "source_line_ids": [go_line],
                        "suggestion": "Built payment reconciliation services in Go.",
                        "targets": ["R1"],
                    }
                ]
            },
        ]
    )
    result = await tailor_bullets(_client(sampling), cv=cv, match=match)
    assert result.bullets[0].suggestion == "Built payment reconciliation services in Go."
    assert "40%" not in (result.bullets[0].suggestion or "")


async def test_a_suggestion_that_fails_twice_is_dropped(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    bad = {
        "bullets": [
            {
                "source_line_ids": [go_line],
                "suggestion": "Built Go services that cut costs by 40%.",
                "targets": ["R1"],
            }
        ]
    }
    sampling = FakeSampling([bad, bad])
    result = await tailor_bullets(_client(sampling), cv=cv, match=match)
    bullet = result.bullets[0]
    assert bullet.suggestion is None
    assert bullet.dropped_reason == "unsupported_claims"
    assert "40%" in bullet.unsupported_tokens


async def test_a_dropped_bullet_still_reports_its_original(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    bad = {
        "bullets": [
            {
                "source_line_ids": [go_line],
                "suggestion": "Scaled Go services to 10M requests per day.",
                "targets": ["R1"],
            }
        ]
    }
    sampling = FakeSampling([bad, bad])
    result = await tailor_bullets(_client(sampling), cv=cv, match=match)
    assert "Go" in result.bullets[0].original


async def test_a_failed_repair_call_drops_rather_than_raises(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling(
        [
            {
                "bullets": [
                    {
                        "source_line_ids": [go_line],
                        "suggestion": "Built Go services used by 3,000 merchants.",
                        "targets": ["R1"],
                    }
                ]
            }
        ]
    )
    sampling.queue_error(-32003, "provider exploded")
    result = await tailor_bullets(_client(sampling), cv=cv, match=match)
    assert result.bullets[0].suggestion is None
    assert result.bullets[0].dropped_reason == "unsupported_claims"


async def test_citations_to_unknown_lines_are_ignored(cv: CVDoc, match: MatchResult) -> None:
    sampling = FakeSampling(
        [{"bullets": [{"source_line_ids": ["L999"], "suggestion": "Anything", "targets": ["R1"]}]}]
    )
    result = await tailor_bullets(_client(sampling), cv=cv, match=match)
    assert result.bullets == []


async def test_max_bullets_is_capped(cv: CVDoc, match: MatchResult) -> None:
    sampling = FakeSampling([{"bullets": []}])
    await tailor_bullets(_client(sampling), cv=cv, match=match, max_bullets=99)
    prompt = sampling.requests[0]["messages"][0]["content"]["text"]
    assert prompt.count("\nL") <= 12


async def test_no_evidenced_requirements_means_no_model_call(cv: CVDoc, match: MatchResult) -> None:
    empty = match.model_copy(
        update={"evidence": [e.model_copy(update={"status": "missing", "line_ids": []}) for e in match.evidence]}
    )
    sampling = FakeSampling([])
    result = await tailor_bullets(_client(sampling), cv=cv, match=empty)
    assert result.bullets == []
    assert sampling.requests == []


# ─── Letter ───────────────────────────────────────────────────────────


async def test_a_grounded_letter_keeps_its_citations(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling(
        [
            {
                "paragraphs": [
                    {
                        "text": "I am applying for the backend role at [Company].",
                        "line_ids": [],
                    },
                    {
                        "text": "I built payment reconciliation services in Go.",
                        "line_ids": [go_line],
                    },
                ]
            }
        ]
    )
    letter = await write_letter(_client(sampling), cv=cv, match=match)
    assert len(letter.paragraphs) == 2
    assert letter.paragraphs[1].line_ids == [go_line]


async def test_placeholders_are_reported_for_the_warning(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling(
        [
            {
                "paragraphs": [
                    {"text": "Dear [Hiring Manager], I am writing about the role at [Company].", "line_ids": []},
                    {"text": "I built reconciliation services in Go.", "line_ids": [go_line]},
                ]
            }
        ]
    )
    letter = await write_letter(_client(sampling), cv=cv, match=match)
    assert letter.placeholders == ["[Company]", "[Hiring Manager]"]


async def test_a_paragraph_with_an_invented_number_is_repaired(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling(
        [
            {
                "paragraphs": [
                    {"text": "I grew revenue by 40% at [Company].", "line_ids": [go_line]},
                ]
            },
            {
                "paragraphs": [
                    {"text": "I built reconciliation services in Go at [Company].", "line_ids": [go_line]},
                ]
            },
        ]
    )
    letter = await write_letter(_client(sampling), cv=cv, match=match)
    assert all("40%" not in para.text for para in letter.paragraphs)


async def test_a_letter_that_never_verifies_raises(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    bad = {"paragraphs": [{"text": "I grew revenue by 40% at Globex.", "line_ids": [go_line]}]}
    sampling = FakeSampling([bad, bad])
    with pytest.raises(EngineError) as excinfo:
        await write_letter(_client(sampling), cv=cv, match=match)
    assert excinfo.value.code == "model_output_invalid"


async def test_a_match_with_no_evidence_cannot_produce_a_letter(cv: CVDoc, match: MatchResult) -> None:
    empty = match.model_copy(
        update={"evidence": [e.model_copy(update={"status": "missing", "line_ids": []}) for e in match.evidence]}
    )
    sampling = FakeSampling([])
    with pytest.raises(EngineError) as excinfo:
        await write_letter(_client(sampling), cv=cv, match=empty)
    assert excinfo.value.code == "no_requirements_found"


async def test_tone_and_length_reach_the_prompt(cv: CVDoc, match: MatchResult) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling(
        [{"paragraphs": [{"text": "I built reconciliation services in Go.", "line_ids": [go_line]}]}]
    )
    letter = await write_letter(_client(sampling), cv=cv, match=match, tone="formal", length="short")
    system = sampling.requests[0]["system_prompt"]
    assert "Tone: formal" in system
    assert "about 150 words" in system
    assert letter.tone == "formal"
