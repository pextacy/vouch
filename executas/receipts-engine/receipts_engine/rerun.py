"""What the second run changed — the payoff the app kept asking for and never showed.

Four screens now ask the user to write a sentence into their CV: a gap
question, an audit finding, a recurring gap, and "since you applied", whose
whole argument is *run this posting again*. They run it again, and the app
hands back a fresh match map with no memory of the first one. The one moment
this entire product is built towards — **the line you wrote turned a "no
evidence" into a receipt** — was the moment it had nothing to say.

Only this app can say it. Two verified per-requirement verdicts for the same
posting, made weeks apart against a CV whose every added line carries a date,
is a comparison nobody else is holding the records for.

**No model, no tokens**, like every other reading action. Two stored results
and a lexicon.

The hard part is that the two runs are not the same list. Requirements are
re-extracted each time, so `R3` in one is not `R3` in the other, and a posting
pasted twice can even yield a different number of them. So they are lined up
the way every cross-application screen in this app lines things up — on
`recurring.keys_for`, the lexicon that already decides "Kubernetes in
production" and "Experience running services on Kubernetes" are one demand.
Requirements it does not recognise group on their exact normalised wording,
which is the conservative floor: a wrong pairing would tell someone a gap
closed when it did not.

Three honesties the screen depends on:

* **What moved the other way is reported too.** A requirement can lose its
  evidence between two runs — the posting was pasted differently, or the model
  read a line differently — and a screen that only ever showed gains would be
  a congratulation rather than a record.
* **Credit is only claimed where it is earned.** `credited` is set when the
  newer run cites a line the user wrote *after the older run*. Anything else
  moved for reasons this module cannot see, and it says nothing rather than
  taking the credit.
* **A changed question is not an answer.** Terms only one of the runs asked
  about are kept apart from the gains and losses, because that difference is
  about the reading, not about the candidate. This is also where the
  lexicon's limits land in plain sight: two runs of one posting can word the
  same demand differently ("Backend engineering in Go", "Go experience"), and
  because `Go` is one of the ambiguous one-word terms the lexicon skips, that
  pair cannot be joined. It shows up as two entries with the verdict each run
  gave, which is untidy — and the honest alternative to guessing that two
  sentences mean the same thing and reporting a gain that never happened.
"""

from __future__ import annotations

from typing import Final

from .recurring import keys_for
from .schemas import CVDoc, Kind, MatchResult, RunChange, RunDiff, Status
from .since import parse_moment

#: Per list. A diff longer than this has stopped being "what changed".
MAX_ITEMS: Final[int] = 12

#: How the three verdicts order. Only the ranking is meaningful, not the gaps
#: between the numbers — nothing here is averaged or scored.
_RANK: Final[dict[str, int]] = {"missing": 0, "partial": 1, "strong": 2}


class _Side:
    """What one run said about one term."""

    __slots__ = ("kind", "line_ids", "status", "surface", "texts")

    def __init__(self, surface: str) -> None:
        self.surface = surface
        self.kind: Kind = "nice"
        self.status: Status = "missing"
        self.line_ids: list[str] = []
        self.texts: list[str] = []

    def add(self, *, kind: Kind, status: Status, line_ids: list[str], text: str) -> None:
        if kind == "must":
            self.kind = "must"
        # The best verdict any wording of this demand got in this run: asked
        # twice and proved once is proved, the same way the match map reads.
        if _RANK[status] >= _RANK[self.status]:
            self.status = status
        for line_id in line_ids:
            if line_id not in self.line_ids:
                self.line_ids.append(line_id)
        if text not in self.texts:
            self.texts.append(text)


def compare_runs(cv: CVDoc, before: MatchResult, after: MatchResult) -> RunDiff:
    """Line up two runs of the same posting and say what actually moved."""
    first = _sides(before)
    second = _sides(after)

    # Lines the user wrote between the two runs: the only thing in the CV that
    # the older run could not possibly have seen.
    boundary = parse_moment(before.created_at)
    earned = {
        line.id
        for line in cv.lines
        if line.added_at is not None
        and boundary is not None
        and (parse_moment(line.added_at) or boundary) > boundary
    }

    gained: list[RunChange] = []
    lost: list[RunChange] = []
    still: list[RunChange] = []
    differed: list[RunChange] = []

    for key in sorted(set(first) | set(second)):
        old = first.get(key)
        new = second.get(key)
        if old is None or new is None:
            # One of the runs never asked. That is a fact about the postings,
            # not about the CV, so it is kept out of the gains and losses.
            side = new or old
            assert side is not None
            differed.append(
                _change(
                    key,
                    side,
                    before=old.status if old else None,
                    after=new.status if new else None,
                    direction="new_ask" if new else "dropped_ask",
                    earned=earned,
                )
            )
            continue

        if _RANK[new.status] > _RANK[old.status]:
            gained.append(
                _change(key, new, before=old.status, after=new.status, direction="gained", earned=earned)
            )
        elif _RANK[new.status] < _RANK[old.status]:
            lost.append(
                _change(key, new, before=old.status, after=new.status, direction="lost", earned=earned)
            )
        elif new.status != "strong":
            still.append(
                _change(key, new, before=old.status, after=new.status, direction="same", earned=earned)
            )

    return RunDiff(
        before_id=before.id,
        after_id=after.id,
        days_between=_days(before.created_at, after.created_at),
        before_strong=before.summary.strong,
        before_total=before.summary.total,
        after_strong=after.summary.strong,
        after_total=after.summary.total,
        added_between=sorted(earned, key=_line_order),
        gained=_ranked(gained),
        lost=_ranked(lost),
        still=_ranked(still),
        differed=_ranked(differed),
    )


def _sides(match: MatchResult) -> dict[str, _Side]:
    """Every term one run asked about, with the verdict it gave."""
    verdicts = {evidence.requirement_id: evidence for evidence in match.evidence}
    sides: dict[str, _Side] = {}
    for requirement in match.requirements:
        evidence = verdicts.get(requirement.id)
        for key, surface in keys_for(requirement.text):
            side = sides.setdefault(key, _Side(surface))
            side.add(
                kind=requirement.kind,
                # No entry is the same "nothing was proven" every other screen
                # in this app reads it as.
                status=evidence.status if evidence else "missing",
                line_ids=list(evidence.line_ids) if evidence else [],
                text=requirement.text,
            )
    return sides


def _change(
    key: str,
    side: _Side,
    *,
    before: Status | None,
    after: Status | None,
    direction: str,
    earned: set[str],
) -> RunChange:
    cited = side.line_ids if after is not None else []
    return RunChange(
        key=key[:120],
        surface=(side.surface or key.removeprefix("text:") or key)[:120],
        kind=side.kind,
        before=before,
        after=after,
        direction=direction,  # type: ignore[arg-type]
        line_ids=cited[:5],
        # Only where it is earned: the newer run is standing on a sentence the
        # older run never saw.
        credited=direction == "gained" and any(line_id in earned for line_id in cited),
        texts=side.texts[:5],
    )


def _ranked(changes: list[RunChange]) -> list[RunChange]:
    """Must-haves first, then the ones the user earned, then stably by name."""
    changes.sort(key=lambda change: (0 if change.kind == "must" else 1, 0 if change.credited else 1, change.key))
    return changes[:MAX_ITEMS]


def _line_order(line_id: str) -> tuple[int, str]:
    digits = line_id[1:]
    return (int(digits), line_id) if digits.isdigit() else (1 << 30, line_id)


def _days(before: str, after: str) -> int | None:
    start, end = parse_moment(before), parse_moment(after)
    if start is None or end is None:
        return None
    return max(0, (end - start).days)
