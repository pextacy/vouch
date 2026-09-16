"""Build the DOCX the user downloads.

The bytes come back to the UI base64-encoded rather than being pushed into
storage from here: the plugin's storage token covers the ``user`` and ``tool``
scopes, while the iframe's ``files.*`` surface is pinned to ``app`` scope, so
the plugin cannot write a file the UI can later hand to ``files.download``
(``docs/api-notes.md §6``). A 30–60 KB document is far inside the 512 KiB
response cap, so the round trip is cheap and the UI owns the save dialog.

The document is deliberately plain: a recruiter's ATS parses text, not styling,
and the whole product argument is that the content is trustworthy.
"""

from __future__ import annotations

import base64
import io
import re
from datetime import date
from typing import Any, Final

from ..schemas import LetterResult, TailorResult

MIME: Final[str] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_UNSAFE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"[^\w.\- ]+", re.UNICODE)


def build_docx(
    *,
    tailor: TailorResult | None = None,
    letter: LetterResult | None = None,
    company: str | None = None,
    role: str | None = None,
    locale: str = "en",
) -> tuple[str, str]:
    """Render the accepted bullets and the letter. Returns (filename, base64)."""
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

    if tailor is not None:
        accepted = [b for b in tailor.bullets if b.suggestion]
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
            paragraph = document.add_paragraph(para.text)
            paragraph.paragraph_format.space_after = Pt(8)
        if letter.placeholders:
            note = document.add_paragraph()
            run = note.add_run(strings["placeholders"].format(items=", ".join(letter.placeholders)))
            run.italic = True

    footer = document.add_paragraph()
    footer_run = footer.add_run(strings["footer"])
    footer_run.italic = True
    footer_run.font.size = Pt(9)

    buffer = io.BytesIO()
    document.save(buffer)
    return _filename(company, role, locale), base64.b64encode(buffer.getvalue()).decode("ascii")


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
        "footer": "Written with Receipts. Every line above is traceable to your CV.",
        "file_stem": "receipts",
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
        "footer": "Receipts ile hazırlandı. Yukarıdaki her satır CV'nize dayanıyor.",
        "file_stem": "receipts",
    },
}
