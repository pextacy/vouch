"""CV → :class:`CVDoc`: stable numbered lines the model can cite by id.

The model never sees the CV as prose. It sees ``L12: Built payment
reconciliation services`` and answers with ids, which the engine then checks
against the document. That indirection is what makes a fabricated citation
detectable rather than plausible.

Nothing here calls the model, and nothing here writes to disk: a CV is parsed
in memory and handed straight back to the UI, which stores it in the user's own
Anna storage.
"""

from __future__ import annotations

import io
import re
from typing import Final

from ..errors import EngineError
from ..schemas import CVDoc, CVLine, Language, Section, Warning
from ..text import clean, detect_language, sha256_of, strip_bullet, trim_to_chars

#: Hard input ceiling (``docs/prd.md §F1``). Also the point past which base64 chunk
#: upload stops being reasonable.
MAX_FILE_BYTES: Final[int] = 2 * 1024 * 1024

#: Below this a "CV" is a fragment, and matching it produces noise dressed up
#: as a result.
MIN_CV_CHARS: Final[int] = 200

#: Keeps ``run_match`` args inside the host's 64 KB async-invoke cap and the
#: CV inside its ~6k-token share of the sampling budget.
MAX_CV_CHARS: Final[int] = 24_000

_SECTION_PATTERNS: Final[list[tuple[Section, re.Pattern[str]]]] = [
    (
        "experience",
        re.compile(
            r"^\s*(work\s+)?(experience|employment|professional\s+experience|career|"
            r"work\s+history|deneyim|i(ş|s)\s+deneyimi|tecr(ü|u)be|(ç|c)al(ı|i)(ş|s)ma\s+ge(ç|c)mi(ş|s)i)"
            r"\s*:?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "education",
        re.compile(
            r"^\s*(education|academic|qualifications|e(ğ|g)itim|(ö|o)(ğ|g)renim|akademik)\s*:?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "skills",
        re.compile(
            r"^\s*(technical\s+)?(skills|competencies|technologies|tech\s+stack|tools|"
            r"beceriler|yetenekler|yetkinlikler|teknolojiler|teknik\s+beceriler)\s*:?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "projects",
        re.compile(r"^\s*(projects|selected\s+projects|portfolio|projeler)\s*:?\s*$", re.IGNORECASE),
    ),
    (
        "certifications",
        re.compile(
            r"^\s*(certifications?|licenses?|courses|awards|sertifika(lar)?|"
            r"kurslar|(ö|o)d(ü|u)ller)\s*:?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "summary",
        re.compile(
            r"^\s*(summary|profile|about( me)?|objective|professional\s+summary|"
            r"(ö|o)zet|hakk(ı|i)mda|profil|kariyer\s+hedefi)\s*:?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "other",
        re.compile(
            r"^\s*(languages|interests|hobbies|references|volunteer|publications|"
            r"diller|ilgi\s+alanlar(ı|i)|referanslar|g(ö|o)n(ü|u)ll(ü|u)|yay(ı|i)nlar)\s*:?\s*$",
            re.IGNORECASE,
        ),
    ),
]

_CONTINUATION_RE: Final[re.Pattern[str]] = re.compile(r"[,;:\-–—/&(]$|\b(and|ve|ile|with|for)$", re.IGNORECASE)
_ENDS_SENTENCE_RE: Final[re.Pattern[str]] = re.compile(r"[.!?:;]$")


def parse_cv(
    *,
    source: str,
    text: str | None = None,
    data: bytes | None = None,
    filename: str | None = None,
) -> CVDoc:
    """Parse a CV from pasted text, a PDF or a DOCX into a :class:`CVDoc`."""
    warnings: list[Warning] = []

    if source == "text":
        if not text or not text.strip():
            raise EngineError("cv_too_short")
        raw = text
    elif source in {"pdf", "docx"}:
        if data is None:
            raise EngineError("invalid_args", f"{source} source needs file bytes")
        if len(data) > MAX_FILE_BYTES:
            raise EngineError("file_too_large", details={"bytes": len(data)})
        raw = _extract_pdf(data) if source == "pdf" else _extract_docx(data, warnings)
    else:
        raise EngineError("invalid_args", f"unknown source {source!r}")

    cleaned = clean(raw)
    if len(cleaned) < MIN_CV_CHARS:
        # An image-only PDF yields a handful of stray glyphs, which is a
        # different problem from a genuinely thin CV — say which one it is.
        if source == "pdf" and len(cleaned) < 40:
            raise EngineError("unreadable_file", details={"chars": len(cleaned)})
        raise EngineError("cv_too_short", details={"chars": len(cleaned)})

    if source == "pdf" and _looks_multi_column(cleaned):
        warnings.append("multi_column_suspected")

    trimmed, was_trimmed = trim_to_chars(cleaned, MAX_CV_CHARS)
    if was_trimmed:
        warnings.append("truncated")

    lines = _to_lines(trimmed)
    if not lines:
        raise EngineError("unreadable_file")

    language = detect_language(trimmed)
    return CVDoc(
        hash=sha256_of(trimmed),
        lines=lines,
        detected_language=_as_language(language),
        warnings=sorted(set(warnings)),
    )


def _as_language(value: str) -> Language:
    return "tr" if value == "tr" else "en" if value == "en" else "other"


# ─── Extraction ───────────────────────────────────────────────────────


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # An empty user password is common on "protected" exports and
            # decrypts silently; a real password is unreadable for us.
            try:
                if reader.decrypt("") == 0:
                    raise EngineError("unreadable_file", "the PDF is password protected")
            except EngineError:
                raise
            except Exception as exc:
                raise EngineError("unreadable_file", "the PDF is password protected") from exc
        pages = [page.extract_text() or "" for page in reader.pages]
    except EngineError:
        raise
    except (PdfReadError, ValueError, OSError) as exc:
        raise EngineError("unreadable_file", details={"reason": type(exc).__name__}) from exc
    return "\n".join(pages)


def _extract_docx(data: bytes, warnings: list[Warning]) -> str:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises a grab-bag of types
        raise EngineError("unreadable_file", details={"reason": type(exc).__name__}) from exc

    parts: list[str] = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = Paragraph(child, document).text.strip()
            if text:
                parts.append(text)
        elif tag == "tbl":
            table = Table(child, document)
            flattened = _flatten_table(table)
            if flattened:
                parts.extend(flattened)
                if "tables_flattened" not in warnings:
                    warnings.append("tables_flattened")
    return "\n".join(parts)


def _flatten_table(table: object) -> list[str]:
    """A table row becomes one line: skills grids are the common case."""
    rows: list[str] = []
    for row in getattr(table, "rows", []):
        cells = [cell.text.strip() for cell in row.cells]
        # `row.cells` repeats merged cells; collapse the duplicates.
        deduped: list[str] = []
        for cell in cells:
            if cell and (not deduped or deduped[-1] != cell):
                deduped.append(cell)
        if deduped:
            rows.append(" · ".join(deduped))
    return rows


def _looks_multi_column(text: str) -> bool:
    """Heuristic: a two-column PDF extracts as many short, broken lines.

    pypdf gives no glyph coordinates, so this is the signal available. It only
    drives a warning and an offer to paste instead, never a rejection.
    """
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 12:
        return False
    short = sum(1 for line in lines if len(line.strip()) < 25)
    return short / len(lines) > 0.45


# ─── Line splitting ───────────────────────────────────────────────────


def _to_lines(text: str) -> list[CVLine]:
    section: Section = "header"
    seen_heading = False
    lines: list[CVLine] = []
    buffer: list[str] = []
    buffer_section: Section = "header"

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        joined = " ".join(buffer).strip()
        if joined:
            lines.append(
                CVLine(id=f"L{len(lines) + 1}", text=joined, section=buffer_section)
            )
        buffer = []

    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            flush()
            continue

        heading = _heading_of(stripped)
        if heading is not None:
            flush()
            section = heading
            seen_heading = True
            continue

        if not seen_heading and section == "header" and len(lines) >= 6:
            # A header that runs past a handful of lines is really a summary.
            section = "summary"

        candidate = strip_bullet(stripped)
        if not candidate:
            continue

        if buffer and _is_continuation(buffer[-1], candidate) and buffer_section == section:
            buffer.append(candidate)
        else:
            flush()
            buffer_section = section
            buffer = [candidate]

    flush()
    return lines


def _heading_of(line: str) -> Section | None:
    if len(line) > 48:
        return None
    for section, pattern in _SECTION_PATTERNS:
        if pattern.match(line):
            return section
    return None


def _is_continuation(previous: str, current: str) -> bool:
    """Whether ``current`` is the wrapped remainder of ``previous``.

    PDF extraction breaks one bullet across several lines. Rejoining them keeps
    a claim and its evidence on the same citable line — split across two ids,
    "led a team of" and "4 engineers" would each look unsupported.
    """
    if _ENDS_SENTENCE_RE.search(previous):
        return False
    if _CONTINUATION_RE.search(previous):
        return True
    return current[:1].islower()
