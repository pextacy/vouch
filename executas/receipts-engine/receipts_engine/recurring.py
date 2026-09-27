"""What keeps coming up — the only question one application cannot answer.

The app has been honest about one posting at a time and learned nothing across
them. Someone applies twenty times, "no Kubernetes evidence" comes back
unproven in fifteen of those, and nothing ever says so. That is the question a
single match structurally cannot answer — *which gap is actually costing me
jobs?* — and this is the only app that can, because it already stores a
verified per-requirement verdict for every application the user has made.

No model, no tokens. Grouping is lexicon work, which is why it lives here
rather than in the UI: "Experience running services on Kubernetes" and
"Kubernetes in production" are the same gap, and deciding that in TypeScript
would mean a second copy of `verify/lexicon.py` drifting out of step with this
one.

**The denominator is the whole point.** A count of how often something came
back unproven says nothing on its own: fifteen unproven out of fifteen asked is
the thing to go learn, and fifteen out of two hundred is noise. Worse, a term
asked twenty times and proved eighteen of them would show two unproven and read
as a recurring gap — telling someone their strongest skill is their weakness.
So every group carries ``asked`` beside ``unproven``, and a gap has to be
unproven *every* time to be called one.

Two rules keep the grouping honest:

* **A gap that happened once is not a pattern.** Singletons are excluded;
  calling one a trend would be the app overclaiming from thin data.
* **Merge only what the lexicon vouches for.** A requirement joins a term's
  group when the lexicon finds that term in it; requirements the lexicon does
  not recognise group only with requirements whose wording normalises to
  exactly the same string. No fuzzy matching, because a wrong merge is an
  invisible lie while a split the user can see in ``texts`` is only untidy.
"""

from __future__ import annotations

from typing import Final

from .schemas import Kind, RecurringGroup, RecurringInput, RecurringResult
from .text import normalize
from .verify import DEFAULT_LEXICON

#: Below this there is no "keeps coming up" to speak of, and a report drawn
#: from two applications would be a horoscope.
MIN_MATCHES: Final[int] = 3

#: A gap that happened once is not a pattern.
MIN_OCCURRENCES: Final[int] = 2

#: Bounds the work and the payload. Forty applications of ~15 requirements.
MAX_ITEMS: Final[int] = 2000

#: Enough to act on. A longer list is a reading exercise, not a plan.
MAX_GROUPS: Final[int] = 10


class _Bucket:
    """Everything one key accumulates while the items are scanned."""

    __slots__ = ("asked", "ids", "kind", "must", "surface", "texts", "unproven")

    def __init__(self, surface: str) -> None:
        self.surface = surface
        self.kind: Kind = "nice"
        self.ids: list[str] = []
        self.texts: list[str] = []
        self.asked: set[str] = set()
        self.unproven: set[str] = set()
        self.must: set[str] = set()


def recurring_gaps(items: list[RecurringInput]) -> RecurringResult:
    """Group past requirements by what they were really asking for."""
    items = items[:MAX_ITEMS]
    seen_matches = {item.match for item in items}
    if len(seen_matches) < MIN_MATCHES:
        # A real answer, not an error: the screen says "come back after a few
        # more applications" rather than inventing a pattern out of two.
        return RecurringResult(matches=len(seen_matches))

    buckets: dict[str, _Bucket] = {}
    for item in items:
        for key, surface in keys_for(item.text):
            bucket = buckets.setdefault(key, _Bucket(surface))
            bucket.ids.append(item.id)
            if item.text not in bucket.texts:
                bucket.texts.append(item.text)
            bucket.asked.add(item.match)
            if item.kind == "must":
                bucket.must.add(item.match)
                bucket.kind = "must"
            if item.status != "strong":
                bucket.unproven.add(item.match)

    groups = [
        _as_group(key, bucket)
        for key, bucket in buckets.items()
        if len(bucket.asked) >= MIN_OCCURRENCES and len(bucket.unproven) == len(bucket.asked)
    ]
    strengths = [
        _as_group(key, bucket)
        for key, bucket in buckets.items()
        if len(bucket.asked) >= MIN_OCCURRENCES and not bucket.unproven
    ]

    return RecurringResult(
        matches=len(seen_matches),
        groups=_ranked(groups),
        strengths=_ranked(strengths),
    )


def keys_for(text: str) -> list[tuple[str, str]]:
    """The ``(key, surface)`` pairs this requirement belongs under.

    Public because `compare.py` groups the same way: two screens that merged
    requirements differently would disagree about what the user was asked for.

    A requirement naming two technologies belongs under both: an application
    asking for Go *and* Kubernetes really did ask for each of them, so counting
    it once per term is the honest tally rather than double counting.
    """
    spellings = DEFAULT_LEXICON.surfaces(text)
    if spellings:
        return sorted(spellings.items())
    # Nothing the lexicon knows. Group only on an exact normalised match —
    # the conservative floor, since anything looser would merge on a guess.
    normalized = normalize(text)
    return [(f"text:{normalized}", text.strip())] if normalized else []


def _as_group(key: str, bucket: _Bucket) -> RecurringGroup:
    return RecurringGroup(
        key=key[:120],
        # Never empty: the UI renders it unconditionally, and a blank heading
        # would be worse than a clumsy one.
        surface=(bucket.surface or key.removeprefix("text:") or key)[:120],
        kind=bucket.kind,
        asked=len(bucket.asked),
        unproven=len(bucket.unproven),
        must=len(bucket.must),
        ids=bucket.ids,
        texts=bucket.texts[:5],
    )


def _ranked(groups: list[RecurringGroup]) -> list[RecurringGroup]:
    """Must-haves first, then by how often it came up, then stably by name."""
    groups.sort(key=lambda g: (0 if g.kind == "must" else 1, -g.asked, g.key))
    return groups[:MAX_GROUPS]
