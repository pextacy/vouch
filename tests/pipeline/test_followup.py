"""The follow-up: the note the app writes, and the one it refuses to write.

Every other tool in this category will write a follow-up on demand — a warm
paragraph that says the candidate remains interested and hands a recruiter
nothing they did not already have. The feature here is the refusal, so the
first thing tested is that an application with nothing new behind it costs
**no model call at all**: a decline that spent the user's credits would be the
worst of both.

The rest is the promise every generated sentence in this product carries. The
note may only stand on lines written *after* the application went out, and a
paragraph the verifier rejects is dropped rather than softened — with the
whole note failing loudly when the paragraph it exists for is the one that
fell over.
"""

from __future__ import annotations

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.llm import LlmClient, TokenBudget
from receipts_engine.pipeline import write_followup
from receipts_engine.schemas import (
    CVDoc,
    CVLine,
    Evidence,
    MatchResult,
    MatchSummary,
    PostingMeta,
    Requirement,
)

from .fake_llm import FakeSampling

SENT = "2026-09-10T09:00:00+00:00"
AFTER = "2026-09-20T10:00:00Z"
BEFORE = "2026-09-01T10:00:00Z"


def _cv(*added: CVLine) -> CVDoc:
    return CVDoc(
        hash="cv-hash~e1",
        detected_language="en",
        lines=[
            CVLine(id="L1", text="Dilek Aydın — Backend Engineer", section="header"),
            CVLine(
                id="L2",
                text="Built payment reconciliation services in Go at Acme Payments.",
                section="experience",
            ),
            *added,
        ],
    )


def _match(*, cv_hash: str = "cv-hash") -> MatchResult:
    return MatchResult(
        id="m1",
        created_at=SENT,
        cv_hash=cv_hash,
        posting=PostingMeta(
            hash="p1", language="en", title="Backend Engineer", company="Northwind"
        ),
        requirements=[
            Requirement(
                id="R1",
                text="Production experience with Kafka",
                kind="must",
                category="skill",
                source_quote="Kafka in production",
            ),
            Requirement(
                id="R2",
                text="Backend engineering in Go",
                kind="must",
                category="skill",
                source_quote="Go",
            ),
        ],
        evidence=[
            Evidence(requirement_id="R1", status="missing", line_ids=[], why=""),
            Evidence(requirement_id="R2", status="strong", line_ids=["L2"], why=""),
        ],
        summary=MatchSummary(total=2, strong=1, partial=0, missing=1, must_missing=1, sentence=""),
    )


def _client(sampling: FakeSampling) -> LlmClient:
    return LlmClient(sampling, TokenBudget())


def _note(*paragraphs: tuple[str, list[str]]) -> dict:
    return {"paragraphs": [{"text": text, "line_ids": ids} for text, ids in paragraphs]}


KAFKA = CVLine(
    id="L9",
    text="Owned the Kafka consumer rewrite at Acme Payments.",
    section="experience",
    added_at=AFTER,
)


# ─── The refusal, and what it costs ───────────────────────────────────


async def test_nothing_new_declines_without_spending_a_call() -> None:
    sampling = FakeSampling()

    result = await write_followup(_client(sampling), cv=_cv(), match=_match())

    assert result.kind == "nothing_new"
    assert result.paragraphs == []
    # The whole point: declining is free. A model call to be told there is
    # nothing to say would spend the user's credits on the app's own opinion.
    assert sampling.requests == []


async def test_a_line_written_before_it_went_out_is_not_news() -> None:
    """The match read that line already and said what it said."""
    old = CVLine(id="L9", text="Owned the Kafka consumer rewrite.", section="experience", added_at=BEFORE)
    sampling = FakeSampling()

    result = await write_followup(_client(sampling), cv=_cv(old), match=_match())

    assert result.kind == "nothing_new"
    assert sampling.requests == []


async def test_a_requirement_the_application_already_proved_is_not_a_reason() -> None:
    go_again = CVLine(
        id="L9",
        text="More Go work at Acme Payments.",
        section="experience",
        added_at=AFTER,
    )
    sampling = FakeSampling()

    result = await write_followup(_client(sampling), cv=_cv(go_again), match=_match())

    assert result.kind == "nothing_new"


# ─── The note, when there is one ──────────────────────────────────────


async def test_it_writes_from_the_line_the_cv_gained() -> None:
    sampling = FakeSampling()
    sampling.queue(
        _note(
            ("I am following up on my application for the [Role] role.", []),
            ("Since I applied I owned the Kafka consumer rewrite at Acme Payments.", ["L9"]),
            ("Happy to talk it through, [Hiring Manager].", []),
        )
    )

    result = await write_followup(_client(sampling), cv=_cv(KAFKA), match=_match(), sent_at=SENT)

    assert result.kind == "new_evidence"
    assert [para.line_ids for para in result.paragraphs] == [[], ["L9"], []]
    assert result.line_ids == ["L9"]
    assert result.terms == ["Kafka"]
    # One call, and the model was never told the employer or the role.
    assert len(sampling.requests) == 1
    sent = str(sampling.requests[0])
    assert "Northwind" not in sent and "Backend Engineer" not in sent


async def test_only_the_placeholders_a_person_must_fill_are_reported() -> None:
    sampling = FakeSampling()
    sampling.queue(
        _note(
            ("About my application for the [Role] role at [Company].", []),
            ("I have since owned the Kafka consumer rewrite at Acme Payments.", ["L9"]),
            ("Thank you, [Hiring Manager].", []),
        )
    )

    result = await write_followup(_client(sampling), cv=_cv(KAFKA), match=_match())

    # The posting gave a company and a role, so those are filled at the point
    # of use; the reader's name is the one nobody can fill for the user.
    assert result.placeholders == ["[Hiring Manager]"]


async def test_an_invented_paragraph_is_dropped_rather_than_softened() -> None:
    sampling = FakeSampling()
    sampling.queue(
        _note(
            ("I am following up on my application for the [Role] role.", []),
            ("Since I applied I owned the Kafka consumer rewrite at Acme Payments.", ["L9"]),
            ("It cut incidents by 40% across three teams.", ["L9"]),
        )
    )

    result = await write_followup(_client(sampling), cv=_cv(KAFKA), match=_match())

    texts = [para.text for para in result.paragraphs]
    assert not any("40%" in text for text in texts), "a number the CV cannot back"
    assert any("Kafka consumer rewrite" in text for text in texts)


async def test_an_invented_evidence_paragraph_is_repaired_rather_than_refused() -> None:
    """The same budget `tailor` and `letter` get: one more attempt, then drop."""
    sampling = FakeSampling()
    sampling.queue(
        _note(
            ("I am following up on my application for the [Role] role.", []),
            ("Since I applied I have led a team of 12 at Globex.", ["L9"]),
        )
    )
    sampling.queue(
        _note(
            ("I am following up on my application for the [Role] role.", []),
            ("Since I applied I owned the Kafka consumer rewrite at Acme Payments.", ["L9"]),
        )
    )

    result = await write_followup(_client(sampling), cv=_cv(KAFKA), match=_match())

    assert result.kind == "new_evidence"
    assert any("Kafka consumer rewrite" in para.text for para in result.paragraphs)
    assert not any("Globex" in para.text for para in result.paragraphs)
    assert len(sampling.requests) == 2
    # The repair was told what sank the first draft rather than asked again.
    assert "Globex" in str(sampling.requests[1])


async def test_a_note_that_cannot_be_grounded_twice_is_an_error_not_a_short_note() -> None:
    sampling = FakeSampling()
    for _ in range(2):
        sampling.queue(
            _note(
                ("I am following up on my application for the [Role] role.", []),
                ("Since I applied I have led a team of 12 at Globex.", ["L9"]),
            )
        )

    with pytest.raises(EngineError) as raised:
        await write_followup(_client(sampling), cv=_cv(KAFKA), match=_match())

    assert raised.value.code == "model_output_invalid"
    assert len(sampling.requests) == 2, "one repair, not a loop"


async def test_the_clock_comes_from_the_record_not_from_the_model() -> None:
    sampling = FakeSampling()
    sampling.queue(_note(("Since I applied I owned the Kafka consumer rewrite.", ["L9"])))

    result = await write_followup(
        _client(sampling), cv=_cv(KAFKA), match=_match(), sent_at="2026-09-12T09:00:00Z"
    )

    assert result.dated_from == "sent"
    assert result.days is not None and result.days >= 0
    # And the model was told neither the date nor the gap.
    assert "2026-09-12" not in str(sampling.requests[0])
