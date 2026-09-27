"""CV parsing: ids, sections, warnings, and the four ways a file can fail."""

from __future__ import annotations

import io
import zipfile

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.parse.cv import (
    MAX_CV_CHARS,
    MAX_DOCX_MEMBERS,
    MAX_DOCX_UNPACKED_BYTES,
    MAX_FILE_BYTES,
    MAX_PDF_PAGES,
    parse_cv,
)

from ..conftest import SAMPLE_CV_LINES, build_docx, build_pdf


def test_text_source_produces_sequential_line_ids(sample_cv_text: str) -> None:
    doc = parse_cv(source="text", text=sample_cv_text)
    assert [line.id for line in doc.lines] == [f"L{n}" for n in range(1, len(doc.lines) + 1)]


def test_sections_are_detected_from_headings(sample_cv_text: str) -> None:
    doc = parse_cv(source="text", text=sample_cv_text)
    sections = {line.section for line in doc.lines}
    assert {"experience", "education", "skills"} <= sections


def test_heading_lines_are_not_kept_as_content(sample_cv_text: str) -> None:
    doc = parse_cv(source="text", text=sample_cv_text)
    assert all(line.text.strip().lower() != "experience" for line in doc.lines)


def test_experience_bullets_land_in_the_experience_section(sample_cv_text: str) -> None:
    doc = parse_cv(source="text", text=sample_cv_text)
    experience = [line.text for line in doc.lines if line.section == "experience"]
    assert any("reconciliation" in text for text in experience)


def test_hash_is_stable_across_identical_input(sample_cv_text: str) -> None:
    assert parse_cv(source="text", text=sample_cv_text).hash == parse_cv(
        source="text", text=sample_cv_text
    ).hash


def test_hash_changes_when_content_changes(sample_cv_text: str) -> None:
    other = sample_cv_text.replace("18%", "19%")
    assert parse_cv(source="text", text=sample_cv_text).hash != parse_cv(
        source="text", text=other
    ).hash


def test_bullet_markers_are_stripped() -> None:
    doc = parse_cv(source="text", text="Experience\n" + "\n".join(f"- Item {n} of the list" for n in range(12)))
    assert all(not line.text.startswith("-") for line in doc.lines)


def test_wrapped_lines_are_rejoined() -> None:
    text = "Experience\nLed the migration of the billing\nplatform to a new provider.\n" + "x" * 200
    doc = parse_cv(source="text", text=text)
    joined = " ".join(line.text for line in doc.lines)
    assert "billing platform" in joined


def test_empty_text_is_rejected() -> None:
    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="text", text="   ")
    assert excinfo.value.code == "cv_too_short"


def test_short_text_is_rejected() -> None:
    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="text", text="Just a name and a phone number")
    assert excinfo.value.code == "cv_too_short"


def test_unknown_source_is_an_argument_error() -> None:
    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="rtf", text="x" * 400)
    assert excinfo.value.code == "invalid_args"


def test_language_detection_marks_turkish() -> None:
    turkish = (
        "Deneyim\n"
        "Acme Ödeme - Yazılım Mühendisi, 2018-2024\n"
        "Ödeme mutabakat servislerini geliştirdim ve ekip ile çalıştım.\n"
        "Raporlama hattını PostgreSQL üzerine taşıdım.\n"
        "Eğitim\n"
        "Bilgisayar Mühendisliği yüksek lisans, 2016\n"
        "Beceriler\n"
        "Go, Python, PostgreSQL, Kubernetes\n"
    )
    assert parse_cv(source="text", text=turkish).detected_language == "tr"


def test_long_cv_is_truncated_with_a_warning() -> None:
    long_text = "Experience\n" + "\n".join(
        f"Delivered project number {n} for the platform team." for n in range(2000)
    )
    doc = parse_cv(source="text", text=long_text)
    assert "truncated" in doc.warnings
    assert sum(len(line.text) for line in doc.lines) <= MAX_CV_CHARS


# ─── PDF ──────────────────────────────────────────────────────────────


def test_pdf_text_is_extracted() -> None:
    doc = parse_cv(source="pdf", data=build_pdf(SAMPLE_CV_LINES))
    joined = " ".join(line.text for line in doc.lines)
    assert "reconciliation" in joined


def test_multi_page_pdf_keeps_every_page() -> None:
    doc = parse_cv(source="pdf", data=build_pdf(SAMPLE_CV_LINES, pages=2))
    joined = " ".join(line.text for line in doc.lines)
    assert "Bogazici" in joined


def test_oversized_file_is_rejected_before_parsing() -> None:
    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="pdf", data=b"%PDF-1.4" + b"0" * (MAX_FILE_BYTES + 1))
    assert excinfo.value.code == "file_too_large"


def test_corrupt_pdf_is_unreadable() -> None:
    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="pdf", data=b"not a pdf at all, just bytes" * 10)
    assert excinfo.value.code == "unreadable_file"


def test_image_only_pdf_is_unreadable_not_short() -> None:
    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="pdf", data=build_pdf([]))
    assert excinfo.value.code == "unreadable_file"


def test_narrow_columns_raise_the_multi_column_warning() -> None:
    columnar = [f"Item {n}" for n in range(40)]
    doc = parse_cv(source="pdf", data=build_pdf(columnar + ["x" * 300]))
    assert "multi_column_suspected" in doc.warnings


def test_pdf_without_bytes_is_an_argument_error() -> None:
    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="pdf")
    assert excinfo.value.code == "invalid_args"


# ─── DOCX ─────────────────────────────────────────────────────────────


def test_docx_paragraphs_are_extracted() -> None:
    doc = parse_cv(source="docx", data=build_docx(SAMPLE_CV_LINES))
    joined = " ".join(line.text for line in doc.lines)
    assert "reconciliation" in joined


def test_docx_tables_are_flattened_with_a_warning() -> None:
    data = build_docx(
        SAMPLE_CV_LINES,
        table=[["Go", "PostgreSQL"], ["Kubernetes", "Kafka"]],
    )
    doc = parse_cv(source="docx", data=data)
    assert "tables_flattened" in doc.warnings
    joined = " ".join(line.text for line in doc.lines)
    assert "Kubernetes" in joined


def test_corrupt_docx_is_unreadable() -> None:
    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="docx", data=b"PK\x03\x04 but not really a docx" * 20)
    assert excinfo.value.code == "unreadable_file"


# ─── Bombs and blow-ups ───────────────────────────────────────────────


def test_a_pdf_with_absurdly_many_pages_is_truncated_not_read_whole() -> None:
    """`parse_cv` runs on the synchronous channel, so the page count is a budget.

    A real CV's content sits in its first pages, so the honest answer is to
    read those and say the document was truncated — not to refuse a file whose
    exporter appended a hundred blank pages.
    """
    data = build_pdf(SAMPLE_CV_LINES * 40, pages=MAX_PDF_PAGES + 20)
    doc = parse_cv(source="pdf", data=data)
    assert "truncated" in doc.warnings
    assert doc.lines


def test_a_pdf_within_the_page_budget_is_not_flagged() -> None:
    doc = parse_cv(source="pdf", data=build_pdf(SAMPLE_CV_LINES * 4, pages=4))
    assert "truncated" not in doc.warnings


def test_a_docx_that_unpacks_to_gigabytes_is_refused() -> None:
    """The 2 MB upload cap says nothing about what parsing it costs.

    python-docx parses the expansion, and a zip of repeated bytes expands by
    three orders of magnitude. This is the one shape of file that is small on
    the wire and ruinous in memory.
    """
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", b"A" * (MAX_DOCX_UNPACKED_BYTES + 1))

    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="docx", data=bomb.getvalue())
    assert excinfo.value.code == "file_too_large"


def test_a_docx_with_thousands_of_members_is_refused() -> None:
    crowded = io.BytesIO()
    with zipfile.ZipFile(crowded, "w", zipfile.ZIP_DEFLATED) as archive:
        for index in range(MAX_DOCX_MEMBERS + 1):
            archive.writestr(f"word/media/{index}.bin", b"x")

    with pytest.raises(EngineError) as excinfo:
        parse_cv(source="docx", data=crowded.getvalue())
    assert excinfo.value.code == "file_too_large"


def test_an_ordinary_docx_still_passes_the_guard() -> None:
    doc = parse_cv(source="docx", data=build_docx(SAMPLE_CV_LINES))
    assert doc.lines
