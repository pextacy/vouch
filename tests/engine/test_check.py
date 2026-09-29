"""The verifier, read against a document Vouch did not write.

Two failure modes matter here and they pull in opposite directions. A missed
claim is the product's whole promise broken on the one document that actually
gets sent; a false one teaches the user to scroll past the list, which breaks
it just as thoroughly a week later. So the tests come in pairs: the invented
fact is caught, and the ordinary sentence beside it is left alone.
"""

from __future__ import annotations

import pytest

from receipts_engine.check import (
    MAX_CHARS,
    MAX_CLAIMS_PER_LINE,
    MAX_FLAGGED,
    MAX_UNITS,
    check_document,
)
from receipts_engine.errors import EngineError
from receipts_engine.schemas import (
    CVDoc,
    CVLine,
    MatchResult,
    MatchSummary,
    PostingMeta,
    Requirement,
)


def cv(*lines: tuple[str, str]) -> CVDoc:
    return CVDoc(
        hash="cv-hash",
        detected_language="en",
        lines=[
            CVLine(id=f"L{index}", text=text, section=section)  # type: ignore[arg-type]
            for index, (text, section) in enumerate(lines, start=1)
        ],
    )


REAL_CV = cv(
    ("Mert Yilmaz — Backend Engineer", "header"),
    ("Backend Engineer, Volta Systems, 2019-2023", "experience"),
    ("Built payment services in Python and PostgreSQL.", "experience"),
    ("Ran the nightly reconciliation job for 4 years.", "experience"),
    ("Skills: Python, PostgreSQL, Docker", "skills"),
)


def match(*, company: str | None = None, title: str | None = None, reqs: tuple[str, ...] = ()) -> MatchResult:
    return MatchResult(
        id="m1",
        created_at="2026-09-23T00:00:00Z",
        cv_hash="cv-hash",
        posting=PostingMeta(company=company, title=title, hash="posting-hash", language="en"),
        requirements=[
            Requirement(
                id=f"R{index}", text=text, kind="must", category="skill", source_quote=text
            )
            for index, text in enumerate(reqs, start=1)
        ],
        evidence=[],
        summary=MatchSummary(total=0, strong=0, partial=0, missing=0, must_missing=0, sentence=""),
    )


def surfaces(result: object) -> set[str]:
    return {claim.surface for line in result.flagged for claim in line.claims}  # type: ignore[attr-defined]


# ─── What it catches ──────────────────────────────────────────────────


def test_a_metric_the_cv_never_states_is_flagged() -> None:
    result = check_document(REAL_CV, "Cut checkout latency by 40% and saved $2M a year.")
    assert result.unbacked == 1
    assert {"40%", "2M"} <= surfaces(result)


def test_a_tool_the_cv_never_mentions_is_flagged() -> None:
    result = check_document(REAL_CV, "Migrated the platform to Kubernetes.")
    assert [claim.kind for claim in result.flagged[0].claims] == ["tech"]


def test_an_employer_the_cv_never_names_is_flagged() -> None:
    result = check_document(REAL_CV, "Senior Engineer at Globex Robotics, 2023-2025.")
    assert "Globex Robotics" in surfaces(result)


def test_a_seniority_the_cv_does_not_carry_is_flagged() -> None:
    result = check_document(REAL_CV, "Principal engineer with deep payments experience.")
    assert ("title", "Principal") in {
        (claim.kind, claim.surface) for line in result.flagged for claim in line.claims
    }


def test_each_flagged_sentence_is_quoted_back_verbatim() -> None:
    sentence = "Led a team of 12 engineers across three countries."
    result = check_document(REAL_CV, f"Built payment services in Python.\n{sentence}")
    assert [line.text for line in result.flagged] == [sentence]


def test_the_position_points_at_the_sentence_in_the_document() -> None:
    result = check_document(
        REAL_CV, "Built payment services in Python.\nRan a 40-person department."
    )
    assert [line.index for line in result.flagged] == [1]


# ─── What it leaves alone ─────────────────────────────────────────────


def test_a_sentence_the_cv_states_outright_passes() -> None:
    result = check_document(REAL_CV, "Built payment services in Python and PostgreSQL.")
    assert result.flagged == []
    assert result.checked == 1


def test_rewording_is_free() -> None:
    """The asymmetry the verifier is built on, checked on the paste path too."""
    result = check_document(REAL_CV, "Owned the payment services, written in Python.")
    assert result.flagged == []


def test_a_duration_the_cv_dates_can_derive_passes() -> None:
    result = check_document(REAL_CV, "Four years of backend work.")
    assert result.flagged == []


def test_a_salutation_is_not_a_claim() -> None:
    letter = "Dear Hiring Manager,\nBuilt payment services in Python.\nKind regards,"
    assert check_document(REAL_CV, letter).flagged == []


def test_a_named_recipient_is_not_a_claim() -> None:
    assert check_document(REAL_CV, "Dear Ms. Karadeniz,").flagged == []


def test_a_turkish_salutation_is_not_a_claim() -> None:
    assert check_document(REAL_CV, "Sayın Yetkili,\nSaygılarımla,").flagged == []


def test_hiring_manager_outside_a_greeting_is_still_a_claim() -> None:
    """The greeting rule is anchored on "Dear", not on the words it forgives.

    A rule shaped "allowed because we recognise the phrase" is the leak
    `CLAUDE.md` rule 1 warns about; this is the test that says it is not one.
    """
    result = check_document(REAL_CV, "Hiring Manager, Globex Robotics, 2023-2025.")
    assert "Globex Robotics" in surfaces(result)
    assert any(claim.kind == "title" for line in result.flagged for claim in line.claims)


def test_a_bracket_placeholder_is_not_a_claim() -> None:
    assert check_document(REAL_CV, "I am applying to [Company] for [Role].").flagged == []


# ─── The envelope is not the letter ───────────────────────────────────


def test_the_company_applied_to_is_not_read_as_a_claim() -> None:
    letter = "I am excited to apply to Globex Robotics."
    assert check_document(REAL_CV, letter).unbacked == 1
    with_posting = check_document(REAL_CV, letter, match=match(company="Globex Robotics"))
    assert with_posting.flagged == []
    assert with_posting.masked == ["Globex Robotics"]


def test_the_role_applied_for_is_not_read_as_a_claim() -> None:
    letter = "I am applying for the Staff Reliability Engineer opening."
    assert check_document(REAL_CV, letter, match=match(title="Staff Reliability Engineer")).flagged == []


def test_an_explicit_company_wins_over_the_postings_own() -> None:
    result = check_document(
        REAL_CV, "Writing to Globex.", match=match(company="Globex Robotics PLC"), company="Globex"
    )
    assert result.masked[0] == "Globex"
    assert result.flagged == []


def test_initials_too_short_to_blank_are_left_checked() -> None:
    """Blanking a two-letter name would blank real sentences with it."""
    result = check_document(REAL_CV, "Joined AI Labs in 2024.", match=match(company="AI"))
    assert result.masked == []


def test_a_concept_the_posting_uses_is_borrowable() -> None:
    result = check_document(
        REAL_CV,
        "Comfortable with Stakeholder Management across teams.",
        match=match(reqs=("Stakeholder Management experience",)),
    )
    assert result.flagged == []


def test_a_tool_the_posting_names_is_never_borrowable() -> None:
    result = check_document(
        REAL_CV,
        "Strong Kubernetes background.",
        match=match(reqs=("Kubernetes in production",)),
    )
    assert "Kubernetes" in surfaces(result)


# ─── Shape of the answer ──────────────────────────────────────────────


def test_a_claim_is_quoted_the_way_the_document_spells_it() -> None:
    """Not the lexicon's canonical term — the user never typed that."""
    result = check_document(REAL_CV, "Ran the cluster on k8s.")
    assert surfaces(result) == {"k8s"}


def test_a_claim_does_not_carry_the_sentences_full_stop() -> None:
    result = check_document(REAL_CV, "Worked at Globex.")
    assert "Globex" in surfaces(result)


def test_the_same_word_is_not_listed_twice_for_one_sentence() -> None:
    result = check_document(REAL_CV, "Senior Architect, Globex.")
    written = [claim.surface for claim in result.flagged[0].claims]
    assert len(written) == len(set(written))


def test_the_counts_are_the_denominator_for_the_list() -> None:
    result = check_document(
        REAL_CV,
        "Built payment services in Python.\nRan a 40-person team.\nUsed Kafka daily.",
    )
    assert (result.checked, result.unbacked, len(result.flagged)) == (3, 2, 2)


def test_a_paragraph_is_split_into_sentences_so_the_quote_is_findable() -> None:
    result = check_document(
        REAL_CV,
        "I built payment services in Python. I also cut costs by 60%. Thank you.",
    )
    assert result.checked == 3
    assert [line.text for line in result.flagged] == ["I also cut costs by 60%."]


def test_blanking_a_name_that_ends_in_a_full_stop_keeps_the_sentences_aligned() -> None:
    """The quoted sentence and the checked one must stay the same sentence."""
    result = check_document(
        REAL_CV,
        "I am writing to Globex Inc. I led a team of 30 there.",
        match=match(company="Globex Inc."),
    )
    assert [line.text for line in result.flagged] == ["I led a team of 30 there."]


# ─── Limits and refusals ──────────────────────────────────────────────


def test_an_empty_document_is_refused_rather_than_called_clean() -> None:
    with pytest.raises(EngineError) as raised:
        check_document(REAL_CV, "   \n  ")
    assert raised.value.code == "invalid_args"


def test_a_check_without_a_cv_to_check_against_is_refused() -> None:
    empty = CVDoc(hash="h", detected_language="en", lines=[])
    with pytest.raises(EngineError) as raised:
        check_document(empty, "Anything at all.")
    assert raised.value.code == "cv_too_short"


def test_an_overlong_document_is_cut_and_says_so() -> None:
    result = check_document(REAL_CV, "Built payment services in Python.\n" * 2000)
    assert result.truncated
    assert result.checked <= MAX_UNITS


def test_the_flagged_list_is_capped_but_the_count_is_not() -> None:
    result = check_document(REAL_CV, "Shipped Kafka work.\n" * (MAX_FLAGGED + 12))
    assert len(result.flagged) == MAX_FLAGGED
    assert result.unbacked == MAX_FLAGGED + 12


def test_one_sentence_reports_at_most_a_handful_of_claims() -> None:
    crowded = "At Globex, Initech, Umbrella, Soylent, Tyrell and Cyberdyne I ran 9 teams."
    result = check_document(REAL_CV, crowded)
    assert len(result.flagged[0].claims) <= MAX_CLAIMS_PER_LINE


def test_a_long_document_stays_inside_the_character_budget() -> None:
    assert MAX_CHARS >= 20_000


def test_the_cv_hash_is_the_cv_the_check_was_made_against() -> None:
    assert check_document(REAL_CV, "Anything.").cv_hash == REAL_CV.hash


# ─── The answer loop ──────────────────────────────────────────────────


def test_an_answer_added_to_the_cv_clears_the_finding() -> None:
    """The only repair this screen offers, end to end.

    The app cannot edit the user's file, so the finding clears the way every
    other one in this product does: the person says where it happened, their
    sentence becomes a CV line, and the same check run again has evidence it
    did not have before.
    """
    document = "Ran the production cluster on Kubernetes."
    assert check_document(REAL_CV, document).unbacked == 1

    answered = REAL_CV.model_copy(
        update={
            "lines": [
                *REAL_CV.lines,
                CVLine(
                    id=f"L{len(REAL_CV.lines) + 1}",
                    text="I ran our Kubernetes cluster at Volta Systems.",
                    section="experience",
                    added_at="2026-09-23",
                ),
            ]
        }
    )
    assert check_document(answered, document).flagged == []
