"""Which application is worth the hour — the question asked *before* applying.

The app answers "does this CV fit this posting" one posting at a time, and
`recurring.py` answers "what keeps costing me jobs" across all of them. Between
those two sits the decision a job seeker actually makes on a Sunday evening:
three postings are open in three tabs, there is time to tailor one properly,
and nothing anywhere says which one.

Every other tool answers that with a fit score — a number invented by the same
model that wrote the CV bullets, precise to a percentage point about something
it guessed. This app already holds something better: a verified per-requirement
verdict for each of those postings, made one at a time, each one citing lines.
Lining them up is arithmetic over verdicts that already exist.

**No model, no tokens, no quota**, like `audit_cv` and `recurring_gaps`. It
groups with the same lexicon `recurring.py` uses, because the comparison is
only worth reading if "Experience running services on Kubernetes" in one
posting and "Kubernetes in production" in another are known to be the same
demand — and deciding that in TypeScript would mean a second copy of
`verify/lexicon.py` drifting out of step with this one.

Three things are reported per posting, and none of them is a score:

===========  ==============================================================
counts       must-haves proved out of must-haves asked, and the same for the
             whole posting. Two integers a person can check against the
             match map they came from.
blockers     the must-haves this posting asks for and the CV does not prove.
             The reason to spend the hour somewhere else.
edge         what this posting asks for, the CV proves, and at least one of
             the others never asks about at all. The thing only a comparison
             can tell you: where the evidence you already have is worth the
             most.
===========  ==============================================================

And two things are reported about the set: what every one of them asks for and
none of them proves — one answer there changes every application on the screen
— and what every one of them asks for and the CV proves every time. A report
that is only a list of failures stops being read, the same reason
`summarize.py` drops its second sentence when there is nothing to warn about.

The ordering is by evidence, and the screen says so: fewest unproved
must-haves first. That is not "which job you want", and this module has no
opinion about that.
"""

from __future__ import annotations

from typing import Final

from .recurring import keys_for
from .schemas import CompareColumn, CompareResult, Kind, RecurringGroup, RecurringInput

#: One posting cannot be compared with itself, and the answer to "which one"
#: needs at least two to be a question at all.
MIN_POSTINGS: Final[int] = 2

#: Four fits on a 360 px screen as a list of readable rows. Beyond that the
#: screen becomes a table nobody reads and the decision it exists to help with
#: has stopped being a decision.
MAX_POSTINGS: Final[int] = 4

#: Four postings of a hundred requirements. Bounds the work and the payload.
MAX_ITEMS: Final[int] = 400

#: Per column. A longer list stops being the reason to choose and becomes
#: another thing to read.
MAX_TERMS: Final[int] = 5

#: Across the set.
MAX_SHARED: Final[int] = 6


class _Term:
    """What one posting asked for, under one canonical key."""

    __slots__ = ("ids", "kind", "proved", "surface", "texts")

    def __init__(self, surface: str) -> None:
        self.surface = surface
        self.kind: Kind = "nice"
        self.proved = False
        self.ids: list[str] = []
        self.texts: list[str] = []


def compare_postings(items: list[RecurringInput]) -> CompareResult:
    """Line up saved applications against the verdicts they already carry."""
    items = items[:MAX_ITEMS]
    order: list[str] = []
    rows: dict[str, list[RecurringInput]] = {}
    for item in items:
        if item.match not in rows:
            # Past the cap the extra postings are dropped rather than
            # truncating one of them halfway: a column built from half a
            # posting's requirements would report counts that are simply wrong.
            if len(rows) >= MAX_POSTINGS:
                continue
            order.append(item.match)
            rows[item.match] = []
        rows[item.match].append(item)

    if len(order) < MIN_POSTINGS:
        # A real answer, not an error: the screen asks for a second one rather
        # than rendering a comparison of one thing with nothing.
        return CompareResult(postings=len(order))

    terms = {match: _terms_for(rows[match]) for match in order}
    columns = [_column(match, rows[match], terms) for match in order]

    return CompareResult(
        postings=len(order),
        columns=_ranked(columns, order),
        shared_gaps=_shared(order, terms, proved=False),
        shared_proved=_shared(order, terms, proved=True),
    )


def _terms_for(items: list[RecurringInput]) -> dict[str, _Term]:
    """What one posting asked for, keyed the way the lexicon groups it.

    A requirement naming two technologies is counted under both: a posting
    asking for Go *and* Kubernetes really did ask for each of them.
    """
    terms: dict[str, _Term] = {}
    for item in items:
        for key, surface in keys_for(item.text):
            term = terms.setdefault(key, _Term(surface))
            term.ids.append(item.id)
            if item.text not in term.texts:
                term.texts.append(item.text)
            if item.kind == "must":
                term.kind = "must"
            # Any requirement under this key that the CV proved is enough: the
            # question this answers is "can you show them something", and one
            # cited line is something.
            if item.status == "strong":
                term.proved = True
    return terms


def _column(
    match: str, items: list[RecurringInput], terms: dict[str, dict[str, _Term]]
) -> CompareColumn:
    musts = [item for item in items if item.kind == "must"]
    elsewhere = [other for other in terms if other != match]

    return CompareColumn(
        match=match,
        asked=len(items),
        proved=sum(1 for item in items if item.status == "strong"),
        related=sum(1 for item in items if item.status == "partial"),
        must_asked=len(musts),
        must_proved=sum(1 for item in musts if item.status == "strong"),
        blockers=_blockers(musts),
        edge=[
            term.surface
            for key, term in terms[match].items()
            if term.proved and any(key not in terms[other] for other in elsewhere)
        ][:MAX_TERMS],
    )


def _blockers(musts: list[RecurringInput]) -> list[str]:
    """The must-haves this posting asks for and the CV does not prove.

    Named the way the lexicon knows them where it knows them, and by the
    posting's own wording where it does not — a blocker the user cannot
    recognise is not a reason to choose, it is a puzzle.
    """
    surfaces: list[str] = []
    for item in musts:
        if item.status == "strong":
            continue
        found = [surface for _key, surface in keys_for(item.text)]
        for surface in found or [item.text.strip()]:
            if surface and surface not in surfaces:
                surfaces.append(surface)
    return surfaces[:MAX_TERMS]


def _shared(
    order: list[str], terms: dict[str, dict[str, _Term]], *, proved: bool
) -> list[RecurringGroup]:
    """What every compared posting asks for, and the CV proves in all or none.

    A term proved in two postings out of three says nothing worth acting on:
    the verdict came from the same CV, so a split means the postings asked for
    different things under one word. Only the unanimous rows are stated, which
    is the same silence `recurring.py` keeps over a mixed record.
    """
    first = terms[order[0]]
    groups: list[RecurringGroup] = []
    for key, term in first.items():
        others = [terms[match].get(key) for match in order[1:]]
        if any(other is None for other in others):
            continue
        members = [term, *[other for other in others if other is not None]]
        if any(member.proved != proved for member in members):
            continue
        texts: list[str] = []
        for member in members:
            for text in member.texts:
                if text not in texts:
                    texts.append(text)
        groups.append(
            RecurringGroup(
                key=key[:120],
                surface=(term.surface or key.removeprefix("text:") or key)[:120],
                kind="must" if any(member.kind == "must" for member in members) else "nice",
                asked=len(order),
                unproven=0 if proved else len(order),
                must=sum(1 for member in members if member.kind == "must"),
                ids=[member_id for member in members for member_id in member.ids],
                texts=texts[:5],
            )
        )
    groups.sort(key=lambda group: (0 if group.kind == "must" else 1, group.key))
    return groups[:MAX_SHARED]


def _ranked(columns: list[CompareColumn], order: list[str]) -> list[CompareColumn]:
    """Fewest unproved must-haves first — the only ranking the evidence licenses.

    A must-have with nothing behind it is what stops an application, so it
    sorts first; ties fall to the one that proves more of them, then to the one
    that proves more overall, and finally to the order the user picked, so the
    list never reshuffles itself between two equal postings.
    """
    position = {match: index for index, match in enumerate(order)}
    return sorted(
        columns,
        key=lambda column: (
            column.must_asked - column.must_proved,
            -column.must_proved,
            -column.proved,
            position[column.match],
        ),
    )
