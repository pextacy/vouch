"""Taking the CV back out.

Three screens write the user's own sentences into the stored CV, and this is
the only way any of them reaches the document an employer reads. Two things
therefore have to hold, and they are the two this file is about.

**Not one word may change.** The text in the document is the text in the CV,
byte for byte. An export that tidied a sentence would be the app editing
someone's account of their own career — the same line it refuses to cross
when it writes a bullet.

**It has to come out in reading order.** Answers are appended to the end of
``lines``, so printing in stored order would put a new job under the skills
list and hand the user a document they cannot send.

No model anywhere in this file.
"""

from __future__ import annotations

import base64
import io

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.export import build_cv_docx
from receipts_engine.schemas import CVDoc, CVLine

ADDED = "2026-09-20T10:00:00+00:00"


def _line(id_: str, text: str, section: str = "experience", added: str | None = None) -> CVLine:
    return CVLine(id=id_, text=text, section=section, added_at=added)  # type: ignore[arg-type]


def _cv(*lines: CVLine) -> CVDoc:
    return CVDoc(hash="cv-1", lines=list(lines), detected_language="en")


def _read(b64: str) -> list[tuple[str, str]]:
    """``(style, text)`` for every paragraph in the rendered document."""
    import docx

    document = docx.Document(io.BytesIO(base64.b64decode(b64)))
    return [(p.style.name, p.text) for p in document.paragraphs]


SAMPLE = _cv(
    _line("L1", "Dilek Aydın — Backend Engineer, Istanbul", section="header"),
    _line("L2", "Acme Payments — Backend Engineer, 2018–2024"),
    _line("L3", "Built payment reconciliation services in Go for 1,200 merchants."),
    _line("L4", "MSc Computer Science, Boğaziçi University, 2016", section="education"),
    _line("L5", "Go, Python, PostgreSQL", section="skills"),
    _line("L6", "I ran the Kafka consumers behind the payout feed for two years.", added=ADDED),
)


# ─── Nothing is rewritten ─────────────────────────────────────────────


def test_every_line_appears_exactly_as_the_cv_stores_it() -> None:
    _, content, lines = build_cv_docx(cv=SAMPLE, mode="full", locale="en")
    rendered = [text for _, text in _read(content)]

    assert lines == len(SAMPLE.lines)
    for line in SAMPLE.lines:
        assert line.text in rendered, line.id


def test_the_document_adds_no_sentence_of_its_own() -> None:
    """A full CV goes to an employer: no footer, no signature, no note."""
    _, content, _ = build_cv_docx(cv=SAMPLE, mode="full", locale="en")
    own = {line.text for line in SAMPLE.lines}
    extra = [text for style, text in _read(content) if text and text not in own]

    assert extra == ["Experience", "Education", "Skills"]
    assert not any("Receipts" in text for _, text in _read(content))


# ─── Reading order ────────────────────────────────────────────────────


def test_an_added_line_prints_inside_its_own_section_not_at_the_end() -> None:
    texts = [text for _, text in _read(build_cv_docx(cv=SAMPLE, mode="full", locale="en")[1])]

    added = texts.index("I ran the Kafka consumers behind the payout feed for two years.")
    assert added < texts.index("Education")
    assert added > texts.index("Experience")


def test_sections_come_out_in_reading_order() -> None:
    texts = [text for style, text in _read(build_cv_docx(cv=SAMPLE, mode="full")[1]) if text]

    assert texts[0] == "Dilek Aydın — Backend Engineer, Istanbul"
    assert texts.index("Experience") < texts.index("Education") < texts.index("Skills")


def test_the_header_gets_no_heading_above_it() -> None:
    rendered = _read(build_cv_docx(cv=SAMPLE, mode="full")[1])
    assert rendered[0] == ("Normal", "Dilek Aydın — Backend Engineer, Istanbul")


def test_lines_keep_their_order_within_a_section() -> None:
    texts = [text for _, text in _read(build_cv_docx(cv=SAMPLE, mode="full")[1])]
    assert texts.index("Acme Payments — Backend Engineer, 2018–2024") < texts.index(
        "Built payment reconciliation services in Go for 1,200 merchants."
    )


# ─── Only what the user added ─────────────────────────────────────────


def test_additions_carry_the_added_lines_and_nothing_else() -> None:
    _, content, lines = build_cv_docx(cv=SAMPLE, mode="additions", locale="en")
    texts = [text for _, text in _read(content) if text]

    assert lines == 1
    assert "I ran the Kafka consumers behind the payout feed for two years." in texts
    assert "Built payment reconciliation services in Go for 1,200 merchants." not in texts


def test_the_additions_sheet_says_what_it_is() -> None:
    """It is a worksheet for the user, not a document for an employer."""
    _, content, _ = build_cv_docx(cv=SAMPLE, mode="additions", locale="en")
    texts = [text for _, text in _read(content)]
    assert any("Receipts" in text and "rewritten" in text for text in texts)


def test_additions_are_refused_when_the_user_has_added_nothing() -> None:
    parsed_only = _cv(_line("L1", "Acme Payments — Backend Engineer, 2018–2024"))
    with pytest.raises(EngineError) as raised:
        build_cv_docx(cv=parsed_only, mode="additions")
    assert raised.value.code == "invalid_args"


# ─── Both languages ───────────────────────────────────────────────────


def test_turkish_headings_are_turkish() -> None:
    texts = [text for _, text in _read(build_cv_docx(cv=SAMPLE, mode="full", locale="tr")[1])]
    assert "Deneyim" in texts
    assert "Experience" not in texts


def test_the_filename_names_the_two_documents_apart() -> None:
    full, _, _ = build_cv_docx(cv=SAMPLE, mode="full")
    additions, _, _ = build_cv_docx(cv=SAMPLE, mode="additions")
    assert full.startswith("cv-") and full.endswith(".docx")
    assert additions.startswith("cv-additions-")
