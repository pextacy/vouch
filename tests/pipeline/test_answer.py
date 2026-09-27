"""Answering a form's questions — and refusing to.

The generated half is tested the way every generated thing in this product is:
an invented fact must not survive the verifier. But the feature's argument is
the other half, so that is where most of these live. Two kinds of silence have
to be real rather than decorative:

* ``no_evidence`` — the CV cannot answer it, so the app does not write around
  it. A model that claims an answer and grounds none of it gets downgraded
  here, because an answer that cited nothing is an absent one.
* ``not_about_you`` — the question asks what the candidate wants. A CV holds no
  evidence of wanting anything, so prose arriving through that door is thrown
  away unread. That door is the promise, and this is the test that keeps it.
"""

from __future__ import annotations

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.llm import LlmClient, TokenBudget
from receipts_engine.parse.cv import parse_cv
from receipts_engine.pipeline import answer_questions
from receipts_engine.pipeline.answer import MAX_QUESTIONS, MAX_SENTENCES
from receipts_engine.schemas import (
    CVDoc,
    MatchResult,
    MatchSummary,
    PostingMeta,
    Requirement,
)

from .fake_llm import FakeSampling

CV_TEXT = "\n".join(
    [
        "Dilek Aydin",
        "Backend Engineer - Istanbul",
        "",
        "Experience",
        "Acme Payments - Backend Engineer, 2018-2024",
        "Built payment reconciliation services in Go for 1,200 merchant accounts.",
        "Migrated the reporting pipeline from MySQL to PostgreSQL with zero downtime.",
        "Led a team of 4 engineers and owned the on-call rotation.",
        "",
        "Education",
        "MSc Computer Science, Bogazici University, 2016",
    ]
)


def _client(sampling: FakeSampling) -> LlmClient:
    return LlmClient(sampling, TokenBudget())  # type: ignore[arg-type]


@pytest.fixture
def cv() -> CVDoc:
    return parse_cv(source="text", text=CV_TEXT)


def line_id(cv: CVDoc, needle: str) -> str:
    for line in cv.lines:
        if needle.lower() in line.text.lower():
            return line.id
    raise AssertionError(f"no CV line contains {needle!r}")


def reply(*answers: dict[str, object]) -> dict[str, object]:
    """The two flat lists the host's schema depth limit forces."""
    verdicts = [{"index": a["index"], "kind": a["kind"]} for a in answers]
    sentences = [
        {"index": a["index"], "text": s["text"], "line_ids": s["line_ids"]}
        for a in answers
        for s in a["sentences"]  # type: ignore[union-attr]
    ]
    return {"verdicts": verdicts, "sentences": sentences}


def answered(index: int, *sentences: tuple[str, list[str]]) -> dict[str, object]:
    return {
        "index": index,
        "kind": "answered",
        "sentences": [{"text": text, "line_ids": ids} for text, ids in sentences],
    }


def match_for(*requirements: str) -> MatchResult:
    return MatchResult(
        id="m1",
        created_at="2026-09-25T00:00:00Z",
        cv_hash="cv-hash",
        posting=PostingMeta(company="Globex", title="Staff Engineer", hash="p", language="en"),
        requirements=[
            Requirement(id=f"R{i}", text=text, kind="must", category="skill", source_quote=text)
            for i, text in enumerate(requirements, start=1)
        ],
        evidence=[],
        summary=MatchSummary(total=0, strong=0, partial=0, missing=0, must_missing=0, sentence=""),
    )


# ─── Answering from the CV ────────────────────────────────────────────


async def test_a_grounded_answer_survives_with_its_citations(cv: CVDoc) -> None:
    source = line_id(cv, "reconciliation")
    sampling = FakeSampling()
    sampling.queue(
        reply(answered(0, ("I built payment reconciliation services in Go.", [source])))
    )

    result = await answer_questions(
        _client(sampling),
        cv=cv,
        questions=["Describe your experience with payment systems."],
    )

    assert [item.kind for item in result.items] == ["answered"]
    assert result.items[0].sentences[0].line_ids == [source]
    assert result.items[0].dropped == 0


async def test_the_question_is_echoed_back_as_the_user_typed_it(cv: CVDoc) -> None:
    """Paired by text, not by order, and never tidied by the model."""
    asked = "Describe your experience with payment systems."
    sampling = FakeSampling()
    sampling.queue(reply(answered(0, ("I built reconciliation services in Go.", [line_id(cv, "reconciliation")]))))

    result = await answer_questions(_client(sampling), cv=cv, questions=[asked])

    assert result.items[0].question == asked


async def test_several_questions_are_answered_in_the_order_they_were_asked(cv: CVDoc) -> None:
    go = line_id(cv, "reconciliation")
    team = line_id(cv, "team of 4")
    sampling = FakeSampling()
    sampling.queue(
        reply(
            answered(1, ("I led a team of 4 engineers.", [team])),
            answered(0, ("I built reconciliation services in Go.", [go])),
        )
    )

    result = await answer_questions(
        _client(sampling),
        cv=cv,
        questions=["What have you built?", "Have you led anyone?"],
    )

    assert [item.question for item in result.items] == [
        "What have you built?",
        "Have you led anyone?",
    ]
    assert result.items[0].sentences[0].line_ids == [go]
    assert result.items[1].sentences[0].line_ids == [team]


async def test_an_answer_is_capped_at_a_readable_length(cv: CVDoc) -> None:
    source = line_id(cv, "reconciliation")
    sampling = FakeSampling()
    sampling.queue(
        reply(
            answered(
                0,
                *[("I built payment reconciliation services in Go.", [source])] * 8,
            )
        )
    )

    result = await answer_questions(_client(sampling), cv=cv, questions=["Tell us more."])

    assert len(result.items[0].sentences) <= MAX_SENTENCES


# ─── What the verifier refuses ────────────────────────────────────────


async def test_an_invented_metric_is_dropped(cv: CVDoc) -> None:
    source = line_id(cv, "reconciliation")
    sampling = FakeSampling()
    sampling.queue(
        reply(
            answered(
                0,
                ("I built payment reconciliation services in Go.", [source]),
                ("They cut settlement failures by 38%.", [source]),
            )
        )
    )
    # The repair pass gets one attempt and does no better.
    sampling.queue(reply(answered(0, ("They cut settlement failures by 38%.", [source]))))

    result = await answer_questions(_client(sampling), cv=cv, questions=["What did you build?"])

    texts = [sentence.text for sentence in result.items[0].sentences]
    assert texts == ["I built payment reconciliation services in Go."]
    assert result.items[0].dropped == 1


async def test_an_uncited_sentence_is_dropped(cv: CVDoc) -> None:
    """"Somewhere in this document" is not a citation a reader can follow."""
    sampling = FakeSampling()
    sampling.queue(reply(answered(0, ("I have deep experience in payments.", []))))
    sampling.queue(reply(answered(0, ("I have deep experience in payments.", []))))

    result = await answer_questions(_client(sampling), cv=cv, questions=["Tell us about payments."])

    assert result.items[0].kind == "no_evidence"
    assert result.items[0].sentences == []


async def test_an_answer_that_grounded_nothing_is_downgraded_not_reported_as_thin(
    cv: CVDoc,
) -> None:
    source = line_id(cv, "reconciliation")
    sampling = FakeSampling()
    sampling.queue(reply(answered(0, ("I ran Kubernetes across three regions.", [source]))))
    sampling.queue(reply(answered(0, ("I ran Kubernetes across three regions.", [source]))))

    result = await answer_questions(_client(sampling), cv=cv, questions=["Kubernetes experience?"])

    assert result.items[0].kind == "no_evidence"
    assert result.items[0].sentences == []
    assert result.items[0].dropped == 1


async def test_the_repair_pass_can_rescue_an_answer(cv: CVDoc) -> None:
    source = line_id(cv, "reconciliation")
    sampling = FakeSampling()
    sampling.queue(reply(answered(0, ("I cut failures by 38% in Go.", [source]))))
    sampling.queue(reply(answered(0, ("I built payment reconciliation services in Go.", [source]))))

    result = await answer_questions(_client(sampling), cv=cv, questions=["What did you build?"])

    assert result.items[0].kind == "answered"
    assert result.items[0].sentences[0].text == "I built payment reconciliation services in Go."
    # The count survives the rescue: the user should know a sentence was lost.
    assert result.items[0].dropped == 1


async def test_a_sentence_that_passed_is_not_replaced_by_a_second_draft(cv: CVDoc) -> None:
    go = line_id(cv, "reconciliation")
    team = line_id(cv, "team of 4")
    sampling = FakeSampling()
    sampling.queue(
        reply(
            answered(0, ("I built payment reconciliation services in Go.", [go])),
            answered(1, ("I led a team of 12.", [team])),
        )
    )
    sampling.queue(
        reply(
            answered(0, ("Something else entirely.", [go])),
            answered(1, ("I led a team of 4 engineers.", [team])),
        )
    )

    result = await answer_questions(
        _client(sampling), cv=cv, questions=["What did you build?", "Have you led anyone?"]
    )

    assert result.items[0].sentences[0].text == "I built payment reconciliation services in Go."
    assert result.items[1].sentences[0].text == "I led a team of 4 engineers."


# ─── The two silences ─────────────────────────────────────────────────


async def test_a_motivation_question_is_answered_with_nothing(cv: CVDoc) -> None:
    sampling = FakeSampling()
    sampling.queue(reply({"index": 0, "kind": "not_about_you", "sentences": []}))

    result = await answer_questions(
        _client(sampling), cv=cv, questions=["Why do you want to work here?"]
    )

    assert result.items[0].kind == "not_about_you"
    assert result.items[0].sentences == []


async def test_prose_smuggled_through_the_motivation_door_is_discarded(cv: CVDoc) -> None:
    """The door is the promise, so nothing comes through it — cited or not."""
    source = line_id(cv, "reconciliation")
    sampling = FakeSampling()
    sampling.queue(
        reply(
            {
                "index": 0,
                "kind": "not_about_you",
                "sentences": [
                    {"text": "I built payment reconciliation services in Go.", "line_ids": [source]}
                ],
            }
        )
    )

    result = await answer_questions(
        _client(sampling), cv=cv, questions=["Why do you want to work here?"]
    )

    assert result.items[0].kind == "not_about_you"
    assert result.items[0].sentences == []


async def test_a_question_the_model_skipped_still_comes_back_answerable(cv: CVDoc) -> None:
    sampling = FakeSampling()
    sampling.queue(reply(answered(0, ("I built reconciliation services in Go.", [line_id(cv, "reconciliation")]))))

    result = await answer_questions(
        _client(sampling), cv=cv, questions=["What did you build?", "Do you know Rust?"]
    )

    assert [item.kind for item in result.items] == ["answered", "no_evidence"]


# ─── The question is never a source ───────────────────────────────────


async def test_the_questions_own_words_do_not_license_a_claim(cv: CVDoc) -> None:
    """The one input here an employer controls cannot vouch for anything.

    Otherwise a form reading "Describe your Kubernetes work" would let the
    answer claim Kubernetes — the posting-vocabulary leak with a new front
    door (`CLAUDE.md` rule 1).
    """
    source = line_id(cv, "reconciliation")
    sampling = FakeSampling()
    sampling.queue(reply(answered(0, ("I have run Kubernetes in production.", [source]))))
    sampling.queue(reply(answered(0, ("I have run Kubernetes in production.", [source]))))

    result = await answer_questions(
        _client(sampling), cv=cv, questions=["Describe your Kubernetes work."]
    )

    assert result.items[0].kind == "no_evidence"


async def test_a_concept_the_posting_uses_is_still_borrowable(cv: CVDoc) -> None:
    """The existing, tested rule, unchanged: concepts yes, facts never."""
    source = line_id(cv, "team of 4")
    sampling = FakeSampling()
    sampling.queue(
        reply(answered(0, ("I handled Stakeholder Management for the on-call rotation.", [source])))
    )

    result = await answer_questions(
        _client(sampling),
        cv=cv,
        questions=["How do you work with others?"],
        match=match_for("Stakeholder Management experience"),
    )

    assert result.items[0].kind == "answered"


async def test_the_match_is_recorded_but_never_required(cv: CVDoc) -> None:
    sampling = FakeSampling()
    sampling.queue(reply({"index": 0, "kind": "not_about_you", "sentences": []}))
    with_match = await answer_questions(
        _client(sampling), cv=cv, questions=["Why us?"], match=match_for("Go")
    )
    assert with_match.match_id == "m1"

    sampling.queue(reply({"index": 0, "kind": "not_about_you", "sentences": []}))
    alone = await answer_questions(_client(sampling), cv=cv, questions=["Why us?"])
    assert alone.match_id is None


# ─── Limits and refusals ──────────────────────────────────────────────


async def test_a_form_with_no_questions_is_refused(cv: CVDoc) -> None:
    with pytest.raises(EngineError) as raised:
        await answer_questions(_client(FakeSampling()), cv=cv, questions=["   ", ""])
    assert raised.value.code == "invalid_args"


async def test_answering_without_a_cv_is_refused() -> None:
    empty = CVDoc(hash="h", detected_language="en", lines=[])
    with pytest.raises(EngineError) as raised:
        await answer_questions(_client(FakeSampling()), cv=empty, questions=["Anything?"])
    assert raised.value.code == "cv_too_short"


async def test_a_questionnaire_is_cut_to_a_form(cv: CVDoc) -> None:
    sampling = FakeSampling()
    sampling.queue(reply())

    result = await answer_questions(
        _client(sampling),
        cv=cv,
        questions=[f"Question number {n}?" for n in range(MAX_QUESTIONS + 4)],
    )

    assert len(result.items) == MAX_QUESTIONS


async def test_the_same_question_twice_is_answered_once(cv: CVDoc) -> None:
    sampling = FakeSampling()
    sampling.queue(reply())

    result = await answer_questions(
        _client(sampling), cv=cv, questions=["Why us?", "Why us?", "  Why us?  "]
    )

    assert len(result.items) == 1


async def test_one_clean_pass_costs_one_model_call(cv: CVDoc) -> None:
    """`prd.md §8`: a repair is the exception, not the shape of the feature."""
    sampling = FakeSampling()
    sampling.queue(reply(answered(0, ("I built reconciliation services in Go.", [line_id(cv, "reconciliation")]))))

    await answer_questions(_client(sampling), cv=cv, questions=["What did you build?"])

    assert len(sampling.requests) == 1
