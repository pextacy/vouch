"""``run_match`` end to end against a scripted model.

The assertions here are about the guarantees the UI depends on: ids line up,
invented citations are corrected, an empty extraction is a failure rather than
an empty success, and the run stays inside the host's sampling budget.
"""

from __future__ import annotations

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.llm import LlmClient, TokenBudget
from receipts_engine.parse.cv import parse_cv
from receipts_engine.pipeline import clear_requirement_cache, run_match

from .fake_llm import FakeSampling


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    clear_requirement_cache()


REQUIREMENTS = {
    "posting_title": "Senior Backend Engineer",
    "company": "Northwind Ledger",
    "requirements": [
        {
            "id": "R1",
            "text": "5+ years of backend engineering",
            "kind": "must",
            "category": "experience",
            "source_quote": "5+ years of backend engineering experience",
        },
        {
            "id": "R2",
            "text": "Production experience with Go",
            "kind": "must",
            "category": "skill",
            "source_quote": "Strong production experience with Go",
        },
        {
            "id": "R3",
            "text": "Running services on Kubernetes",
            "kind": "must",
            "category": "skill",
            "source_quote": "Experience running services on Kubernetes",
        },
        {
            "id": "R4",
            "text": "Familiarity with Kafka",
            "kind": "nice",
            "category": "skill",
            "source_quote": "Familiarity with Kafka",
        },
    ],
}

EVIDENCE = {
    "evidence": [
        {"requirement_id": "R1", "status": "strong", "line_ids": ["L5"], "why": "Six years at Acme"},
        {"requirement_id": "R2", "status": "strong", "line_ids": ["L6"], "why": "Built services in Go"},
        {"requirement_id": "R3", "status": "partial", "line_ids": ["L7"], "why": "Migrated to k8s"},
        {"requirement_id": "R4", "status": "missing", "line_ids": [], "why": "No mention of Kafka"},
    ]
}


def _client(sampling: FakeSampling) -> LlmClient:
    return LlmClient(sampling, TokenBudget())  # type: ignore[arg-type]


async def test_happy_path_returns_a_complete_result(sample_cv_text: str, sample_posting: str) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([REQUIREMENTS, EVIDENCE])

    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)

    assert len(result.requirements) == 4
    assert len(result.evidence) == 4
    assert result.cv_hash == cv.hash
    assert result.posting.company == "Northwind Ledger"


async def test_every_requirement_gets_a_status(sample_cv_text: str, sample_posting: str) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([REQUIREMENTS, EVIDENCE])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert {e.requirement_id for e in result.evidence} == {r.id for r in result.requirements}


async def test_summary_counts_match_the_evidence(sample_cv_text: str, sample_posting: str) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([REQUIREMENTS, EVIDENCE])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    summary = result.summary
    assert (summary.strong, summary.partial, summary.missing) == (2, 1, 1)
    assert summary.total == 4
    assert summary.must_missing == 0


async def test_summary_sentence_is_written_in_the_requested_locale(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([REQUIREMENTS, EVIDENCE])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting, locale="tr")
    assert "gereksinimden" in result.summary.sentence


async def test_invented_line_ids_are_downgraded_to_missing(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    invented = {
        "evidence": [
            {"requirement_id": "R1", "status": "strong", "line_ids": ["L999"], "why": "…"},
            {"requirement_id": "R2", "status": "strong", "line_ids": ["L6"], "why": "Go"},
            {"requirement_id": "R3", "status": "partial", "line_ids": ["L7"], "why": "k8s"},
            {"requirement_id": "R4", "status": "missing", "line_ids": [], "why": "none"},
        ]
    }
    sampling = FakeSampling([REQUIREMENTS, invented])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)

    first = next(e for e in result.evidence if e.requirement_id == "R1")
    assert first.status == "missing"
    assert first.line_ids == []
    assert result.summary.must_missing == 1


async def test_a_citation_on_a_missing_verdict_is_removed(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    contradictory = {
        "evidence": [
            {"requirement_id": "R1", "status": "strong", "line_ids": ["L6"], "why": "…"},
            {"requirement_id": "R2", "status": "strong", "line_ids": ["L6"], "why": "Go"},
            {"requirement_id": "R3", "status": "partial", "line_ids": ["L7"], "why": "k8s"},
            {"requirement_id": "R4", "status": "missing", "line_ids": ["L6"], "why": "none"},
        ]
    }
    sampling = FakeSampling([REQUIREMENTS, contradictory])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert next(e for e in result.evidence if e.requirement_id == "R4").line_ids == []


async def test_a_skipped_requirement_defaults_to_missing(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    partial = {"evidence": EVIDENCE["evidence"][:2]}
    sampling = FakeSampling([REQUIREMENTS, partial])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert next(e for e in result.evidence if e.requirement_id == "R4").status == "missing"


async def test_duplicate_requirements_are_merged(sample_cv_text: str, sample_posting: str) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    duplicated = {
        **REQUIREMENTS,
        "requirements": REQUIREMENTS["requirements"] + [
            {
                "id": "R9",
                "text": "Production experience with Go",
                "kind": "must",
                "category": "skill",
                "source_quote": "Strong production experience with Go",
            }
        ],
    }
    sampling = FakeSampling([duplicated, EVIDENCE])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert len(result.requirements) == 4


async def test_requirement_ids_are_renumbered_contiguously(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    gappy = {
        **REQUIREMENTS,
        "requirements": [
            {**item, "id": f"R{index * 7 + 3}"}
            for index, item in enumerate(REQUIREMENTS["requirements"])
        ],
    }
    sampling = FakeSampling([gappy, {"evidence": []}])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert [r.id for r in result.requirements] == ["R1", "R2", "R3", "R4"]


async def test_a_paraphrased_source_quote_is_dropped(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    reworded = {
        **REQUIREMENTS,
        "requirements": [
            {**REQUIREMENTS["requirements"][0], "source_quote": "about five years of backend work"}
        ],
    }
    sampling = FakeSampling([reworded, {"evidence": []}])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert result.requirements[0].source_quote == ""


async def test_no_requirements_is_a_failure_not_an_empty_success(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([{**REQUIREMENTS, "requirements": []}])
    with pytest.raises(EngineError) as excinfo:
        await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert excinfo.value.code == "no_requirements_found"


async def test_text_that_is_not_a_posting_fails_before_any_model_call(sample_cv_text: str) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([])
    with pytest.raises(EngineError) as excinfo:
        await run_match(_client(sampling), cv=cv, posting_text="hello there")
    assert excinfo.value.code == "no_requirements_found"
    assert sampling.requests == []


async def test_malformed_model_output_is_retried_once(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling(["not json at all", REQUIREMENTS, EVIDENCE])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert len(result.requirements) == 4
    assert len(sampling.requests) == 3


async def test_two_bad_responses_surface_model_output_invalid(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling(["nope", "still nope"])
    with pytest.raises(EngineError) as excinfo:
        await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert excinfo.value.code == "model_output_invalid"
    assert excinfo.value.retriable


async def test_json_wrapped_in_prose_is_still_parsed(
    sample_cv_text: str, sample_posting: str
) -> None:
    import json

    cv = parse_cv(source="text", text=sample_cv_text)
    fenced = f"Here you go:\n```json\n{json.dumps(REQUIREMENTS)}\n```\nHope that helps."
    sampling = FakeSampling([fenced, EVIDENCE])
    result = await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert len(result.requirements) == 4


async def test_sampling_quota_maps_to_sampling_unavailable(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling()
    sampling.queue_error(-32002, "quota exhausted")
    with pytest.raises(EngineError) as excinfo:
        await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert excinfo.value.code == "sampling_unavailable"


async def test_a_match_costs_exactly_two_model_calls(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([REQUIREMENTS, EVIDENCE])
    await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert len(sampling.requests) == 2


async def test_repeating_the_same_posting_reuses_the_extraction(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([REQUIREMENTS, EVIDENCE, EVIDENCE])
    await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    await run_match(_client(sampling), cv=cv, posting_text=sample_posting)
    assert len(sampling.requests) == 3  # extract once, match twice


async def test_the_run_stays_inside_the_per_invoke_token_budget(
    sample_cv_text: str, sample_posting: str
) -> None:
    cv = parse_cv(source="text", text=sample_cv_text)
    sampling = FakeSampling([REQUIREMENTS, EVIDENCE])
    budget = TokenBudget()
    await run_match(LlmClient(sampling, budget), cv=cv, posting_text=sample_posting)  # type: ignore[arg-type]
    assert budget.tokens_left > 0
    assert budget.calls_left > 0
