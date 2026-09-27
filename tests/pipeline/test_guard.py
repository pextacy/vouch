"""The guard on the primary function.

Every other generated claim in this app meets a deterministic rule before a
user sees it. The verdict on the match map — the receipt the product is named
after — did not, and the eval has been printing the cost as the false-`strong`
rate. These tests are that rule.

They come in pairs on purpose. A guard that downgrades a correct verdict is
worse than no guard at all: it would teach people that "Related" means "the app
got confused", and the one screen this product exists to show would stop being
read. So for every case where a `strong` has to fall, there is a case beside it
where it must not move.
"""

from __future__ import annotations

from receipts_engine.pipeline.match import MAX_CITED_LINES, guard_citations
from receipts_engine.schemas import CVDoc, CVLine, Evidence, Requirement


def cv(*texts: str) -> CVDoc:
    return CVDoc(
        hash="cv-1",
        detected_language="en",
        lines=[
            CVLine(id=f"L{index}", text=text, section="experience")
            for index, text in enumerate(texts, start=1)
        ],
    )


def requirement(text: str, id_: str = "R1") -> Requirement:
    return Requirement(id=id_, text=text, kind="must", category="skill", source_quote=text)


def evidence(status: str, *line_ids: str, why: str = "The CV shows it.", id_: str = "R1") -> Evidence:
    return Evidence(
        requirement_id=id_,
        status=status,  # type: ignore[arg-type]
        line_ids=list(line_ids),
        why=why,
    )


def guard(doc: CVDoc, reqs: list[Requirement], items: list[Evidence]):
    return guard_citations(doc, reqs, items)


# ─── A verdict the citation actually backs ────────────────────────────


def test_a_cited_line_that_shows_the_technology_is_left_alone() -> None:
    doc = cv("Ran the settlement workers on Kubernetes across two regions.")
    kept, report = guard(doc, [requirement("Kubernetes in production")], [evidence("strong", "L1")])

    assert kept[0].status == "strong"
    assert kept[0].line_ids == ["L1"]
    assert kept[0].why == "The CV shows it."
    assert report.total == 0


def test_a_synonym_counts_as_showing_it() -> None:
    """The lexicon is the point: "k8s" and "Kubernetes" are one demand."""
    doc = cv("Ran the settlement workers on k8s across two regions.")
    kept, report = guard(doc, [requirement("Kubernetes in production")], [evidence("strong", "L1")])

    assert kept[0].status == "strong"
    assert report.unproven == 0


def test_a_requirement_naming_nothing_checkable_is_never_touched() -> None:
    """The model is better at concepts than any lexicon, and keeps them."""
    doc = cv("Led a team of four engineers and owned the on-call rotation.")
    kept, report = guard(
        doc, [requirement("Experience leading a small team")], [evidence("strong", "L1")]
    )

    assert kept[0].status == "strong"
    assert report.total == 0


def test_a_title_in_the_requirement_is_not_a_demand() -> None:
    """"Lead a team" against "Led a team" is the same fact, not the same word.

    Demanding titles would downgrade correct verdicts wholesale, which is the
    one failure this guard must not have.
    """
    doc = cv("Led a team of four engineers.")
    kept, report = guard(doc, [requirement("Lead a small team")], [evidence("strong", "L1")])

    assert kept[0].status == "strong"
    assert report.total == 0


def test_a_duration_in_the_requirement_is_not_a_demand() -> None:
    doc = cv("Backend Engineer, Volta Systems, 2019-2023")
    kept, report = guard(
        doc, [requirement("5+ years of backend experience")], [evidence("strong", "L1")]
    )

    assert kept[0].status == "strong"
    assert report.total == 0


# ─── A citation pointed at the wrong line ─────────────────────────────


def test_a_citation_is_repaired_when_the_cv_shows_it_somewhere_else() -> None:
    doc = cv(
        "Built payment services in Go.",
        "Ran the settlement workers on Kubernetes across two regions.",
    )
    kept, report = guard(doc, [requirement("Kubernetes in production")], [evidence("strong", "L1")])

    assert kept[0].status == "strong"
    assert kept[0].line_ids == ["L1", "L2"]
    assert report.repaired == 1
    assert report.unproven == 0


def test_a_repair_survives_a_citation_that_was_already_full() -> None:
    """The proving line is what the verdict now rests on; it is not trimmed."""
    doc = cv(
        "Built payment services in Go.",
        "Migrated the reporting pipeline to PostgreSQL.",
        "Owned the on-call rotation.",
        "Ran the settlement workers on Kubernetes.",
    )
    kept, report = guard(
        doc, [requirement("Kubernetes in production")], [evidence("strong", "L1", "L2", "L3")]
    )

    assert len(kept[0].line_ids) <= MAX_CITED_LINES
    assert "L4" in kept[0].line_ids
    assert report.repaired == 1


def test_a_repair_needs_every_demanded_term_to_turn_up() -> None:
    """Half a repair is not a repair — the verdict still cannot be backed."""
    doc = cv(
        "Built payment services in Go.",
        "Ran the settlement workers on Kubernetes.",
    )
    kept, report = guard(
        doc, [requirement("Kubernetes and Terraform in production")], [evidence("strong", "L1")]
    )

    assert kept[0].status == "partial"
    assert report.unproven == 1


# ─── A verdict the CV cannot back at all ──────────────────────────────


def test_a_strong_the_cv_never_shows_falls_to_related() -> None:
    doc = cv("Ran the settlement workers on ECS across two regions.")
    kept, report = guard(doc, [requirement("Kubernetes in production")], [evidence("strong", "L1")])

    assert kept[0].status == "partial"
    assert kept[0].line_ids == ["L1"]
    assert report.unproven == 1


def test_the_models_sentence_goes_with_the_strength_it_described() -> None:
    doc = cv("Ran the settlement workers on ECS.")
    kept, _ = guard(
        doc,
        [requirement("Kubernetes in production")],
        [evidence("strong", "L1", why="The CV shows Kubernetes in production.")],
    )

    assert kept[0].why == ""


def test_the_unshown_term_is_recorded_as_the_posting_writes_it() -> None:
    """Not the lexicon's spelling: the user never read the word "kubernetes"."""
    doc = cv("Ran the settlement workers on ECS.")
    kept, _ = guard(doc, [requirement("Production experience with K8s")], [evidence("strong", "L1")])

    assert kept[0].unshown == ["K8s"]


def test_a_partial_verdict_is_left_where_it_is() -> None:
    """`partial` already claims adjacency and nothing more."""
    doc = cv("Ran the settlement workers on ECS.")
    kept, report = guard(
        doc, [requirement("Kubernetes in production")], [evidence("partial", "L1")]
    )

    assert kept[0].status == "partial"
    assert kept[0].unshown == []
    assert report.unproven == 0


def test_a_missing_verdict_is_left_where_it_is() -> None:
    doc = cv("Ran the settlement workers on ECS.")
    kept, report = guard(
        doc, [requirement("Kubernetes in production")], [evidence("missing", why="")]
    )

    assert kept[0].status == "missing"
    assert report.unproven == 0


# ─── The older rule, still standing ───────────────────────────────────


def test_an_invented_citation_still_empties_the_verdict() -> None:
    doc = cv("Ran the settlement workers on Kubernetes.")
    kept, report = guard(doc, [requirement("Kubernetes in production")], [evidence("strong", "L9")])

    assert kept[0].status == "missing"
    assert kept[0].line_ids == []
    assert report.invented == 1


def test_a_citation_on_a_missing_verdict_is_still_a_contradiction() -> None:
    doc = cv("Ran the settlement workers on Kubernetes.")
    kept, _ = guard(doc, [requirement("Kubernetes in production")], [evidence("missing", "L1")])

    assert kept[0].line_ids == []


def test_the_report_counts_and_says_nothing_about_the_cv() -> None:
    doc = cv(
        "Ran the settlement workers on ECS.",
        "Migrated the reporting pipeline to PostgreSQL.",
    )
    _, report = guard(
        doc,
        [
            requirement("Kubernetes in production", "R1"),
            requirement("PostgreSQL and schema migrations", "R2"),
        ],
        [evidence("strong", "L1", id_="R1"), evidence("strong", "L1", id_="R2")],
    )

    assert (report.invented, report.repaired, report.unproven) == (0, 1, 1)
    assert report.total == 2


def test_a_word_the_lexicon_calls_ambiguous_is_not_a_demand() -> None:
    """"Go in production" is a demand; "go to production" is a sentence.

    The lexicon refuses to read a lone ambiguous word as a technology, and the
    guard inherits that refusal rather than second-guessing it — a requirement
    the model matched on the word "go" must not cost someone a verdict.
    """
    doc = cv("Ran the settlement workers on ECS.")
    kept, report = guard(doc, [requirement("Go in production")], [evidence("strong", "L1")])

    assert kept[0].status == "strong"
    assert report.total == 0
