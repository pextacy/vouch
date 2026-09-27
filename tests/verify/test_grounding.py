"""Verifier tests — the ones that matter most.

Two kinds of failure are possible and they are not symmetric:

* a **leak** (``ok=True`` for invented content) breaks the product's only
  promise;
* a **false positive** (``ok=False`` for an honest rewrite) silently deletes a
  good suggestion.

Both are tested. When a real leak turns up, the fix is a new case here plus a
narrower rule — never a loosened one.
"""

from __future__ import annotations

import pytest

from receipts_engine.verify import TechLexicon, extract_claims, verify

CV = [
    "Built payment reconciliation services in Go, 2018-2024",
    "Migrated the reporting pipeline to PostgreSQL and k8s",
    "Led a team of 4 engineers at Acme Payments",
    "Reduced settlement errors by 18% across the ledger",
    "MSc Computer Science, Boğaziçi University, 2016",
    "Handled 1,200 merchant accounts during the EU rollout",
]


def ok(text: str, sources: list[str] | None = None, **kwargs: object) -> bool:
    return verify(text, sources or CV, **kwargs).ok  # type: ignore[arg-type]


# ─── Numbers ──────────────────────────────────────────────────────────


def test_invented_percentage_is_rejected() -> None:
    verdict = verify("Increased revenue by 40%", CV)
    assert not verdict.ok
    assert "40%" in verdict.tokens


def test_percentage_present_in_source_passes() -> None:
    assert ok("Cut settlement errors by 18%")


def test_invented_team_size_is_rejected() -> None:
    assert not ok("Led a team of 12 engineers")


def test_real_team_size_passes() -> None:
    assert ok("Led a team of 4 engineers")


def test_thousands_separator_forms_are_equivalent() -> None:
    assert ok("Handled 1200 merchant accounts")


def test_european_thousands_separator_matches() -> None:
    assert ok("Handled 1.200 merchant accounts", ["Handled 1,200 merchant accounts"])


def test_k_suffix_matches_the_written_out_number() -> None:
    assert ok("Served 5k users", ["Served 5000 users"])


def test_written_out_number_matches_a_k_suffix_source() -> None:
    assert ok("Served 5000 users", ["Served 5k users"])


def test_decimal_values_must_match_exactly() -> None:
    assert not ok("Improved latency by 2.5x", ["Improved latency by 2x"])


def test_currency_amount_must_exist_in_source() -> None:
    assert not ok("Owned a $2M budget", CV)


def test_currency_amount_present_in_source_passes() -> None:
    assert ok("Owned a $2M budget", ["Owned a $2M budget for the platform team"])


def test_number_glued_to_a_name_is_not_a_bare_number() -> None:
    # "S3" must not be read as the number 3 — otherwise every mention of S3
    # would demand a literal "3" in the CV.
    claims = extract_claims("Stored exports in S3")
    assert not [claim for claim in claims if claim.kind == "number"]


# ─── Dates and durations ──────────────────────────────────────────────


def test_invented_year_is_rejected() -> None:
    assert not ok("Shipped the ledger rewrite in 2011")


def test_year_present_in_source_passes() -> None:
    assert ok("Shipped the ledger rewrite in 2018")


def test_duration_derivable_from_source_dates_passes() -> None:
    assert ok("5+ years building payment services")


def test_duration_beyond_the_source_dates_is_rejected() -> None:
    assert not ok("12+ years building payment services")


def test_duration_exactly_at_the_span_boundary_passes() -> None:
    assert ok("6 years building payment services")


def test_duration_with_no_dates_in_source_is_rejected() -> None:
    assert not ok("4 years of Go", ["Built services in Go"])


def test_explicit_duration_in_source_passes() -> None:
    assert ok("3 years of Go", ["3 years of Go at a payments company"])


def test_present_end_date_counts_up_to_today() -> None:
    assert ok("2+ years on the platform", ["Platform engineer, 2019 - present"])


def test_month_name_must_appear_in_source() -> None:
    assert not ok("Joined in March", ["Joined in June 2019"])


def test_turkish_month_name_present_in_source_passes() -> None:
    assert ok("Ekim ayında yayına aldım", ["Ekim 2020'de yayına aldım"])


# ─── Technologies ─────────────────────────────────────────────────────


def test_tool_absent_from_cv_is_rejected() -> None:
    verdict = verify("Provisioned infrastructure with Terraform", CV)
    assert not verdict.ok


def test_known_synonym_passes_k8s() -> None:
    assert ok("Deployed to Kubernetes")


def test_known_synonym_passes_postgres() -> None:
    assert ok("Tuned Postgres queries")


def test_synonym_in_the_other_direction_passes() -> None:
    assert ok("Ran workloads on k8s", ["Ran workloads on Kubernetes"])


def test_dotted_tool_name_matches_undotted_source() -> None:
    assert ok("Built the API in Node.js", ["Built the API in nodejs"])


def test_lowercase_tool_not_in_cv_is_still_caught() -> None:
    # The proper-noun rule would miss this; the lexicon is why it is caught.
    assert not ok("deployed with kubernetes", ["Built services in Go"])


def test_ambiguous_word_is_not_treated_as_a_tool() -> None:
    assert ok("Owned the go-to-market plan", ["Owned the launch plan with sales"])


def test_ambiguous_word_capitalised_is_still_a_proper_noun_claim() -> None:
    assert not ok("Wrote services in Go", ["Wrote services in Python"])


def test_multiword_tool_is_matched_as_one_term() -> None:
    assert not ok("Ran jobs on Google Cloud", ["Ran jobs on AWS"])


def test_multiword_tool_present_in_source_passes() -> None:
    assert ok("Ran jobs on Google Cloud", ["Ran jobs on GCP"])


# ─── Proper nouns ─────────────────────────────────────────────────────


def test_invented_employer_is_rejected() -> None:
    assert not ok("Shipped reconciliation at Globex Industries")


def test_real_employer_passes() -> None:
    assert ok("Shipped reconciliation at Acme Payments")


def test_sentence_initial_capital_is_not_a_claim() -> None:
    assert ok("Reduced settlement errors across the ledger")


def test_turkish_dotted_capital_matches_ascii_spelling() -> None:
    assert ok("Studied at Bogazici University", ["MSc, Boğaziçi University"])


def test_turkish_dotless_i_normalises_to_the_same_token() -> None:
    assert ok("ISTANBUL ofisinde çalıştım", ["İstanbul ofisinde çalıştım"])


def test_proper_noun_inside_a_tech_phrase_does_not_leak() -> None:
    # "Acme" must still be checked even though "Kubernetes" is stripped out.
    assert not ok("Ran Acme Kubernetes Corp workloads", CV)


# ─── Titles ───────────────────────────────────────────────────────────


def test_invented_seniority_is_rejected() -> None:
    assert not ok("Senior engineer on the payments team")


def test_real_seniority_passes() -> None:
    assert ok("Senior engineer on the payments team", ["Senior Engineer, Payments"])


def test_turkish_title_is_checked_too() -> None:
    assert not ok("Kıdemli yazılım mühendisi", ["Yazılım mühendisi olarak çalıştım"])


def test_lead_is_a_title_claim() -> None:
    assert not ok("Tech lead for the ledger team", ["Engineer on the ledger team"])


# ─── Rewording is free ────────────────────────────────────────────────


def test_pure_rewording_passes() -> None:
    assert ok("Rebuilt reconciliation for payments", ["Built payment reconciliation services"])


def test_stronger_verb_without_new_facts_passes() -> None:
    assert ok("Drove the reporting pipeline migration", ["Migrated the reporting pipeline"])


def test_posting_vocabulary_may_supply_a_general_concept() -> None:
    assert ok(
        "Partnered with Stakeholders across the business",
        ["Worked with product and sales teams"],
        posting_vocab=["Stakeholder management across the business"],
    )


def test_posting_vocabulary_may_not_supply_a_tool() -> None:
    assert not ok(
        "Deployed to Kubernetes",
        ["Deployed services to a container platform"],
        posting_vocab=["Kubernetes in production"],
    )


def test_posting_vocabulary_may_not_supply_a_tool_the_lexicon_never_heard_of() -> None:
    """The leak the concept list closed.

    The rule used to be "allowed unless the lexicon knows it", so a product the
    lexicon had never heard of was allowed *because* it was unknown — and a
    posting names the tools it wants. Every new SaaS name reopened the hole.
    """
    assert not ok(
        "Administered Zyntherio for the sales team",
        ["Administered the CRM for the sales team"],
        posting_vocab=["Zyntherio administration"],
    )


def test_posting_vocabulary_may_not_supply_an_employer() -> None:
    assert not ok(
        "Built payment services at Globex",
        ["Built payment reconciliation services"],
        posting_vocab=["Experience of the scale Globex operates at"],
    )


def test_posting_vocabulary_may_still_supply_a_turkish_concept() -> None:
    assert ok(
        "Paydaşlarla birlikte raporlama süreçlerini yürüttüm",
        ["Ürün ve satış ekipleriyle rapor hazırladım"],
        posting_vocab=["Paydaş yönetimi ve raporlama"],
    )


def test_posting_vocabulary_may_not_supply_a_number() -> None:
    assert not ok(
        "Delivered 99.9% uptime",
        ["Kept the service available"],
        posting_vocab=["99.9% uptime SLA"],
    )


def test_posting_vocabulary_may_not_supply_a_title() -> None:
    assert not ok(
        "Senior engineer on payments",
        ["Engineer on payments"],
        posting_vocab=["Senior Backend Engineer"],
    )


# ─── Unit collisions ──────────────────────────────────────────────────
#
# The number is only half of the fact. Before these cases the verifier keyed a
# claim on the value alone, so any 40 in the CV vouched for "40%" — the exact
# fabrication the product exists to stop, licensed by a coincidence.


@pytest.mark.parametrize(
    ("generated", "source"),
    [
        ("Improved conversion by 40%", ["Worked 40 hours a week on checkout"]),
        ("Cut infrastructure cost by 30%", ["Managed a team of 30 engineers"]),
        ("Reduced latency to 250ms", ["Handled 250 requests per second"]),
        ("Shipped 5 features", ["Worked 5 years in backend"]),
        ("Owned a $2M budget", ["Reviewed 2M log lines a day"]),
    ],
)
def test_a_number_with_a_different_unit_is_not_evidence(
    generated: str, source: list[str]
) -> None:
    assert not ok(generated, source)


@pytest.mark.parametrize(
    ("generated", "source"),
    [
        ("Cut errors by 18 percent", ["Reduced settlement errors by 18%"]),
        ("Yüzde 18 hata azalttım", ["Reduced settlement errors by 18%"]),
        ("Cut p95 latency to 250 ms", ["Reduced p95 latency from 800ms to 250ms"]),
        ("Spent 5 saat a day on reconciliation", ["Spent 5 hours a day on reconciliation"]),
        ("Led a team of 4 engineers", ["Led a team of 4 developers at Acme"]),
    ],
)
def test_the_same_fact_in_another_wording_still_passes(
    generated: str, source: list[str]
) -> None:
    assert ok(generated, source)


# ─── Word boundaries ──────────────────────────────────────────────────


def test_a_longer_word_does_not_evidence_a_shorter_name() -> None:
    assert not ok("Led engineering at Meta", ["Owned metadata pipelines for the catalogue"])


def test_a_longer_word_does_not_evidence_a_title() -> None:
    assert not ok("Senior engineer on payments", ["Engineer with seniority in payments"])


def test_turkish_case_suffix_without_an_apostrophe_still_evidences_the_name() -> None:
    assert ok("Ankara ofisini kurdum", ["Ankarada yeni ofisi kurdum"])


def test_spelling_only_difference_still_passes() -> None:
    assert ok("Built services with Node js", ["Built services with Node.js and Postgres"])


# ─── Shape and edges ──────────────────────────────────────────────────


def test_empty_generated_text_is_trivially_ok() -> None:
    assert verify("", CV).ok


def test_whitespace_only_text_is_trivially_ok() -> None:
    assert verify("   \n  ", CV).ok


def test_empty_sources_reject_any_factual_claim() -> None:
    assert not verify("Led 4 engineers at Acme", []).ok


def test_verdict_tokens_are_deduplicated_and_ordered() -> None:
    verdict = verify("Grew revenue 40% and margin 40% at Globex", CV)
    assert verdict.tokens.count("40%") == 1


def test_unsupported_claims_carry_their_kind() -> None:
    verdict = verify("Increased revenue by 40%", CV)
    assert {claim.kind for claim in verdict.unsupported} == {"number"}


def test_a_custom_lexicon_replaces_the_default() -> None:
    lexicon = TechLexicon({"widgetron": ("wgt",)})
    assert not verify("Built it on Widgetron", ["Built it on other tooling"], lexicon=lexicon).ok
    assert verify("Built it on Widgetron", ["Built it with wgt"], lexicon=lexicon).ok


@pytest.mark.parametrize(
    "text",
    [
        "Cut costs by 30%",
        "Managed 15 direct reports",
        "Delivered in 2015",
        "Certified in AWS",
        "Worked at Initech",
    ],
)
def test_common_fabrications_are_all_rejected(text: str) -> None:
    assert not ok(text)


# ─── Sentence openers are grammar, not employers ──────────────────────
#
# The sentence-initial rule forgives a single capitalised word, which left
# "Since I applied…" — the natural first line of a follow-up note — read as a
# two-word proper noun and dropped a paragraph that was fully grounded. The
# rule is narrower by exactly the function words below, so a phrase is only
# discarded when *every* word in it is one of them.


@pytest.mark.parametrize(
    "text",
    [
        "Since I migrated the reporting pipeline to PostgreSQL",
        "After I migrated the reporting pipeline to PostgreSQL",
        "While I migrated the reporting pipeline to PostgreSQL",
        "Recently I migrated the reporting pipeline to PostgreSQL",
    ],
)
def test_a_sentence_opener_before_a_pronoun_is_not_a_proper_noun(text: str) -> None:
    assert ok(text)


@pytest.mark.parametrize(
    "text",
    [
        "Since Globex I migrated the reporting pipeline to PostgreSQL",
        "After Initech I migrated the reporting pipeline to PostgreSQL",
        "Since the merger with Umbrella I migrated the pipeline",
    ],
)
def test_an_employer_after_the_opener_is_still_a_claim(text: str) -> None:
    assert not ok(text)
