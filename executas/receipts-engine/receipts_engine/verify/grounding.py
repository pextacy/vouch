"""The "Invent nothing" verifier.

Pure Python, no model in the loop: given a generated sentence and the CV lines
it claims to be based on, it extracts every **claim** — a fact a reader would
hold the candidate to — and checks each one against the source. A claim with no
support is a violation, and a generated bullet with any violation is repaired
once and then dropped.

The asymmetry is deliberate. Rewording is free; facts are not. The verifier
never objects to "led" instead of "was responsible for", but it will object to
"40%" when the CV says nothing about 40%.

Claim classes and what supports them (``docs.md §6``):

===============  ===========================================================
number           the same numeric value appears in the source
date             the year or month name appears in the source
duration         the same number + unit, **or** derivable from source dates
tech             the canonical term appears in the source
proper_noun      appears in the source — or, if it is not a tech term, in the
                 posting's own requirement vocabulary
title            appears in the source
===============  ===========================================================
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal

from ..text import normalize, normalize_token
from .lexicon import DEFAULT_LEXICON, TechLexicon

ClaimKind = Literal["number", "date", "duration", "tech", "proper_noun", "title"]

#: Claim classes the posting's vocabulary may never license. A concept can be
#: borrowed from the posting ("stakeholders"); a fact cannot ("Kubernetes").
_NEVER_FROM_POSTING: Final[frozenset[str]] = frozenset(
    {"number", "date", "duration", "tech", "title"}
)


@dataclass(frozen=True)
class Claim:
    kind: ClaimKind
    surface: str
    key: str

    def __str__(self) -> str:  # pragma: no cover - debug aid
        return f"{self.kind}:{self.surface}"


@dataclass
class Verdict:
    ok: bool
    unsupported: list[Claim] = field(default_factory=list)

    @property
    def tokens(self) -> list[str]:
        """Surfaces of the unsupported claims, for the repair prompt."""
        seen: dict[str, None] = {}
        for claim in self.unsupported:
            seen.setdefault(claim.surface, None)
        return list(seen)


# ─── Patterns ─────────────────────────────────────────────────────────

_YEAR_RE: Final[re.Pattern[str]] = re.compile(r"\b(19|20)\d{2}\b")
_NUMBER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-zÀ-ÿ0-9])"                     # not glued to a word (S3, H2)
    r"(?P<value>\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
    r"\s*(?P<suffix>%|k\b|m\b|bn\b|x\b|\+)?",
    re.IGNORECASE,
)
_DURATION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<count>\d+(?:[.,]\d+)?)\s*\+?\s*"
    r"(?P<unit>years?|yrs?|yıll?ık|yıl|sene|months?|mos?\b|ay\b)",
    re.IGNORECASE,
)
_RANGE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b((?:19|20)\d{2})\s*[-–—/]\s*((?:19|20)\d{2}|present|current|now|halen|devam|günümüz)\b",
    re.IGNORECASE,
)
_TITLE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(senior|junior|mid-?level|lead|principal|staff|head|chief|director|"
    r"manager|supervisor|architect|founder|co-?founder|vp|c-?level|cto|ceo|cfo|coo|"
    r"kıdemli|yönetici|müdür|direktör|şef|uzman|baş|takım lideri)\b",
    re.IGNORECASE,
)
_PROPER_RE: Final[re.Pattern[str]] = re.compile(
    r"\b([A-ZÇĞİÖŞÜ][\wÀ-ÿ&.+#-]*(?:\s+[A-ZÇĞİÖŞÜ][\wÀ-ÿ&.+#-]*){0,3})"
)
_SENTENCE_START_RE: Final[re.Pattern[str]] = re.compile(r"(?:^|[.!?:;•\-–—]\s+|\n\s*)$")

_MONTHS: Final[frozenset[str]] = frozenset(
    {
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
        "oct", "nov", "dec",
        "ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz",
        "ağustos", "eylül", "ekim", "kasım", "aralık",
    }
)

#: Capitalised words that carry no factual weight: they start sentences, name
#: months and weekdays, or are ordinary words that happen to be capitalised in
#: a CV bullet. Flagging them would bury the real violations.
_COMMON_CAPITALISED: Final[frozenset[str]] = frozenset(
    {
        "i", "a", "an", "the", "and", "or", "but", "for", "with", "without",
        "from", "to", "in", "on", "at", "by", "of", "as", "via", "per",
        "built", "led", "drove", "owned", "designed", "developed", "delivered",
        "managed", "created", "improved", "reduced", "increased", "launched",
        "migrated", "shipped", "worked", "collaborated", "partnered", "wrote",
        "team", "teams", "project", "projects", "product", "products",
        "company", "customer", "customers", "client", "clients", "user",
        "users", "engineer", "engineering", "developer", "development",
        "experience", "responsible", "responsibilities", "summary", "profile",
        "education", "skills", "certifications", "languages", "interests",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
        "sunday", "today", "present", "current",
        "ve", "ile", "için", "olarak", "ekip", "proje", "ürün", "şirket",
        "müşteri", "deneyim", "eğitim", "beceriler", "yetenekler", "özet",
        "geliştirdim", "yönettim", "kurdum", "tasarladım", "çalıştım",
    }
    | _MONTHS
)


# ─── Support index ────────────────────────────────────────────────────


class SupportIndex:
    """Everything the source lines can vouch for, precomputed once."""

    def __init__(self, sources: list[str], lexicon: TechLexicon) -> None:
        joined = "\n".join(sources)
        self.raw = joined
        self.normalized = normalize(joined)
        self.tokens = frozenset(self.normalized.split())
        self.compact = self.normalized.replace(" ", "")
        self.numbers = _numbers_in(joined)
        self.years = {match.group(0) for match in _YEAR_RE.finditer(joined)}
        self.durations = _durations_in(joined)
        self.tech = lexicon.matches(self.normalized)
        self.span_years = _total_years(joined)

    def has_phrase(self, phrase: str) -> bool:
        """Whether the normalised source contains ``phrase``.

        Falls back to a separator-insensitive compare so "Node.js" in the CV
        supports "node js" in the suggestion.
        """
        needle = normalize(phrase)
        if not needle:
            return True
        if needle in self.normalized:
            return True
        return normalize_token(phrase) in self.compact


# ─── Extraction ───────────────────────────────────────────────────────


def extract_claims(text: str, lexicon: TechLexicon | None = None) -> list[Claim]:
    """Every checkable claim in ``text``, in no particular order."""
    lex = lexicon or DEFAULT_LEXICON
    text = _mask_placeholders(text)
    claims: list[Claim] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: ClaimKind, surface: str, key: str) -> None:
        marker = (kind, key)
        if key and marker not in seen:
            seen.add(marker)
            claims.append(Claim(kind=kind, surface=surface, key=key))

    duration_spans: list[tuple[int, int]] = []
    for match in _DURATION_RE.finditer(text):
        duration_spans.append(match.span())
        count = _to_number(match.group("count"))
        unit = _unit_of(match.group("unit"))
        if count is not None:
            add("duration", match.group(0).strip(), f"{count:g}:{unit}")

    for match in _YEAR_RE.finditer(text):
        add("date", match.group(0), match.group(0))

    for word in re.findall(r"[^\W\d_]+", text, re.UNICODE):
        if normalize(word) in _MONTHS:
            add("date", word, normalize(word))

    for match in _NUMBER_RE.finditer(text):
        if any(start <= match.start() < end for start, end in duration_spans):
            continue  # already covered by the duration claim
        if _YEAR_RE.fullmatch(match.group("value")):
            continue  # already covered by the date claim
        value = _to_number(match.group("value"), match.group("suffix"))
        if value is not None:
            add("number", match.group(0).strip(), f"{value:g}")

    normalized = normalize(text)
    for term in lex.matches(normalized):
        add("tech", term, term)

    for match in _TITLE_RE.finditer(text):
        add("title", match.group(0), normalize(match.group(0)))

    for match in _PROPER_RE.finditer(text):
        phrase = match.group(1).strip()
        sentence_initial = _is_sentence_initial(text, match.start())
        for offset, group in _proper_groups(phrase, lex):
            # A capitalised word that only opens the sentence is grammar, not a
            # claim — but the rest of the phrase after it still is.
            if sentence_initial and offset == 0 and len(group.split()) == 1:
                continue
            if _is_noise(group, lex):
                continue
            add("proper_noun", group, normalize(group))

    return claims


def _proper_groups(phrase: str, lexicon: TechLexicon) -> list[tuple[int, str]]:
    """Split a capitalised phrase into the runs that are *not* technologies.

    "Google Cloud" disappears entirely (the tech claim already checks it, with
    synonyms); "Acme Kubernetes Corp" yields "Acme" and "Corp".
    """
    words = phrase.split()
    covered = lexicon.cover(words)
    groups: list[tuple[int, str]] = []
    current: list[str] = []
    start = 0
    for index, word in enumerate(words):
        if index in covered:
            if current:
                groups.append((start, " ".join(current)))
                current = []
            continue
        if not current:
            start = index
        current.append(word)
    if current:
        groups.append((start, " ".join(current)))
    return groups


def _is_sentence_initial(text: str, index: int) -> bool:
    return bool(_SENTENCE_START_RE.search(text[:index]))


def _mask_placeholders(text: str) -> str:
    """Blank out ``[Company]``-style placeholders, keeping offsets intact.

    The letter prompt is told to write these when a fact is genuinely unknown —
    they are the honest alternative to a guessed company name. Reading
    "[Hiring Manager]" as a proper-noun claim would punish exactly the
    behaviour we asked for. The pattern is narrow (letters and spaces, short)
    so prose in brackets is still checked.
    """
    return _PLACEHOLDER_RE.sub(lambda hit: " " * len(hit.group(0)), text)


_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"\[[A-Za-zÇĞİÖŞÜçğıöşü ]{2,30}\]")


def _is_noise(phrase: str, lexicon: TechLexicon) -> bool:
    """Drop capitalised phrases that are not really proper nouns."""
    words = [normalize(word) for word in phrase.split()]
    words = [word for word in words if word]
    if not words:
        return True
    if all(word in _COMMON_CAPITALISED for word in words):
        return True
    if len(words) == 1:
        word = words[0]
        if len(word) < 2:
            return True
        # An all-caps acronym is a claim even if short; a single capitalised
        # ordinary word is not.
        if word in _COMMON_CAPITALISED and not lexicon.knows(word):
            return True
    return False


# ─── Verification ─────────────────────────────────────────────────────


def supported(claim: Claim, index: SupportIndex, allowed_vocab: frozenset[str]) -> bool:
    """Whether the source (or, for concepts, the posting) backs this claim."""
    if claim.kind == "number":
        return claim.key in index.numbers
    if claim.kind == "date":
        if claim.key in index.years:
            return True
        return claim.key in index.tokens
    if claim.kind == "duration":
        return _duration_supported(claim, index)
    if claim.kind == "tech":
        return claim.key in index.tech
    if claim.kind == "title":
        return index.has_phrase(claim.surface)
    # proper_noun
    if index.has_phrase(claim.surface):
        return True
    if claim.kind in _NEVER_FROM_POSTING:
        return False
    return bool(_soft_forms(claim.key) & allowed_vocab)


#: Suffixes stripped when matching a *concept* against the posting's wording.
#: "Stakeholders" and "stakeholder management" are the same idea; nothing here
#: applies to numbers, tools or titles, where the exact form is the claim.
_CONCEPT_SUFFIXES: Final[tuple[str, ...]] = ("s", "es", "ler", "lar", "leri", "ları")


def _soft_forms(key: str) -> frozenset[str]:
    """``key`` plus the singular/plural variants a concept may take."""
    forms = {key}
    for word_suffix in _CONCEPT_SUFFIXES:
        if key.endswith(word_suffix) and len(key) > len(word_suffix) + 2:
            forms.add(key[: -len(word_suffix)])
        forms.add(key + word_suffix)
    return frozenset(forms)


def _duration_supported(claim: Claim, index: SupportIndex) -> bool:
    count_text, unit = claim.key.split(":", 1)
    count = float(count_text)
    if (count, unit) in index.durations:
        return True
    # "5+ years" is honest when the CV's own date ranges add up to at least
    # five years — the candidate does not have to spell the total out.
    if unit == "year" and index.span_years is not None:
        return count <= index.span_years + 1e-9
    if unit == "month" and index.span_years is not None:
        return count <= index.span_years * 12 + 1e-9
    return False


def verify(
    generated: str,
    sources: list[str],
    *,
    lexicon: TechLexicon | None = None,
    posting_vocab: list[str] | None = None,
) -> Verdict:
    """Check one generated sentence against the CV lines it cites.

    ``posting_vocab`` is the list of requirement texts. A capitalised concept
    the posting itself uses ("Customer Success") is allowed even when the CV
    words it differently — but only when it is not a technology and not a
    number, date, duration or title.
    """
    lex = lexicon or DEFAULT_LEXICON
    if not generated.strip():
        return Verdict(ok=True)
    index = SupportIndex(sources, lex)
    allowed = _vocab_index(posting_vocab or [], lex)
    unsupported = [
        claim for claim in extract_claims(generated, lex) if not supported(claim, index, allowed)
    ]
    return Verdict(ok=not unsupported, unsupported=unsupported)


def _vocab_index(posting_vocab: list[str], lexicon: TechLexicon) -> frozenset[str]:
    """Normalised capitalised phrases the posting uses, minus tech terms."""
    allowed: set[str] = set()
    for entry in posting_vocab:
        for match in _PROPER_RE.finditer(entry):
            phrase = match.group(1).strip()
            if lexicon.matches(normalize(phrase)):
                continue  # a tool named in the posting is still not yours
            allowed.add(normalize(phrase))
        for word in normalize(entry).split():
            if not lexicon.knows(word):
                allowed.add(word)
    return frozenset(allowed)


# ─── Numeric helpers ──────────────────────────────────────────────────

_SUFFIX_FACTORS: Final[dict[str, float]] = {"k": 1_000.0, "m": 1_000_000.0, "bn": 1_000_000_000.0}


def _to_number(value: str, suffix: str | None = None) -> float | None:
    """Parse ``1,000`` / ``1.000`` / ``2.5`` / ``1k`` into a float.

    A dot or comma is a thousands separator when it groups exactly three
    digits, and a decimal point otherwise — the rule that makes the European
    and US spellings of the same number compare equal.
    """
    cleaned = value.strip()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", cleaned):
        cleaned = re.sub(r"[.,]", "", cleaned)
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        number = float(cleaned)
    except ValueError:
        return None
    if suffix:
        marker = suffix.strip().lower()
        if marker in _SUFFIX_FACTORS:
            number *= _SUFFIX_FACTORS[marker]
    return number


def _numbers_in(text: str) -> frozenset[str]:
    """Every numeric value the source states, in canonical form."""
    values: set[str] = set()
    for match in _NUMBER_RE.finditer(text):
        number = _to_number(match.group("value"), match.group("suffix"))
        if number is not None:
            values.add(f"{number:g}")
        # A source "1k" also vouches for a generated "1000" and vice versa, so
        # index the bare value too.
        bare = _to_number(match.group("value"))
        if bare is not None:
            values.add(f"{bare:g}")
    for match in _DURATION_RE.finditer(text):
        number = _to_number(match.group("count"))
        if number is not None:
            values.add(f"{number:g}")
    return frozenset(values)


def _unit_of(unit: str) -> str:
    lowered = normalize(unit)
    if lowered.startswith(("month", "mo", "ay")):
        return "month"
    return "year"


def _durations_in(text: str) -> frozenset[tuple[float, str]]:
    found: set[tuple[float, str]] = set()
    for match in _DURATION_RE.finditer(text):
        count = _to_number(match.group("count"))
        if count is not None:
            found.add((count, _unit_of(match.group("unit"))))
    return frozenset(found)


def _total_years(text: str, today: date | None = None) -> float | None:
    """Total years covered by the date ranges in the source, merged.

    Overlapping roles are merged so two concurrent jobs do not double-count.
    Returns ``None`` when the source states no ranges at all.
    """
    now = (today or date.today()).year
    spans: list[tuple[int, int]] = []
    for match in _RANGE_RE.finditer(text):
        start = int(match.group(1))
        end_text = match.group(2)
        end = now if not end_text.isdigit() else int(end_text)
        if end >= start:
            spans.append((start, end))
    if not spans:
        return None
    spans.sort()
    merged: list[list[int]] = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    total = float(sum(end - start for start, end in merged))
    return total if not math.isnan(total) else None
