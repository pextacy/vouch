"""Which of your applications are worth another look — all of them, at once.

`since.py` answers this for one application, and answers it well. It is also
the wrong shape for the person it was built for: someone who applies to thirty
jobs a month is not going to open thirty saved applications one at a time to
find out whether last Tuesday's sentence changed any of them. The answer
existed and nothing was going to read it.

So this is the same question asked of the whole shelf: for every application,
did the CV gain a line **after that application went out** that names
something that application could not show? A job seeker cannot answer it
alone, because the evidence is spread across thirty postings they sent one at
a time, and no other tool holds both halves — a verified per-requirement
verdict for every application, and a date on every line the person has
written.

**No model, no tokens**, like the rest of the reading actions. Dates and a
lexicon.

It shares `since.naming_lines` with the single-application screen rather than
re-deriving it, because the two must never disagree about what counts as
naming something — one of them says "this application is worth reopening" and
the other is what the user sees when they do.

The modesty is the same too, and it is the reason the screen can be trusted to
be short: **names is not proves.** A row here is a reason to spend one model
call, not a verdict, and the list stays empty until the user's own writing
gives it something to say.
"""

from __future__ import annotations

from typing import Final

from .schemas import CVDoc, CVLine, RecurringInput, WorthItem, WorthResult
from .since import naming_lines, parse_moment

#: Bounds the work and the payload — the same forty applications the recurring
#: report reads, at ~15 requirements each.
MAX_ITEMS: Final[int] = 2000

#: Applications on screen. Past this it is a reading exercise rather than a
#: list of things to do, and the ones below the cut are the weakest anyway.
MAX_ROWS: Final[int] = 10

#: Per row. Enough to recognise the application; the match itself has the rest.
MAX_TERMS: Final[int] = 5
MAX_LINES: Final[int] = 3
MAX_TEXTS: Final[int] = 3


class _Row:
    """What one application accumulates while the feed is scanned."""

    __slots__ = ("lines", "must", "requirements", "terms", "texts", "unproved")

    def __init__(self) -> None:
        self.unproved = 0
        self.requirements = 0
        self.must = 0
        self.terms: list[str] = []
        self.lines: list[str] = []
        self.texts: list[str] = []


def worth_rerunning(cv: CVDoc, items: list[RecurringInput]) -> WorthResult:
    """Every saved application the CV has since gained an answer for."""
    items = items[:MAX_ITEMS]
    written = [line for line in cv.lines if line.added_at is not None]
    seen: list[str] = []
    rows: dict[str, _Row] = {}

    for item in items:
        if item.match not in rows:
            seen.append(item.match)
            rows[item.match] = _Row()
        row = rows[item.match]
        if item.status == "strong":
            continue
        row.unproved += 1

        # Only what the application could not have read. A line written before
        # it went out was in front of that match when it ran, and the match
        # said what it said.
        candidates = _written_since(written, item.created_at)
        if not candidates:
            continue
        hits, terms = naming_lines(item.text, candidates)
        if not hits:
            continue

        row.requirements += 1
        if item.kind == "must":
            row.must += 1
        for line_id in hits:
            if line_id not in row.lines:
                row.lines.append(line_id)
        for term in terms:
            if term not in row.terms:
                row.terms.append(term)
        if item.text not in row.texts:
            row.texts.append(item.text)

    worth = [
        WorthItem(
            match=match,
            unproved=rows[match].unproved,
            requirements=rows[match].requirements,
            must=rows[match].must,
            terms=rows[match].terms[:MAX_TERMS],
            line_ids=rows[match].lines[:MAX_LINES],
            texts=rows[match].texts[:MAX_TEXTS],
        )
        for match in seen
        if rows[match].requirements > 0
    ]
    # Must-haves first — a must-have an application could not show is what
    # decided it — then how much is newly named, then the order the caller
    # sent them in, which is the tracker's own order.
    worth.sort(key=lambda item: (-item.must, -item.requirements))

    return WorthResult(
        applications=len(seen),
        written=len(written),
        items=worth[:MAX_ROWS],
    )


def _written_since(written: list[CVLine], created_at: str) -> list[CVLine]:
    """The user's lines that this application never saw.

    An application whose date cannot be read gets nothing rather than
    everything: the whole claim of a row here is that a sentence arrived
    *after* it went out, and without a date there is no after.
    """
    boundary = parse_moment(created_at) if created_at else None
    if boundary is None:
        return []
    return [
        line
        for line in written
        if line.added_at is not None
        and (moment := parse_moment(line.added_at)) is not None
        and moment > boundary
    ]
