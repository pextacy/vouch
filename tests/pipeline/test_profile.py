"""The profile: the one surface with no posting behind it, and no licence from one.

`tailor` and `letter` may use a concept the posting named — that is the
documented edge of the verifier's rule. A profile has no posting, so it has
no such edge: every term in it has to come from the CV. These tests hold that
line, and they hold the other half of the promise too — a headline that cannot
be grounded comes back empty rather than printed, because a profile with an
invented headline is worse than one with none.
"""

from __future__ import annotations

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.llm import LlmClient, TokenBudget
from receipts_engine.parse.cv import parse_cv
from receipts_engine.pipeline import write_profile
from receipts_engine.schemas import CVDoc

from .fake_llm import FakeSampling


@pytest.fixture
def cv(sample_cv_text: str) -> CVDoc:
    return parse_cv(source="text", text=sample_cv_text)


def _client(sampling: FakeSampling) -> LlmClient:
    return LlmClient(sampling, TokenBudget())


def _profile(headline: str, headline_ids: list[str], *about: tuple[str, list[str]]) -> dict:
    return {
        "headline": headline,
        "headline_line_ids": headline_ids,
        "about": [{"text": text, "line_ids": ids} for text, ids in about],
    }


def _line_containing(cv: CVDoc, needle: str) -> str:
    return next(line.id for line in cv.lines if needle in line.text)


async def test_a_grounded_headline_and_about_are_kept(cv: CVDoc) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling()
    sampling.queue(
        _profile(
            "Backend engineer — payments reconciliation in Go",
            [go_line],
            ("I build payment reconciliation services in Go.", [go_line]),
        )
    )

    result = await write_profile(_client(sampling), cv=cv)

    assert "Go" in result.headline
    assert result.headline_line_ids == [go_line]
    assert [para.line_ids for para in result.about] == [[go_line]]
    assert result.cv_hash == cv.hash


async def test_an_invented_headline_comes_back_empty_rather_than_printed(cv: CVDoc) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling()
    # Both calls keep the invention: the repair is allowed once, not forever.
    for _ in range(2):
        sampling.queue(
            _profile(
                "Award-winning engineer at Globex — 40% faster payments",
                [go_line],
                ("I build payment reconciliation services in Go.", [go_line]),
            )
        )

    result = await write_profile(_client(sampling), cv=cv)

    assert result.headline == ""
    assert result.headline_line_ids == []
    # The About that *was* grounded still stands: the headline failing is not
    # a reason to throw away the paragraph that passed.
    assert result.about


async def test_a_profile_with_nothing_grounded_is_an_error(cv: CVDoc) -> None:
    sampling = FakeSampling()
    for _ in range(2):
        sampling.queue(
            _profile(
                "Engineer",
                [],
                ("I led a team of 12 at Globex and cut costs by 40%.", []),
            )
        )

    with pytest.raises(EngineError) as raised:
        await write_profile(_client(sampling), cv=cv)

    assert raised.value.code == "model_output_invalid"
    assert len(sampling.requests) == 2, "one repair, not a loop"


async def test_the_repair_is_told_what_the_cv_could_not_back(cv: CVDoc) -> None:
    go_line = _line_containing(cv, "Go")
    sampling = FakeSampling()
    sampling.queue(
        _profile(
            "Engineer at Globex",
            [go_line],
            ("I cut costs by 40% at Globex.", [go_line]),
        )
    )
    sampling.queue(
        _profile(
            "Backend engineer — payments reconciliation in Go",
            [go_line],
            ("I build payment reconciliation services in Go.", [go_line]),
        )
    )

    result = await write_profile(_client(sampling), cv=cv)

    assert "Globex" not in result.headline
    assert not any("Globex" in para.text for para in result.about)
    assert "Globex" in str(sampling.requests[1])


async def test_the_header_is_not_material_for_a_profile(cv: CVDoc) -> None:
    """A name and a city are not something to write a profile out of."""
    sampling = FakeSampling()
    sampling.queue(_profile("Engineer", [], ("I build payment services in Go.", [])))

    await write_profile(_client(sampling), cv=cv)

    sent = str(sampling.requests[0])
    header = next(line for line in cv.lines if line.section == "header")
    assert header.text not in sent


async def test_an_empty_cv_is_refused_before_a_call() -> None:
    empty = CVDoc(hash="h", detected_language="en", lines=[])
    sampling = FakeSampling()

    with pytest.raises(EngineError) as raised:
        await write_profile(_client(sampling), cv=empty)

    assert raised.value.code == "cv_too_short"
    assert sampling.requests == []
