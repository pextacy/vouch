"""The CV audit: what it must catch, and what it must not cry wolf about.

A finding costs the user attention and a little dignity — it says "an
interviewer will press you here". So false positives matter more than in most
code: a tool that flags an ordinary CV teaches people to ignore it, and then it
catches nothing at all. Every rule below is tested in both directions, and the
quiet cases get as much room as the loud ones.

No model is involved anywhere in this file, which is the point: the audit costs
nothing, needs no quota, and works before the user has a posting.
"""

from __future__ import annotations

from receipts_engine.audit import MIN_OVERLAP_YEARS, audit_cv
from receipts_engine.parse.cv import parse_cv
from receipts_engine.schemas import CvAudit, CVDoc


def _cv(*lines: str) -> CVDoc:
    return parse_cv(source="text", text="\n".join(lines) + "\n" + "Filler line. " * 30)


def _subjects(audit: CvAudit, kind: str) -> list[str]:
    return [f.subject for f in audit.findings if f.kind == kind]


HONEST = [
    "Maya Collins",
    "Backend Engineer - Berlin",
    "",
    "Experience",
    "Acme Payments - Backend Engineer, 2018-2024",
    "Built payment reconciliation services in Go for 1,200 merchant accounts.",
    "Migrated the reporting pipeline from MySQL to PostgreSQL with zero downtime.",
    "",
    "Skills",
    "Go, PostgreSQL, MySQL",
]


# ─── A CV that holds together says nothing ────────────────────────────


def test_an_honest_cv_produces_no_findings() -> None:
    audit = audit_cv(_cv(*HONEST))
    assert audit.findings == []


def test_the_audit_is_stamped_with_the_cv_it_read() -> None:
    cv = _cv(*HONEST)
    assert audit_cv(cv).cv_hash == cv.hash


# ─── Skills listed but never shown ────────────────────────────────────


def test_a_skill_listed_but_never_used_is_reported() -> None:
    """The single most probed line on any CV: "where did you use this?"."""
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
            "",
            "Skills",
            "Go, Kubernetes, Terraform",
        )
    )
    assert _subjects(audit, "skill_unevidenced") == ["kubernetes", "terraform"]


def test_a_skill_shown_in_a_project_counts_as_evidenced() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
            "",
            "Projects",
            "Ran a home cluster on Kubernetes for two years.",
            "",
            "Skills",
            "Go, Kubernetes",
        )
    )
    assert _subjects(audit, "skill_unevidenced") == []


def test_a_cv_with_no_skills_section_is_not_audited_for_skills() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
        )
    )
    assert _subjects(audit, "skill_unevidenced") == []


def test_a_cv_that_is_only_a_skills_list_is_left_alone() -> None:
    """It has one problem and this is not it; listing every term is noise."""
    audit = audit_cv(_cv("Maya Collins", "", "Skills", "Go, Kubernetes, Terraform, Kafka"))
    assert _subjects(audit, "skill_unevidenced") == []


# ─── Titles claimed but not carried ───────────────────────────────────


def test_seniority_in_the_header_that_no_role_carries_is_reported() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "Senior Backend Engineer",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
        )
    )
    assert _subjects(audit, "title_unevidenced") == ["senior"]


def test_a_title_the_roles_do_carry_is_not_reported() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "Senior Backend Engineer",
            "",
            "Experience",
            "Acme Payments - Senior Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
        )
    )
    assert _subjects(audit, "title_unevidenced") == []


def test_a_cv_with_no_experience_section_is_not_audited_for_titles() -> None:
    """A new graduate's CV is not lying by having a headline."""
    audit = audit_cv(_cv("Maya Collins", "Junior Developer", "", "Education", "MSc, 2016"))
    assert _subjects(audit, "title_unevidenced") == []


# ─── Dates ────────────────────────────────────────────────────────────


def test_a_range_that_ends_before_it_starts_is_reported() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2024-2018",
            "Built payment reconciliation services in Go.",
        )
    )
    assert _subjects(audit, "date_conflict") == ["2024-2018"]


def test_two_roles_overlapping_for_years_are_reported() -> None:
    """Usually innocent — consulting, a second job — which is why it gets asked."""
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built reconciliation services in Go.",
            "Globex - Consultant, 2019-2023",
            "Advised on payment flows.",
        )
    )
    assert _subjects(audit, "date_conflict") == ["2019-2023"]


def test_a_short_overlap_is_left_alone() -> None:
    """A notice period is not a discrepancy."""
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2021",
            "Built reconciliation services in Go.",
            "Globex - Engineer, 2021-2024",
            "Advised on payment flows.",
        )
    )
    assert _subjects(audit, "date_conflict") == []
    assert MIN_OVERLAP_YEARS == 2


def test_consecutive_roles_are_left_alone() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2015-2018",
            "Built reconciliation services in Go.",
            "Globex - Engineer, 2019-2024",
            "Advised on payment flows.",
        )
    )
    assert _subjects(audit, "date_conflict") == []


def test_an_open_range_is_not_a_conflict_by_itself() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-present",
            "Built reconciliation services in Go.",
        )
    )
    assert _subjects(audit, "date_conflict") == []


# ─── Shape of the report ──────────────────────────────────────────────


def test_a_finding_carries_no_prose() -> None:
    """The sentence is the UI's, in the user's language — same as error codes."""
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built reconciliation services in Go.",
            "",
            "Skills",
            "Go, Kubernetes",
        )
    )
    finding = audit.findings[0]
    assert finding.subject == "kubernetes"
    assert finding.line_ids
    assert " " not in finding.subject, "a subject is a term, never a sentence"


def test_every_cited_line_exists_in_the_cv() -> None:
    cv = _cv(
        "Maya Collins",
        "Senior Backend Engineer",
        "",
        "Experience",
        "Acme Payments - Backend Engineer, 2018-2024",
        "Built reconciliation services in Go.",
        "",
        "Skills",
        "Go, Kubernetes, Terraform",
    )
    known = {line.id for line in cv.lines}
    audit = audit_cv(cv)
    assert audit.findings
    for finding in audit.findings:
        assert set(finding.line_ids) <= known


def test_a_skill_the_cv_rules_out_is_not_a_claim() -> None:
    """The worst mistake this feature could make, and the repo's own fixture has it.

    `SAMPLE_CV_LINES` ends its skills line with "Terraform-free infra" — a claim
    about architecture, stated in order to say Terraform is *not* used. Telling
    someone they cannot back a claim they never made would be worse than saying
    nothing at all.
    """
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
            "",
            "Skills",
            "Go, Terraform-free infra, no Kubernetes",
        )
    )
    assert _subjects(audit, "skill_unevidenced") == []


def test_the_repo_sample_cv_reports_only_what_it_really_leaves_unshown() -> None:
    """A regression guard on noise: real input, and only the fair findings."""
    from ..conftest import SAMPLE_CV_LINES

    audit = audit_cv(parse_cv(source="text", text="\n".join(SAMPLE_CV_LINES)))
    assert _subjects(audit, "skill_unevidenced") == ["kafka", "python"]
    assert _subjects(audit, "title_unevidenced") == []
    assert _subjects(audit, "date_conflict") == []


# ─── Saying it back the way the CV writes it ──────────────────────────


def test_a_finding_carries_the_spelling_the_cv_uses() -> None:
    """`subject` is for comparing, `surface` is for showing.

    Telling someone their skills list names "grpc" when they wrote "gRPC"
    reads as the app not having looked properly — and this app's entire claim
    is that it looked properly.
    """
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
            "",
            "Skills",
            "Go, gRPC, PostgreSQL",
        )
    )
    findings = {f.subject: f.surface for f in audit.findings}
    assert findings == {"grpc": "gRPC", "postgresql": "PostgreSQL"}


def test_a_synonym_is_shown_as_the_cv_wrote_it_not_as_the_lexicon_knows_it() -> None:
    """The case a UI-side workaround cannot get right: k8s is not "kubernetes"."""
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
            "",
            "Skills",
            "Go, k8s",
        )
    )
    finding = next(f for f in audit.findings if f.kind == "skill_unevidenced")
    assert finding.subject == "kubernetes", "grouping still uses the canonical term"
    assert finding.surface == "k8s", "the screen shows what the CV says"


def test_a_title_is_shown_capitalised_the_way_it_was_claimed() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "Senior Backend Engineer",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go.",
        )
    )
    finding = next(f for f in audit.findings if f.kind == "title_unevidenced")
    assert (finding.subject, finding.surface) == ("senior", "Senior")


def test_a_date_span_is_its_own_surface() -> None:
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2024-2018",
            "Built payment reconciliation services in Go.",
        )
    )
    finding = next(f for f in audit.findings if f.kind == "date_conflict")
    assert finding.surface == finding.subject == "2024-2018"


def test_every_finding_has_a_surface() -> None:
    """The UI renders `surface` unconditionally; an empty one would be a hole."""
    audit = audit_cv(
        _cv(
            "Maya Collins",
            "Senior Backend Engineer",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2024-2018",
            "Built reconciliation services in Go.",
            "",
            "Skills",
            "Go, Kubernetes",
        )
    )
    assert audit.findings
    assert all(f.surface for f in audit.findings)
