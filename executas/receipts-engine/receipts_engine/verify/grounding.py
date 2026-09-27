"""The "Invent nothing" verifier.

Pure Python, no model in the loop: given a generated sentence and the CV lines
it claims to be based on, it extracts every **claim** — a fact a reader would
hold the candidate to — and checks each one against the source. A claim with no
support is a violation, and a generated bullet with any violation is repaired
once and then dropped.

The asymmetry is deliberate. Rewording is free; facts are not. The verifier
never objects to "led" instead of "was responsible for", but it will object to
"40%" when the CV says nothing about 40%.

Claim classes and what supports them (``docs/docs.md §6``):

===============  ===========================================================
number           the same numeric value **with the same unit** appears in the
                 source — ``40%`` is not evidenced by ``40 hours``
date             the year or month name appears in the source
duration         the same number + unit, **or** derivable from source dates
tech             the canonical term appears in the source
proper_noun      appears in the source as a whole word — or, if it is not a
                 tech term, in the posting's own requirement vocabulary: as a
                 multi-word phrase freely, as a single word only when
                 ``concepts.CONCEPT_WORDS`` lists it, because a lone word is
                 the shape a product or employer name takes
title            appears in the source as a whole word
===============  ===========================================================

Two rules keep a coincidence from passing as evidence:

* a number carries its unit into the comparison, so the ``40`` in "40 hours a
  week" cannot vouch for "40% conversion";
* phrases match on word boundaries, so "metadata" cannot vouch for "Meta" and
  "seniority" cannot vouch for "Senior". Turkish case suffixes written without
  an apostrophe (``Ankarada``) are still accepted for the word they inflect.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal

from ..text import normalize, normalize_token
from .concepts import is_concept
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
        # Words that open a sentence and carry no fact. The sentence-initial
        # rule above only forgives a *single* capitalised word, so "Since I
        # applied…" — the natural first line of a follow-up — was read as a
        # two-word proper noun and dropped a grounded paragraph. A phrase is
        # only discarded when **every** word is one of these, so "Since
        # Globex" is still the invented employer it looks like.
        "since", "after", "before", "during", "while", "when", "whenever",
        "because", "although", "though", "unless", "until", "once", "if",
        "then", "also", "however", "meanwhile", "recently", "previously",
        "now", "next", "finally", "still", "yet",
        "sonra", "önce", "çünkü", "ancak", "ayrıca", "şimdi", "artık",
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
        self.token_list = self.normalized.split()
        self.tokens = frozenset(self.token_list)
        # Separator-insensitive forms, one entry per word and per adjacent
        # pair, so "Node.js" in the CV vouches for "node js" in the suggestion
        # without letting a substring of an unrelated word do the same.
        self.compact_forms = frozenset(
            {normalize_token(token) for token in self.token_list}
            | {
                normalize_token(f"{first}{second}")
                for first, second in zip(self.token_list, self.token_list[1:], strict=False)
            }
            - {""}
        )
        self.numbers = _numbers_in(joined)
        self.years = {match.group(0) for match in _YEAR_RE.finditer(joined)}
        self.durations = _durations_in(joined)
        self.tech = lexicon.matches(self.normalized)
        self.span_years = _total_years(joined)

    def has_phrase(self, phrase: str) -> bool:
        """Whether the source states ``phrase`` as whole words.

        Substring containment would let "metadata" evidence "Meta", which is
        precisely the kind of coincidence this product exists to refuse. The
        compact fallback is kept for spelling-only differences ("Node.js" ↔
        "node js") but compares against single words and adjacent pairs, never
        against the whole run-together document.
        """
        needle = normalize(phrase)
        if not needle:
            return True
        parts = needle.split()
        if self._window_match(parts):
            return True
        if self._matches_translated_name(parts):
            return True
        compact = normalize_token(phrase)
        return bool(compact) and len(parts) <= 2 and compact in self.compact_forms

    def _matches_translated_name(self, parts: list[str]) -> bool:
        """Accept a name whose *generic* half is written in the other language.

        A CV in English and a letter in Turkish name the same school
        differently — "Bogazici University" and "Boğaziçi Üniversitesi" — and
        rejecting that would call an honest sentence a fabrication. Only the
        generic half may differ: the distinctive word ("Bogazici") must appear
        in the CV, and the source must name the same kind of institution right
        beside it, so "Stanford Hospital" never evidences "Stanford
        University".
        """
        classes = {_GENERIC_NOUN_CLASSES[word] for word in parts if word in _GENERIC_NOUN_CLASSES}
        distinctive = [word for word in parts if word not in _GENERIC_NOUN_CLASSES]
        if not classes or not distinctive:
            return False

        for position, token in enumerate(self.token_list):
            if not any(_same_word(token, word) for word in distinctive):
                continue
            neighbourhood = self.token_list[max(0, position - 2) : position + 3]
            nearby = {
                _GENERIC_NOUN_CLASSES[word]
                for word in neighbourhood
                if word in _GENERIC_NOUN_CLASSES
            }
            if classes & nearby and all(
                any(_same_word(source, word) for source in self.token_list)
                for word in distinctive
            ):
                return True
        return False

    def _window_match(self, parts: list[str]) -> bool:
        """Find ``parts`` as a consecutive run of source words."""
        if not parts:
            return True
        size = len(parts)
        head, last = parts[:-1], parts[-1]
        for start in range(len(self.token_list) - size + 1):
            window = self.token_list[start : start + size]
            if window[: size - 1] != head:
                continue
            if _same_word(window[-1], last):
                return True
        return False


#: Generic halves of institution names, grouped by what they name. Only words
#: in the same group may stand in for each other, which is what keeps a
#: translated university from becoming any nearby hospital.
_GENERIC_NOUN_CLASSES: Final[dict[str, str]] = {
    "university": "university", "universite": "university",
    "universitesi": "university", "college": "university",
    "kolej": "university", "koleji": "university",
    "institute": "institute", "institution": "institute",
    "enstitu": "institute", "enstitusu": "institute",
    "academy": "academy", "akademi": "academy", "akademisi": "academy",
    "school": "school", "okul": "school", "okulu": "school",
    "lise": "school", "lisesi": "school",
    "company": "company", "sirket": "company", "sirketi": "company",
    "holding": "company", "gmbh": "company", "ltd": "company",
    "bank": "bank", "bankasi": "bank", "bankas": "bank",
    "hospital": "hospital", "hastane": "hospital", "hastanesi": "hospital",
    "technologies": "technology", "technology": "technology",
    "teknoloji": "technology", "teknolojileri": "technology",
    "group": "group", "grup": "group", "grubu": "group",
    "foundation": "foundation", "vakif": "foundation", "vakfi": "foundation",
    "ministry": "ministry", "bakanlik": "ministry", "bakanligi": "ministry",
    "department": "department", "bolum": "department", "bolumu": "department",
}


#: Turkish case and plural suffixes that attach directly to a word. A CV that
#: writes "Ankarada" (the apostrophe correct Turkish would use is often
#: dropped) still evidences "Ankara"; nothing here turns "metadata" into
#: "Meta" or "seniority" into "Senior", because those endings are not suffixes.
_TR_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        "da", "de", "ta", "te", "dan", "den", "tan", "ten",
        "na", "ne", "nda", "nde", "ndan", "nden", "nin", "nun",
        "ya", "ye", "yi", "yu", "yla", "yle", "la", "le",
        "in", "un", "lar", "ler", "lari", "leri", "li", "lu",
        "si", "su", "daki", "deki", "dir", "dur", "tir", "tur",
    }
)


def _same_word(source_word: str, needle: str) -> bool:
    """Whether ``source_word`` is ``needle``, possibly with a Turkish suffix."""
    if source_word == needle:
        return True
    if not source_word.startswith(needle) or len(needle) < 3:
        return False
    return source_word[len(needle) :] in _TR_SUFFIXES


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
            add("number", match.group(0).strip(), _number_key(value, _unit_class(text, match)))

    for surface, value, unit in _spelled_numbers(text):
        # "Six years" is a span, not a count: it has to reach the duration rule,
        # which can derive it from the CV's own date ranges the way "6+ years"
        # already does.
        if unit in _DURATION_UNITS:
            add("duration", surface, f"{value:g}:{unit}")
        else:
            add("number", surface, _number_key(value, unit))

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
            # claim — but the rest of the phrase after it still is. Two things
            # override that: a word shaped like a name ("PhD", "AWS") and the
            # apostrophe Turkish puts before a case suffix, which marks a
            # proper noun and nothing else ("Amazon'da"). Both are exactly
            # where an invented employer or credential lands.
            if (
                sentence_initial
                and offset == 0
                and len(group.split()) == 1
                and not _looks_like_a_name(group)
                and not _carries_turkish_proper_suffix(text, match.start(), group)
            ):
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

    def flush() -> None:
        nonlocal current
        if current:
            groups.append((start, " ".join(current)))
            current = []

    for index, word in enumerate(words):
        if index in covered:
            flush()
            continue
        if lexicon.is_ambiguous(word):
            # A tool the tech rule had to skip. It is still checked — alone,
            # against the CV — rather than dragged into the phrase beside it.
            flush()
            groups.append((index, word))
            continue
        if not current:
            start = index
        current.append(word)
    flush()
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


#: Apostrophes Turkish uses to attach a case suffix to a proper noun.
_APOSTROPHES: Final[str] = "'\u2019\u02bc\u00b4`"


def _looks_like_a_name(word: str) -> bool:
    """Whether the shape of a word says "name" regardless of position.

    An acronym or an internally capitalised token — ``PhD``, ``AWS``, ``iOS``,
    ``GmbH`` — is never the grammar of a sentence opening. Ordinary words are
    capitalised only on the first letter.
    """
    letters = [character for character in word if character.isalpha()]
    if len(letters) < 2:
        return False
    return any(character.isupper() for character in letters[1:])


def _carries_turkish_proper_suffix(text: str, start: int, word: str) -> bool:
    """Whether the word is written with the apostrophe Turkish gives names.

    "Amazon'da" is an employer; "Yüzde 18" is a number. Turkish separates a
    case suffix from a proper noun with an apostrophe and from a common noun
    with nothing, which makes this the one reliable signal in the sentence's
    first word.
    """
    end = start + len(word)
    return end < len(text) and text[end] in _APOSTROPHES


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
    # Strip sentence punctuation the key carried in: "stakeholders." and
    # "stakeholders" are the same borrowing, and the full stop deciding it was
    # an accident of where the word fell in the sentence.
    return bool(_soft_forms(claim.key.strip(".")) & allowed_vocab)


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
    words it differently — but only when it runs to more than one word, is not
    a technology, and is not a number, date, duration or title.
    """
    if not generated.strip():
        return Verdict(ok=True)
    return Verifier(sources, lexicon=lexicon, posting_vocab=posting_vocab).check(generated)


class Verifier:
    """One CV's support index and one posting's vocabulary, held for reuse.

    :func:`verify` builds both every time it is called, which is the right
    trade when the caller has a handful of generated bullets to check. The
    document check reads a whole pasted CV or letter — hundreds of sentences
    against one unchanging CV — and rebuilding the index per sentence would be
    the same work done hundreds of times. The rule applied is identical; only
    the setup is shared.
    """

    def __init__(
        self,
        sources: list[str],
        *,
        lexicon: TechLexicon | None = None,
        posting_vocab: list[str] | None = None,
    ) -> None:
        self.lexicon = lexicon or DEFAULT_LEXICON
        self.index = SupportIndex(sources, self.lexicon)
        self.allowed = _vocab_index(posting_vocab or [], self.lexicon)

    def check(self, generated: str) -> Verdict:
        """The same verdict :func:`verify` would return for this sentence."""
        if not generated.strip():
            return Verdict(ok=True)
        unsupported = [
            claim
            for claim in extract_claims(generated, self.lexicon)
            if not supported(claim, self.index, self.allowed)
        ]
        return Verdict(ok=not unsupported, unsupported=unsupported)


def titles_in(text: str) -> set[str]:
    """Seniority and role words the text claims, normalised.

    Public because the CV audit asks the same question the verifier does — is
    this title carried by a line that can back it — just about the user's own
    document instead of about generated text.
    """
    return {normalize(match.group(0)) for match in _TITLE_RE.finditer(text)}


def title_surfaces(text: str) -> dict[str, str]:
    """Normalised title → the way ``text`` writes it, for showing it back."""
    found: dict[str, str] = {}
    for match in _TITLE_RE.finditer(text):
        found.setdefault(normalize(match.group(0)), match.group(0))
    return found


def year_ranges_in(text: str) -> list[tuple[int, int | None]]:
    """``(start, end)`` year pairs. ``end`` is ``None`` for an open range.

    "2019 – present" is open, and an open range is not a defect: it is the
    current job. The caller decides what today means.
    """
    ranges: list[tuple[int, int | None]] = []
    for match in _RANGE_RE.finditer(text):
        start = int(match.group(1))
        tail = match.group(2)
        ranges.append((start, int(tail) if tail.isdigit() else None))
    return ranges


def _vocab_index(posting_vocab: list[str], lexicon: TechLexicon) -> frozenset[str]:
    """Normalised wording the posting may lend to a rewrite.

    Two rules, and the second one is the fix for a leak the first never had:

    * a **multi-word** capitalised phrase is a concept by construction, so it
      is allowed unless the lexicon says it is a tool;
    * a **single word** is allowed only when :data:`CONCEPT_WORDS` lists it.

    That second rule used to read "allowed unless the lexicon knows it", which
    made an *unknown* word an allowed word — and every product, vendor and
    employer the lexicon had never heard of is an unknown word. A posting
    saying "Salesforce administration" licensed "Salesforce" in a tailored
    bullet whose CV lines never mentioned it. Now the burden runs the other
    way: a lone word has to be a listed concept or come from the CV.
    """
    allowed: set[str] = set()
    for entry in posting_vocab:
        for match in _PROPER_RE.finditer(entry):
            phrase = match.group(1).strip()
            if len(phrase.split()) < 2:
                continue  # a lone name is a fact; the word rule below judges it
            if lexicon.matches(normalize(phrase)):
                continue  # a tool named in the posting is still not yours
            allowed.add(normalize(phrase))
        for word in normalize(entry).split():
            if lexicon.knows(word):
                continue  # ditto, for a tool written in lowercase
            if is_concept(word):
                allowed.add(word)
    return frozenset(allowed)


# ─── Numeric helpers ──────────────────────────────────────────────────

_SUFFIX_FACTORS: Final[dict[str, float]] = {"k": 1_000.0, "m": 1_000_000.0, "bn": 1_000_000_000.0}

#: Currency signs written next to the amount.
_CURRENCY_CHARS: Final[str] = "$€£₺"

#: Unit words, normalised, mapped to the class the comparison uses. Anything
#: not listed here counts as *no unit*: "12 engineers" and "12 developers"
#: describe the same number, and policing the noun is the proper-noun rule's
#: job, not the number rule's. Turkish and English spellings share a class, so
#: a CV written in one language evidences a suggestion written in the other.
_UNIT_CLASSES: Final[dict[str, str]] = {
    "%": "percent", "percent": "percent", "percentage": "percent",
    "pct": "percent", "yuzde": "percent", "yuzdelik": "percent",
    "x": "times", "kat": "times",
    "usd": "money", "eur": "money", "gbp": "money", "try": "money",
    "tl": "money", "dolar": "money", "euro": "money", "lira": "money",
    "sterlin": "money",
    "ms": "ms", "millisecond": "ms", "milliseconds": "ms", "milisaniye": "ms",
    "sn": "second", "sec": "second", "secs": "second", "second": "second",
    "seconds": "second", "saniye": "second",
    "min": "minute", "mins": "minute", "minute": "minute",
    "minutes": "minute", "dk": "minute", "dakika": "minute",
    "hr": "hour", "hrs": "hour", "hour": "hour", "hours": "hour",
    "saat": "hour",
    "day": "day", "days": "day", "gun": "day",
    "week": "week", "weeks": "week", "hafta": "week",
    "month": "month", "months": "month", "mo": "month", "mos": "month",
    "ay": "month", "aylik": "month",
    "year": "year", "years": "year", "yr": "year", "yrs": "year",
    "yil": "year", "yillik": "year", "sene": "year",
    "kb": "kb", "mb": "mb", "gb": "gb", "tb": "tb",
}

_NEXT_WORD_RE: Final[re.Pattern[str]] = re.compile(r"\s*([^\W\d_]+)")
_PREV_WORD_RE: Final[re.Pattern[str]] = re.compile(r"([^\W\d_]+)\s*$")


def _unit_class(text: str, match: re.Match[str]) -> str:
    """The unit a numeric occurrence carries, or ``""`` when it carries none.

    The unit is part of the fact: a CV that says "40 hours a week" has not
    evidenced "40% conversion", however often 40 appears in it.
    """
    suffix = (match.group("suffix") or "").strip().casefold()
    if suffix in {"%", "x"}:
        return _UNIT_CLASSES[suffix]

    before = text[: match.start()].rstrip()
    if before and before[-1] in _CURRENCY_CHARS:
        return "money"

    after = _NEXT_WORD_RE.match(text[match.end() :])
    if after:
        unit = _UNIT_CLASSES.get(normalize(after.group(1)))
        if unit:
            return unit
    # Turkish puts some units in front of the number ("yüzde 40", "3 kat").
    prior = _PREV_WORD_RE.search(before)
    if prior:
        unit = _UNIT_CLASSES.get(normalize(prior.group(1)))
        if unit:
            return unit
    return ""


def _number_key(value: float, unit: str) -> str:
    return f"{value:g}|{unit}"


#: Numbers written as words. A model that cannot put "40%" past the verifier
#: can still write "forty percent", and "six weeks" is as much a promise to a
#: recruiter as "6 weeks" — so both sides of the comparison read them.
#:
#: "one"/"bir" are left out on purpose: they carry no weight in a CV bullet and
#: appear in ordinary prose constantly. The Turkish "on" (10) and "bin" (1000)
#: are an English preposition and an English noun, so they count only in the
#: company a number keeps — see :data:`_CONTEXT_WORD_VALUES`.
_WORD_VALUES: Final[dict[str, float]] = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
    "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "yedi": 7,
    "sekiz": 8, "dokuz": 9, "yirmi": 20, "otuz": 30, "kirk": 40,
    "elli": 50, "altmis": 60, "yetmis": 70, "seksen": 80, "doksan": 90,
}

_WORD_SCALES: Final[dict[str, float]] = {
    "hundred": 100, "thousand": 1_000, "million": 1_000_000,
    "billion": 1_000_000_000, "yuz": 100, "milyon": 1_000_000,
    "milyar": 1_000_000_000,
}

#: Verbs that state a factor. "Doubled deployment frequency" is a 2x claim
#: written without a digit, and it was passing untouched.
_MULTIPLIER_WORDS: Final[dict[str, float]] = {
    "double": 2, "doubled": 2, "doubling": 2, "twofold": 2,
    "triple": 3, "tripled": 3, "tripling": 3, "threefold": 3,
    "quadruple": 4, "quadrupled": 4, "fourfold": 4,
    "halved": 0.5, "halving": 0.5,
    "katladim": 2, "ikiye": 2, "yariya": 0.5,
}

_WORD_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+", re.UNICODE)

#: Units the duration rule understands, and therefore the units a spelled-out
#: number belongs to it rather than to the plain number rule.
_DURATION_UNITS: Final[frozenset[str]] = frozenset({"year", "month"})

#: Words that are a number in Turkish and something else in English. "on iki
#: yıl" is twelve years; "on Kubernetes" is a preposition. Reading them only
#: when a number or a unit follows separates the two without guessing which
#: language the line is in.
_CONTEXT_WORD_VALUES: Final[dict[str, float]] = {"on": 10}
_CONTEXT_SCALES: Final[dict[str, float]] = {"bin": 1_000}


#: Letters and function words that only a Turkish line carries. ``text.py``'s
#: language vote needs a paragraph to be sure; one bullet is all there is here,
#: and one Turkish letter is already decisive.
_TR_LETTERS: Final[frozenset[str]] = frozenset("ğışİĞŞÇÖÜçöü")
_TR_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "ve", "ile", "icin", "olarak", "yil", "ay", "hafta", "gun", "kisi",
        "deneyim", "ekip", "proje", "sirket", "musteri", "adet", "kadar",
        "uzerinde", "boyunca", "yonettim", "gelistirdim", "kurdum", "azalttim",
        "artirdim", "sagladim", "calistim", "hesabi", "hesap", "kullanici",
    }
)


def _reads_as_turkish(text: str) -> bool:
    """Whether this line is Turkish, for the length of one bullet."""
    if any(character in _TR_LETTERS for character in text):
        return True
    return bool(_TR_MARKERS & set(normalize(text).split()))


def _spelled_numbers(text: str) -> list[tuple[str, float, str]]:
    """Every number written as words, as ``(surface, value, unit)``.

    Runs of number words combine the way they are read — "twenty five" is 25,
    "five thousand" is 5000 — so a suggestion cannot dodge the digit rule by
    spelling the figure out.

    In a line that reads as Turkish, "on" and "bin" are numbers wherever they
    stand; in any other line they count only next to another number or a unit,
    because there they are just as likely to be an English preposition.
    """
    turkish = _reads_as_turkish(text)
    tokens = [(match.group(0), match.start(), match.end()) for match in _WORD_TOKEN_RE.finditer(text)]
    words = [normalize(token[0]) for token in tokens]

    def counts_here(position: int) -> bool:
        """Whether an ambiguous word is a number in this company."""
        if turkish:
            return True
        following = words[position + 1] if position + 1 < len(words) else ""
        return (
            following in _WORD_VALUES
            or following in _WORD_SCALES
            or following in _CONTEXT_WORD_VALUES
            or following in _UNIT_CLASSES
        )

    def value_of(position: int) -> float | None:
        word = words[position]
        if word in _WORD_VALUES:
            return _WORD_VALUES[word]
        if word in _CONTEXT_WORD_VALUES and counts_here(position):
            return _CONTEXT_WORD_VALUES[word]
        return None

    def scale_of(position: int, started: bool) -> float | None:
        word = words[position]
        if word in _WORD_SCALES:
            return _WORD_SCALES[word]
        if word in _CONTEXT_SCALES and (started or counts_here(position)):
            return _CONTEXT_SCALES[word]
        return None

    found: list[tuple[str, float, str]] = []
    index = 0
    while index < len(tokens):
        word = words[index]
        if word in _MULTIPLIER_WORDS:
            found.append((tokens[index][0], _MULTIPLIER_WORDS[word], "times"))
            index += 1
            continue
        if value_of(index) is None and scale_of(index, started=False) is None:
            index += 1
            continue

        total = 0.0
        current = 0.0
        end = tokens[index][2]
        cursor = index
        while cursor < len(tokens):
            part_value = value_of(cursor)
            part_scale = scale_of(cursor, started=cursor > index)
            if part_value is not None:
                current += part_value
            elif part_scale is not None:
                current = (current or 1.0) * part_scale
                total += current
                current = 0.0
            else:
                break
            end = tokens[cursor][2]
            cursor += 1

        unit = ""
        if cursor < len(tokens):
            unit = _UNIT_CLASSES.get(words[cursor], "")
        found.append((text[tokens[index][1] : end], total + current, unit))
        index = cursor
    return found


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
    """Every ``value|unit`` pair the source states, in canonical form."""
    values: set[str] = set()
    for match in _NUMBER_RE.finditer(text):
        unit = _unit_class(text, match)
        number = _to_number(match.group("value"), match.group("suffix"))
        if number is not None:
            values.add(_number_key(number, unit))
        # A source "1k" also vouches for a generated "1000" and vice versa, so
        # index the bare value too.
        bare = _to_number(match.group("value"))
        if bare is not None:
            values.add(_number_key(bare, unit))
    for match in _DURATION_RE.finditer(text):
        # Indexed under the duration's own unit: "5 years in backend" states a
        # span, not the number 5, so it must not evidence "5 features".
        number = _to_number(match.group("count"))
        if number is not None:
            values.add(_number_key(number, _unit_of(match.group("unit"))))
    # "Led four engineers" has to be evidenced by a CV that writes "4", and
    # vice versa: both sides read words and digits alike.
    for _surface, value, unit in _spelled_numbers(text):
        values.add(_number_key(value, unit))
        values.add(_number_key(value, ""))
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
    # A CV that writes "five years" states the same span as one writing "5".
    for _surface, value, unit in _spelled_numbers(text):
        if unit in _DURATION_UNITS:
            found.add((value, unit))
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
