"""Job posting → the trimmed text the extraction prompt sees.

Postings arrive with navigation, cookie banners, benefits blurbs and legal
boilerplate. Dropping the obvious noise before the model reads it is the
cheapest way to keep extraction on the actual requirements, and it buys back
tokens for the CV side of the budget.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from ..errors import EngineError
from ..text import clean, detect_language, sha256_of, trim_to_chars

#: The posting's share of the sampling budget (~3k tokens).
MAX_POSTING_CHARS: Final[int] = 10_000

#: Shorter than this and there is nothing to extract requirements from.
MIN_POSTING_CHARS: Final[int] = 120

_NOISE_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*("
    r"(accept|manage)\s+(all\s+)?cookies|cookie\s+(policy|settings|preferences)|"
    r"privacy\s+policy|terms\s+(of\s+(use|service)|and\s+conditions)|"
    r"sign\s+in|log\s+in|create\s+an?\s+account|apply\s+now|share\s+this\s+job|"
    r"save\s+(this\s+)?job|report\s+(this\s+)?job|back\s+to\s+(search|jobs)|"
    r"skip\s+to\s+(main\s+)?content|follow\s+us|all\s+rights\s+reserved|"
    r"(ç|c)erez|gizlilik\s+politikas(ı|i)|kullan(ı|i)m\s+ko(ş|s)ullar(ı|i)|"
    r"(ş|s)imdi\s+ba(ş|s)vur|giri(ş|s)\s+yap|kay(ı|i)t\s+ol"
    r")\s*[.!]?\s*$",
    re.IGNORECASE,
)
_SOCIAL_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(facebook|twitter|linkedin|instagram|youtube|tiktok|x)\s*$", re.IGNORECASE
)
_URL_ONLY_RE: Final[re.Pattern[str]] = re.compile(r"^\s*https?://\S+\s*$", re.IGNORECASE)

_TITLE_HINT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(job\s+title|position|role|pozisyon|unvan)\s*[:\-]\s*(?P<value>.{2,80})$",
    re.IGNORECASE,
)
_COMPANY_HINT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(company|employer|organisation|organization|(ş|s)irket|kurum)\s*[:\-]\s*(?P<value>.{2,80})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Posting:
    text: str
    hash: str
    language: str
    truncated: bool
    title_hint: str | None
    company_hint: str | None


def normalize_posting(raw: str) -> Posting:
    """Clean, de-noise and trim a posting. Raises when there is nothing to read."""
    cleaned = clean(raw or "")
    if len(cleaned) < MIN_POSTING_CHARS:
        raise EngineError("no_requirements_found", details={"chars": len(cleaned)})

    title_hint: str | None = None
    company_hint: str | None = None
    kept: list[str] = []
    for line in cleaned.split("\n"):
        stripped = line.strip()
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        if _NOISE_LINE_RE.match(stripped) or _SOCIAL_RE.match(stripped) or _URL_ONLY_RE.match(stripped):
            continue
        if title_hint is None:
            match = _TITLE_HINT_RE.match(stripped)
            if match:
                title_hint = match.group("value").strip()
        if company_hint is None:
            match = _COMPANY_HINT_RE.match(stripped)
            if match:
                company_hint = match.group("value").strip()
        kept.append(stripped)

    body = "\n".join(kept).strip()
    if len(body) < MIN_POSTING_CHARS:
        raise EngineError("no_requirements_found", details={"chars": len(body)})

    trimmed, truncated = trim_to_chars(body, MAX_POSTING_CHARS)
    return Posting(
        text=trimmed,
        hash=sha256_of(trimmed),
        language=detect_language(trimmed),
        truncated=truncated,
        title_hint=title_hint,
        company_hint=company_hint,
    )
