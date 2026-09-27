"""Which lines do the work — the CV read back through the applications it was sent with.

Every other screen reads the CV as a *source*: the match cites it, the tailor
rewrites from it, the brief quotes it. Nothing has ever read it as a *record* —
which of these twenty-odd sentences has actually carried an application, and
which has been on the page for two years without a single posting ever needing
it.

That question is unanswerable for every other tool in this category, and
already answered here: the app stores, for each application, which requirement
each CV line was accepted as evidence for. Counting it is the whole feature.
A tool that guesses which bullet is "strong" is describing a CV; this is
describing what the CV *did*.

**No model, no tokens, no quota**, like `audit_cv`, `recurring_gaps` and
`interview_brief`. Every number here is a citation a verifier already made, in
an application the user can open and check.

Three things it says, and the second is the one that needs care:

=============  ============================================================
doing the work lines cited in the most applications. Where the page should
               start, and — with ``decisive`` — which single sentence an
               application was resting on.
never asked    lines no posting has ever needed. **Not** "cut these": the
               screen says so out loud. A line is uncited when the jobs the
               person applied to never asked about that work, which is a
               fact about the postings, not about the work.
what you added the sentences the user typed into Receipts answering a gap,
               and what those have proved since. The payback of the answer
               loop, which until now the app asked for and never reported.
=============  ============================================================

Two rules keep it from lying about someone's document.

**The citations must be about *this* document.** A line id is a position, not
a sentence: `L12` in a re-parsed CV is a different line than `L12` was, so
counting an application made against another version would put someone else's
receipt under the wrong sentence — quiet wrongness of exactly the kind this
product exists to prevent. The UI marks an edited CV by suffixing the engine's
hash (`lib/cv.markEdited`), so the *base* of the hash identifies the parsed
document and the suffix only says it has grown since. Applications whose base
differs are not counted, and the count of them is reported rather than
swallowed (`skipped`), because a silently smaller denominator is the failure
this module is trying to avoid in the first place.

**Header lines are not part of it.** A name, an email and a city are not
evidence and will never be cited; listing them under "never asked for" would
be the app inviting someone to cut their own phone number.
"""

from __future__ import annotations

import re
from typing import Final

from .recurring import keys_for
from .schemas import CVDoc, LedgerLine, LedgerResult, RecurringInput

#: Below this the ledger is just the match map again. Two applications cannot
#: say which line does the work; they can only say which line the last posting
#: happened to ask about. The same floor, for the same reason, as
#: `recurring.MIN_MATCHES`.
MIN_MATCHES: Final[int] = 3

#: Bounds the work and the payload — forty applications of ~15 requirements,
#: the same ceiling the recurring report reads.
MAX_ITEMS: Final[int] = 2000

#: Enough to act on when re-ordering a page. A longer list is the CV again.
MAX_WORKING: Final[int] = 12

#: Long enough to be useful, short enough not to read as a hit list. The total
#: is reported separately, so the screen can say how many it is not showing.
MAX_IDLE: Final[int] = 12

#: The answer loop's own section. Someone with more added lines than this has
#: a second CV, not a longer list.
MAX_ADDED: Final[int] = 8

#: Per line. "Cited for Kubernetes, Go, Terraform" is a description; ten terms
#: is a paragraph nobody reads.
MAX_PROVES: Final[int] = 5

#: The suffix `lib/cv.markEdited` adds each time the user edits or adds a line.
#: Everything before it is the hash of the parsed document, which is what says
#: whether a saved citation points at the lines on screen.
_EDITED: Final[re.Pattern[str]] = re.compile(r"~e\d+$")


def base_hash(value: str) -> str:
    """The parsed document's hash, with any edit marker removed.

    Two CVs share a base exactly when they came from the same parse — which is
    exactly when a line id means the same sentence in both. The engine's own
    hashes never contain ``~``, so this is unambiguous.
    """
    return _EDITED.sub("", value.strip())


class _Tally:
    """What one CV line accumulated across every application it was cited in."""

    __slots__ = ("citations", "decisive", "matches", "must", "surfaces")

    def __init__(self) -> None:
        self.matches: set[str] = set()
        self.citations = 0
        self.must = 0
        self.decisive = 0
        #: canonical key → (how the postings spelled it, how often)
        self.surfaces: dict[str, tuple[str, int]] = {}


def line_ledger(cv: CVDoc, items: list[RecurringInput]) -> LedgerResult:
    """Count what each CV line has actually proved, and what it never has."""
    items = items[:MAX_ITEMS]
    base = base_hash(cv.hash)

    # A line id only means something against the document it was written for.
    counted = [item for item in items if base_hash(item.cv_hash) == base]
    skipped = {item.match for item in items} - {item.match for item in counted}
    matches = {item.match for item in counted}

    body = [line for line in cv.lines if line.section != "header"]
    eligible = len(body)

    if len(matches) < MIN_MATCHES:
        # A real answer, not an error: the screen asks the user to come back
        # rather than ranking their CV from one posting's opinion of it.
        return LedgerResult(
            applications=len(matches),
            skipped=len(skipped),
            eligible=eligible,
        )

    known = {line.id for line in body}
    order = {line.id: index for index, line in enumerate(body)}
    written = {line.id for line in body if line.added_at is not None}
    tallies: dict[str, _Tally] = {}

    for item in counted:
        # `missing` is the verdict that cited nothing. If a record carries line
        # ids under it anyway, they were not evidence — the match said so.
        if item.status == "missing":
            continue
        cited = [line_id for line_id in dict.fromkeys(item.line_ids) if line_id in known]
        if not cited:
            continue
        for line_id in cited:
            tally = tallies.setdefault(line_id, _Tally())
            tally.matches.add(item.match)
            tally.citations += 1
            if item.kind == "must":
                tally.must += 1
                # The application was resting on this one sentence.
                if len(cited) == 1:
                    tally.decisive += 1
            _record_surfaces(tally, item.text)

    working = sorted(
        (
            _as_line(line_id, tallies[line_id], added=line_id in written)
            for line_id in tallies
        ),
        key=lambda line: (-line.applications, -line.citations, -line.must, order[line.id]),
    )
    idle = [
        _as_line(line.id, None, added=line.id in written)
        for line in body
        if line.id not in tallies
    ]
    added = sorted(
        (_as_line(line_id, tallies.get(line_id), added=True) for line_id in written),
        key=lambda line: (-line.applications, -line.citations, order[line.id]),
    )

    return LedgerResult(
        applications=len(matches),
        skipped=len(skipped),
        eligible=eligible,
        cited=len(tallies),
        working=working[:MAX_WORKING],
        idle=idle[:MAX_IDLE],
        added=added[:MAX_ADDED],
    )


def _record_surfaces(tally: _Tally, text: str) -> None:
    """Remember what the posting called the thing this line answered.

    Grouped by `recurring.keys_for`, so "Kubernetes in production" and
    "Experience running services on Kubernetes" are one demand here too — the
    three screens that read across applications must never disagree about what
    the user was asked for.
    """
    for key, surface in keys_for(text):
        spelling, count = tally.surfaces.get(key, (surface, 0))
        tally.surfaces[key] = (spelling, count + 1)


def _as_line(line_id: str, tally: _Tally | None, *, added: bool) -> LedgerLine:
    if tally is None:
        return LedgerLine(id=line_id, added=added)
    proves = [
        spelling
        for _, (spelling, _) in sorted(
            tally.surfaces.items(), key=lambda entry: (-entry[1][1], entry[0])
        )
    ]
    return LedgerLine(
        id=line_id,
        applications=len(tally.matches),
        citations=tally.citations,
        must=tally.must,
        decisive=tally.decisive,
        proves=proves[:MAX_PROVES],
        added=added,
    )
