"""Posting normalisation: keep the requirements, drop the furniture."""

from __future__ import annotations

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.parse.posting import MAX_POSTING_CHARS, normalize_posting


def test_requirements_survive_normalisation(sample_posting: str) -> None:
    posting = normalize_posting(sample_posting)
    assert "5+ years of backend engineering experience" in posting.text


def test_cookie_and_apply_furniture_is_dropped(sample_posting: str) -> None:
    posting = normalize_posting(sample_posting)
    assert "Accept all cookies" not in posting.text
    assert "Apply now" not in posting.text


def test_turkish_furniture_is_dropped() -> None:
    raw = "Kıdemli Yazılım Mühendisi\n" + "Aranan nitelikler: 5 yıl deneyim. " * 8 + "\nŞimdi başvur\nÇerez"
    posting = normalize_posting(raw)
    assert "Şimdi başvur" not in posting.text


def test_bare_urls_are_dropped() -> None:
    raw = "Backend Engineer\nhttps://example.com/jobs/1\n" + "We need Go and Kubernetes. " * 8
    posting = normalize_posting(raw)
    assert "https://example.com" not in posting.text


def test_title_and_company_hints_are_picked_up() -> None:
    raw = (
        "Job title: Staff Platform Engineer\n"
        "Company: Northwind Ledger\n" + "Requirements: Go, Kubernetes, PostgreSQL. " * 6
    )
    posting = normalize_posting(raw)
    assert posting.title_hint == "Staff Platform Engineer"
    assert posting.company_hint == "Northwind Ledger"


def test_hash_is_stable(sample_posting: str) -> None:
    assert normalize_posting(sample_posting).hash == normalize_posting(sample_posting).hash


def test_language_is_detected(sample_posting: str) -> None:
    assert normalize_posting(sample_posting).language == "en"


def test_short_text_is_not_a_posting() -> None:
    with pytest.raises(EngineError) as excinfo:
        normalize_posting("We are hiring!")
    assert excinfo.value.code == "no_requirements_found"


def test_text_that_is_only_furniture_is_not_a_posting() -> None:
    raw = "\n".join(["Accept all cookies", "Privacy policy", "Sign in", "Apply now"] * 12)
    with pytest.raises(EngineError) as excinfo:
        normalize_posting(raw)
    assert excinfo.value.code == "no_requirements_found"


def test_long_posting_is_trimmed() -> None:
    raw = "Backend Engineer\n" + ("We need Go, Kubernetes and PostgreSQL experience. " * 2000)
    posting = normalize_posting(raw)
    assert posting.truncated
    assert len(posting.text) <= MAX_POSTING_CHARS
