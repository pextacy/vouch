"""Deterministic text normalisation shared by the parser and the verifier.

Everything the verifier compares passes through :func:`normalize` first, so the
comparison is accent-, case- and punctuation-insensitive in exactly the same way
on both sides. That symmetry is the point: a rule that folds "İstanbul" to
"istanbul" in the generated text but not in the CV would invent a violation.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Final

#: Dotless ı has no canonical decomposition, so NFKD cannot fold it for us.
#: Everything else Turkish (ğ ş ç ö ü) decomposes to ASCII + a combining mark,
#: which the mark-stripping pass below removes. Folding all i-variants together
#: is what makes "İstanbul" == "Istanbul" == "ıstanbul".
_I_VARIANTS: Final[dict[int, str]] = str.maketrans({"ı": "i", "İ": "i", "I": "i"})

_PUNCT_RE: Final[re.Pattern[str]] = re.compile(r"[^\w\s%+#.]", re.UNICODE)
_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+", re.UNICODE)
_BULLET_RE: Final[re.Pattern[str]] = re.compile(r"^[\s ]*[-•▪◦*·–—o]\s+")
_CTRL_RE: Final[re.Pattern[str]] = re.compile(
    "[" + "".join(chr(c) for c in (*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20))) + "]"
    "|[\u200b-\u200f\ufeff]"
)


def strip_marks(value: str) -> str:
    """NFKD-decompose and drop combining marks (é→e, ş→s, İ→I)."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(value: str) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace.

    ``%``, ``+``, ``#`` and ``.`` survive because they carry meaning in claims
    (``40%``, ``5+``, ``C#``, ``3.10``).
    """
    folded = strip_marks(value.translate(_I_VARIANTS)).casefold()
    folded = folded.translate(_I_VARIANTS)
    folded = _PUNCT_RE.sub(" ", folded)
    return _WS_RE.sub(" ", folded).strip()


def normalize_token(value: str) -> str:
    """Normalise a single token and drop the separators entirely.

    Used for identity comparisons where spacing is noise: ``Node.js`` and
    ``nodejs`` and ``node js`` are the same tool.
    """
    return normalize(value).replace(" ", "").replace(".", "")


def clean(value: str) -> str:
    """Tidy raw extracted text without changing its meaning.

    Removes control and zero-width characters, normalises unicode to NFKC and
    collapses runs of spaces — but keeps line structure, which the CV parser
    needs.
    """
    value = unicodedata.normalize("NFKC", value)
    value = _CTRL_RE.sub("", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t ]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def strip_bullet(line: str) -> str:
    """Drop a leading list marker from a CV line."""
    return _BULLET_RE.sub("", line).strip()


def sha256_of(value: str) -> str:
    return hashlib.sha256(normalize(value).encode("utf-8")).hexdigest()




def trim_to_chars(value: str, limit: int) -> tuple[str, bool]:
    """Cut ``value`` to ``limit`` characters on a line boundary.

    Returns the text and whether anything was dropped.
    """
    if len(value) <= limit:
        return value, False
    cut = value[:limit]
    newline = cut.rfind("\n")
    if newline > limit * 0.6:
        cut = cut[:newline]
    return cut.rstrip(), True


_TR_CHARS: Final[frozenset[str]] = frozenset("ğışçöüĞİŞÇÖÜ")
_TR_WORDS: Final[frozenset[str]] = frozenset(
    {
        "ve", "ile", "için", "olarak", "deneyim", "yılı", "yıl", "şirket",
        "geliştirme", "yönetimi", "proje", "eğitim", "üniversite", "lisans",
        "beceriler", "yetenekler", "sorumluluklar", "çalıştım", "ekip",
    }
)
_EN_WORDS: Final[frozenset[str]] = frozenset(
    {
        "and", "with", "for", "the", "experience", "years", "team", "project",
        "development", "management", "education", "university", "bachelor",
        "skills", "responsibilities", "worked", "using",
    }
)


def detect_language(value: str) -> str:
    """Return ``"tr"``, ``"en"`` or ``"other"`` for a block of text.

    A cheap bag-of-words vote plus a Turkish-diacritic signal. Only used to
    choose the output language, so a wrong answer is cosmetic, never unsafe.
    """
    lowered = normalize(value)
    words = set(lowered.split())
    tr_score = len(words & _TR_WORDS) * 2
    en_score = len(words & _EN_WORDS) * 2
    tr_score += min(6, sum(1 for ch in value if ch in _TR_CHARS) // 3)
    if tr_score == 0 and en_score == 0:
        return "other"
    return "tr" if tr_score > en_score else "en"
