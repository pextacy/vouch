"""The verifier, turned on a document this app did not write.

Everything else in `verify/` guards text Receipts **generates**: a tailored
bullet, a letter paragraph, a gap question's angle. That guarantee stops at
the edge of the app, and the edge is exactly where people live. Someone
exports their bullets, pastes them into the CV they designed in Word, adds a
line at 1 a.m., and sends it. Someone else has a CV another tool "improved"
for them last spring and has never read closely since. Neither document was
ever checked by anything, and both are the one an employer actually reads.

So this reads a pasted document sentence by sentence and applies the same rule
`tailor` and `letter` are held to: a number, date, duration, tool, employer or
job title that the CV cannot back is a claim the person will be asked about.
The difference is what happens next. The app cannot edit someone's file and
would not want to — it says which sentence, quotes the words, and offers the
one honest repair it has: *say where it actually happened*, and the sentence
becomes a CV line, verbatim, like every other answer in this product.

**No model, no tokens, no quota.** It is the same deterministic pass the
tailored bullets already go through, so it is instant, free, offline, and it
works the moment a CV exists — before there is a posting, and for a document
that has nothing to do with any posting the app has seen.

Three things are deliberately *not* claims here, and all three are the same
thing: the envelope is not the letter.

* ``[Company]``-style placeholders, which the verifier already blanks — they
  are the honest alternative to a guessed name, and punishing them would
  punish the behaviour the letter prompt asks for;
* the company and role of the open application, when there is one. The name of
  the employer being written to is the address on the envelope, not a claim
  about the candidate's career. The result says which words were disregarded,
  because a check that quietly ignores things is not a check;
* who the letter is addressed to and how it signs off — "Dear Hiring Manager",
  "Sayın Yetkili", "Kind regards". Every one of those is **anchored** on a word
  that can only be addressing (`_ADDRESS_PATTERNS`), so the rule stays
  deny-by-default: an experience line reading "Hiring Manager at Globex,
  2019–2023" is checked like any other, because nothing in it is a greeting.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from .errors import EngineError
from .schemas import CheckedClaim, CheckedLine, CVDoc, DocumentCheck, MatchResult
from .text import clean, normalize, trim_to_chars
from .verify import DEFAULT_LEXICON, Claim, Verifier

#: How much of a pasted document is read. A CV runs to about 4k characters and
#: a long one with a letter under it to maybe 12k; 20k leaves room without
#: letting a pasted book turn a free action into a slow one.
MAX_CHARS: Final[int] = 20_000

#: Sentences read. Reached only by a document already past ``MAX_CHARS`` worth
#: of very short lines, and it keeps the response well inside the stdio cap.
MAX_UNITS: Final[int] = 600

#: Flagged sentences returned. A document where every other line is flagged has
#: one problem and it is not a list — past this the user needs to rewrite, not
#: to scroll. The true count rides along in ``unbacked``.
MAX_FLAGGED: Final[int] = 40

#: Claims shown per sentence. Six unbacked facts in one sentence already says
#: everything the seventh would.
MAX_CLAIMS_PER_LINE: Final[int] = 6

#: A sentence is quoted back so the user can find it in their own file. Past
#: this it is a paragraph that resisted splitting, and the opening is enough
#: to locate it.
MAX_QUOTED_CHARS: Final[int] = 400

#: Shorter than this a company or role name is initials or a common word
#: ("IBM" is fine, "AI" is not), and blanking it would blank real sentences.
MIN_MASKABLE_CHARS: Final[int] = 3

#: Split a line where a full stop is followed by something that opens a
#: sentence. Deliberately conservative: over-splitting only shortens a quote,
#: because support is looked up against the whole CV and never per sentence,
#: while under-splitting would point the user at a paragraph.
_SENTENCE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?…])[ \t]+(?=[^\W\d_])")

#: A unit worth checking has something in it that could be a fact.
_HAS_CONTENT_RE: Final[re.Pattern[str]] = re.compile(r"[^\W_]", re.UNICODE)

#: How a letter addresses someone and how it signs off. Blanked before the
#: check for the same reason the company is: a salutation is the envelope.
#:
#: Every pattern is anchored on a word that does nothing but address — "Dear",
#: "Sayın", "To Whom", a closing formula — so this stays a list of greetings
#: rather than a list of forgiven words. "Hiring Manager" on its own is still
#: a title claim, because on its own that is what it is.
_ADDRESS_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern, re.IGNORECASE | re.UNICODE)
    for pattern in (
        # "Dear Ms. Chen", "Dear Hiring Manager", "Dear Sir or Madam", "Dear Alex"
        r"\bdear\s+(?:mr|mrs|ms|miss|dr|prof)\.?\s*[^\W\d_][\w'’-]*(?:\s+[^\W\d_][\w'’-]*)?",
        r"\bdear\s+(?:hiring|recruiting|recruitment|talent)\s+(?:manager|team|lead|partner)",
        r"\bdear\s+(?:sir(?:\s+(?:or|and)\s+madam)?|madam|colleagues?|team)",
        r"\bdear\s+[^\W\d_][\w'’-]*",
        r"\bto\s+whom\s+it\s+may\s+concern",
        r"\bsayın\s+(?:yetkili(?:si)?|ilgili|[^\W\d_][\w'’-]*)",
        r"\b[iİ]nsan\s+kaynakları(?:\s+(?:departmanı|yetkilisi|müdürü))?",
        r"\b[iİ]nsan\s+kaynaklari(?:\s+(?:departmani|yetkilisi|muduru))?",
        # Sign-offs. Only the formula itself — a title typed under it is a claim.
        r"\byours\s+(?:sincerely|faithfully|truly)",
        r"\b(?:best|kind|warm)\s+regards",
        r"\b(?:sincerely|regards|saygılarımla|saygilarimla)",
        r"\biyi\s+(?:çalışmalar|calismalar)",
    )
)


def check_document(
    cv: CVDoc,
    document: str,
    *,
    match: MatchResult | None = None,
    company: str | None = None,
    role: str | None = None,
) -> DocumentCheck:
    """Read ``document`` against ``cv`` and report what it cannot back."""
    if not cv.lines:
        raise EngineError("cv_too_short", "there is no CV to check this document against")

    text = clean(document)
    if not text.strip():
        raise EngineError("invalid_args", "check_document needs a document")

    text, truncated = trim_to_chars(text, MAX_CHARS)
    masked_terms = _maskable(match=match, company=company, role=role)
    blank = _blanker(masked_terms)

    verifier = Verifier(
        [line.text for line in cv.lines],
        posting_vocab=[requirement.text for requirement in match.requirements] if match else None,
    )

    units = _units(text)
    if len(units) > MAX_UNITS:
        units = units[:MAX_UNITS]
        truncated = True

    unbacked = 0
    flagged: list[CheckedLine] = []
    for index, unit in enumerate(units):
        # Blanked per sentence rather than over the whole document: a masked
        # name ending in a full stop ("Acme Inc.") would otherwise take a
        # sentence boundary with it, and the quoted text and the checked text
        # would stop describing the same sentence.
        verdict = verifier.check(blank(unit))
        if verdict.ok:
            continue
        unbacked += 1
        if len(flagged) < MAX_FLAGGED:
            flagged.append(
                CheckedLine(
                    index=index,
                    text=unit[:MAX_QUOTED_CHARS],
                    claims=[
                        CheckedClaim(kind=claim.kind, surface=_surface(claim, unit))
                        for claim in _distinct(verdict.unsupported)[:MAX_CLAIMS_PER_LINE]
                    ],
                )
            )

    return DocumentCheck(
        cv_hash=cv.hash,
        checked=len(units),
        unbacked=unbacked,
        flagged=flagged,
        truncated=truncated,
        masked=masked_terms,
    )


def _units(text: str) -> list[str]:
    """The document as sentences, in the order it writes them.

    Lines first, because a CV is a list and its bullets are not sentences;
    then sentences within a line, because a cover-letter paragraph is one line
    and flagging the whole of it would tell the user nothing about where to
    look.
    """
    units: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        for piece in _SENTENCE_SPLIT_RE.split(stripped):
            candidate = piece.strip()
            if candidate and _HAS_CONTENT_RE.search(candidate):
                units.append(candidate)
    return units


#: Punctuation a claim can pick up from the end of a sentence. It is part of
#: the sentence, never part of the fact, and quoting "Globex." back at someone
#: reads as a machine that did not look properly.
_TRAILING: Final[str] = ".,;:!?)\u2019'\"\u201d"


def _surface(claim: Claim, unit: str) -> str:
    """The claim as **the checked document** writes it.

    ``extract_claims`` returns the lexicon's canonical term for a technology,
    which is the right key to compare with and the wrong string to show:
    someone who wrote "k8s" did not write "kubernetes", and being quoted words
    they never typed is how a user stops trusting the rest of the list
    (`CLAUDE.md`, rule 9).
    """
    if claim.kind == "tech":
        written = DEFAULT_LEXICON.surfaces(unit).get(claim.key)
        if written:
            return written.strip(_TRAILING)[:80]
    return claim.surface.strip(_TRAILING)[:80] or claim.surface[:80]


def _distinct(claims: list[Claim]) -> list[Claim]:
    """One entry per phrase the user has to look at.

    The verifier already returns one claim per ``(kind, key)``, but a word can
    be two kinds at once — "Senior" is a title and reads as a proper noun —
    and telling someone twice about the same word in the same sentence reads
    as the app not having looked properly.
    """
    seen: dict[str, None] = {}
    unique: list[Claim] = []
    for claim in claims:
        key = normalize(claim.surface)
        if key not in seen:
            seen[key] = None
            unique.append(claim)
    return unique


def _maskable(
    *, match: MatchResult | None, company: str | None, role: str | None
) -> list[str]:
    """The posting's own company and role — the envelope, not a claim.

    Explicit arguments win over the match's: the UI knows what it substituted
    into the letter it rendered, and the posting's extracted title can be
    wordier than the one the user actually wrote.
    """
    candidates = [
        company or (match.posting.company if match else None),
        role or (match.posting.title if match else None),
    ]
    terms: list[str] = []
    for candidate in candidates:
        term = (candidate or "").strip()
        if len(term) >= MIN_MASKABLE_CHARS and term not in terms:
            terms.append(term)
    return terms


def _blanker(terms: list[str]) -> Callable[[str], str]:
    """A function that replaces ``terms`` with spaces, offsets intact.

    Length-preserving for the same reason ``_mask_placeholders`` is: the
    verifier decides whether a capitalised word is a name or the grammar of a
    sentence opening by looking at what precedes it, and a substitution that
    moved the text would change that answer.
    """
    patterns = [re.compile(re.escape(term), re.IGNORECASE) for term in terms]
    patterns.extend(_ADDRESS_PATTERNS)

    def blank(text: str) -> str:
        for pattern in patterns:
            text = pattern.sub(lambda hit: " " * len(hit.group(0)), text)
        return text

    return blank
