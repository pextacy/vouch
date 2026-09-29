"""Build the DOCX the user downloads.

The bytes come back to the UI base64-encoded rather than being pushed into
storage from here: the plugin's storage token covers the ``user`` and ``tool``
scopes, while the iframe's ``files.*`` surface is pinned to ``app`` scope, so
the plugin cannot write a file the UI can later hand to ``files.download``.
A 30–60 KB document is far inside the 512 KiB
response cap, so the round trip is cheap and the UI owns the save dialog.

The document is deliberately plain: a recruiter's ATS parses text, not styling,
and the whole product argument is that the content is trustworthy.

The bullets arriving here are not always the ones the verifier approved: the
user can edit a suggestion before accepting it. So when the CV comes with the
request, every line is checked again against it, and the footer only makes the
"traceable to your CV" claim for a document where every line still is.

:func:`build_cv_docx` is the other direction and the newer one: the CV itself,
back out. Three screens now put the user's own sentences *into* the stored CV
— a gap answer, an audit answer, a recurring answer — and until this existed
none of them could reach the document an employer actually reads. It renders
nothing but the lines themselves, so there is no verifier step and no footer
claim to make: every word in it is already the user's.
"""

from __future__ import annotations

import base64
import io
import re
from datetime import date
from typing import Any, Final

from ..errors import EngineError
from ..pipeline import resolve_placeholders
from ..schemas import CVDoc, LetterResult, Section, TailorResult
from ..verify import DEFAULT_LEXICON, verify

MIME: Final[str] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_UNSAFE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"[^\w.\- ]+", re.UNICODE)

#: Reading order for the exported CV. Stored order cannot be used: answers are
#: appended to the end of the document, and a job printed under "Skills" is
#: not a CV anyone can send.
_SECTION_ORDER: Final[tuple[Section, ...]] = (
    "header",
    "summary",
    "experience",
    "projects",
    "education",
    "certifications",
    "skills",
    "other",
)


def build_docx(
    *,
    tailor: TailorResult | None = None,
    letter: LetterResult | None = None,
    company: str | None = None,
    role: str | None = None,
    locale: str = "en",
    cv: CVDoc | None = None,
) -> tuple[str, str, int]:
    """Render the accepted bullets and the letter.

    Returns ``(filename, base64, unverified)`` — ``unverified`` counts the
    lines that no longer trace back to the CV, which is only possible when the
    user edited one by hand.
    """
    import docx
    from docx.shared import Pt

    strings = _STRINGS.get(locale, _STRINGS["en"])
    document = docx.Document()

    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    heading = f"{role or strings['role_fallback']}"
    if company:
        heading = f"{heading} — {company}"
    document.add_heading(heading, level=1)

    unverified = 0
    if tailor is not None:
        accepted = [b for b in tailor.bullets if b.suggestion]
        unverified = _unverified_count(accepted, cv)
        if accepted:
            document.add_heading(strings["bullets"], level=2)
            for bullet in accepted:
                paragraph = document.add_paragraph(bullet.suggestion or "", style="List Bullet")
                paragraph.paragraph_format.space_after = Pt(4)

        dropped = [b for b in tailor.bullets if not b.suggestion]
        if dropped:
            note = document.add_paragraph()
            run = note.add_run(strings["dropped"].format(count=len(dropped)))
            run.italic = True

    if letter is not None and letter.paragraphs:
        document.add_heading(strings["letter"], level=2)
        for para in letter.paragraphs:
            # The stored paragraph keeps `[Company]`/`[Role]` so that what the
            # verifier approved is what was saved; the document is the point of
            # use, so this is where the posting's own names go in.
            paragraph = document.add_paragraph(
                resolve_placeholders(para.text, company=company, role=role)
            )
            paragraph.paragraph_format.space_after = Pt(8)
        if letter.placeholders:
            note = document.add_paragraph()
            run = note.add_run(strings["placeholders"].format(items=", ".join(letter.placeholders)))
            run.italic = True

    footer = document.add_paragraph()
    footer_run = footer.add_run(
        strings["footer"] if unverified == 0 else strings["footer_edited"].format(count=unverified)
    )
    footer_run.italic = True
    footer_run.font.size = Pt(9)

    buffer = io.BytesIO()
    document.save(buffer)
    return (
        _filename(company, role, locale),
        base64.b64encode(buffer.getvalue()).decode("ascii"),
        unverified,
    )


def build_cv_docx(
    *,
    cv: CVDoc,
    mode: str = "full",
    locale: str = "en",
) -> tuple[str, str, int]:
    """Render the stored CV, or only the lines the user added to it.

    Returns ``(filename, base64, lines)``.

    **Nothing is rewritten.** Each paragraph is one ``CVLine.text``, byte for
    byte — an export that tidied a sentence would be the app editing someone's
    account of their own career, which is the line this product does not
    cross. It also means there is nothing here to verify: the document cannot
    contain a claim the CV does not, because it *is* the CV.

    Lines are grouped by section rather than printed in stored order. An
    answer is appended to the end of ``lines`` (``lib/cv.appendLine``), so
    without grouping a new job would print after the skills list and the
    document would be unusable — which is the whole reason for exporting it.

    ``mode="additions"`` prints only the lines carrying ``added_at``: someone
    who keeps a designed CV wants the new sentences to paste, not a plain
    replacement for the document they spent an evening on.
    """
    import docx
    from docx.shared import Pt

    strings = _STRINGS.get(locale, _STRINGS["en"])
    wanted = [line for line in cv.lines if line.added_at] if mode == "additions" else cv.lines
    if not wanted:
        raise EngineError("invalid_args", "this CV has no lines to export")

    document = docx.Document()
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    for section in _SECTION_ORDER:
        lines = [line for line in wanted if line.section == section]
        if not lines:
            continue
        # The header is the name and the contact details. A document that
        # opened with the word "Header" above them would be a form, not a CV.
        if section != "header":
            document.add_heading(strings["section"][section], level=2)
        for line in lines:
            paragraph = document.add_paragraph(line.text)
            paragraph.paragraph_format.space_after = Pt(4)

    # Only on the worksheet. The full CV goes to an employer, and a tool's
    # signature at the bottom of someone's CV is the tool taking credit for
    # their career.
    if mode == "additions":
        note = document.add_paragraph()
        run = note.add_run(strings["additions_note"])
        run.italic = True
        run.font.size = Pt(9)

    buffer = io.BytesIO()
    document.save(buffer)
    stem = strings["cv_additions_stem"] if mode == "additions" else strings["cv_stem"]
    return (
        f"{stem}-{date.today().isoformat()}.docx",
        base64.b64encode(buffer.getvalue()).decode("ascii"),
        len(wanted),
    )


def _unverified_count(bullets: list[Any], cv: CVDoc | None) -> int:
    """How many rendered lines the CV can no longer vouch for.

    Checked against the whole CV rather than the line a suggestion started
    from: an edit may legitimately pull a fact from elsewhere in the document,
    and flagging that would punish an honest correction.
    """
    if cv is None:
        return 0
    sources = [line.text for line in cv.lines]
    return sum(
        1
        for bullet in bullets
        if bullet.suggestion
        and not verify(bullet.suggestion, sources, lexicon=DEFAULT_LEXICON).ok
    )


def _filename(company: str | None, role: str | None, locale: str) -> str:
    strings = _STRINGS.get(locale, _STRINGS["en"])
    parts = [strings["file_stem"]]
    for value in (company, role):
        if value:
            parts.append(_UNSAFE_FILENAME_RE.sub("", value).strip().replace(" ", "-")[:40])
    parts.append(date.today().isoformat())
    stem = "-".join(part for part in parts if part) or strings["file_stem"]
    return f"{stem}.docx"


_STRINGS: Final[dict[str, dict[str, Any]]] = {
    "en": {
        "role_fallback": "Tailored application",
        "bullets": "Tailored CV bullets",
        "letter": "Cover letter",
        "dropped": (
            "{count} suggestion(s) were left out: they could not be strengthened "
            "without adding facts your CV does not contain."
        ),
        "placeholders": "Replace before sending: {items}",
        "footer": "Written with Vouch. Every line above is traceable to your CV.",
        "footer_edited": (
            "Written with Vouch. {count} line(s) you edited by hand could not be traced "
            "back to your CV — check them before you send this."
        ),
        "cv_stem": "cv",
        "cv_additions_stem": "cv-additions",
        "additions_note": (
            "These are the lines you added in Vouch, exactly as you typed them. "
            "Paste them into your own CV — nothing here was rewritten."
        ),
        "section": {
            "header": "",
            "summary": "Summary",
            "experience": "Experience",
            "projects": "Projects",
            "education": "Education",
            "certifications": "Certifications",
            "skills": "Skills",
            "other": "Other",
        },
        "file_stem": "vouch",
    },
    "tr": {
        "role_fallback": "Uyarlanmış başvuru",
        "bullets": "Uyarlanmış CV maddeleri",
        "letter": "Ön yazı",
        "dropped": (
            "{count} öneri dışarıda bırakıldı: CV'de bulunmayan bilgiler eklemeden "
            "güçlendirilemedi."
        ),
        "placeholders": "Göndermeden önce değiştirin: {items}",
        "footer": "Vouch ile hazırlandı. Yukarıdaki her satır CV'nize dayanıyor.",
        "footer_edited": (
            "Vouch ile hazırlandı. Elle düzenlediğiniz {count} satır CV'nize "
            "dayandırılamadı — göndermeden önce kontrol edin."
        ),
        "cv_stem": "cv",
        "cv_additions_stem": "cv-eklenenler",
        "additions_note": (
            "Bunlar Vouch'ta eklediğiniz satırlar, yazdığınız gibi. Kendi CV'nize "
            "yapıştırın — burada hiçbir şey yeniden yazılmadı."
        ),
        "section": {
            "header": "",
            "summary": "Özet",
            "experience": "Deneyim",
            "projects": "Projeler",
            "education": "Eğitim",
            "certifications": "Sertifikalar",
            "skills": "Beceriler",
            "other": "Diğer",
        },
        "file_stem": "vouch",
    },
}
