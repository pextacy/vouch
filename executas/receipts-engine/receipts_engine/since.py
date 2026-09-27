"""What changed since you sent it — the app's other silence.

The tracker records that an application went out and then the product stops
having anything to say about it. Meanwhile three screens are quietly growing
the CV underneath it: a gap answer, an audit finding, a recurring gap. Someone
applies to a posting that wanted Kafka, comes back a week later, writes the
sentence about the Kafka consumer they actually rewrote — and nothing
anywhere connects that sentence to the five applications it would have
changed. The evidence arrived after the envelope.

Nobody else can join those two records. This app already stores the
per-requirement verdict for every application and the date on every line the
user has written into their CV, so it can say *"this posting asked for
something your application could not show, and your CV has since gained a line
that names it."*

**No model, no tokens, no quota**, like `audit_cv`, `recurring_gaps`,
`interview_brief` and `line_ledger`. It is date arithmetic and a lexicon
lookup over records that already exist.

**It says "names", never "proves".** Deciding that a sentence is evidence for a
requirement is the match's job, and the match is a model call with a verifier
behind it. All this module knows is that the same term appears in both, which
is a reason to run the match again — not a verdict, and the UI copy is written
to match. Anything stronger would be the app grading its own homework with the
one tool it does not trust for the job.

Two consequences of that modesty are worth stating:

* a requirement the lexicon does not recognise can never light up here. It
  groups on canonical terms, and no fuzzy fallback: a wrong hit would send
  someone to re-run an application over a coincidence of wording.
* only lines the user added **after the application went out** count. A line
  that was already in the CV was in front of the match when it ran, and the
  match said what it said.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from .recurring import keys_for
from .schemas import CVDoc, CVLine, MatchResult, SinceAnswer, SinceResult
from .verify import DEFAULT_LEXICON

#: Per requirement. Three sentences naming the same term is already the answer;
#: a longer list is the CV screen with extra steps.
MAX_LINES: Final[int] = 3

#: Requirements worth reporting. Must-haves first, and past this many the
#: screen has stopped being "here is what changed" and become a second match.
MAX_ANSWERS: Final[int] = 8


def since_applied(
    cv: CVDoc,
    match: MatchResult,
    *,
    sent_at: str | None = None,
    now: datetime | None = None,
) -> SinceResult:
    """What has happened to the CV since this application went out."""
    checked = parse_moment(match.created_at)
    sent = parse_moment(sent_at) if sent_at else None
    # The application's own clock: when the user marked it sent, else when the
    # match was run. Saying "applied 9 days ago" off the wrong one would be a
    # small lie in the one sentence the screen opens with.
    reference = sent or checked
    moment = now or datetime.now(UTC)

    added = [
        line
        for line in cv.lines
        if line.added_at is not None and _after(line.added_at, reference)
    ]

    # A requirement with no evidence entry was never proved either: silence
    # has not been evidence anywhere else in this app.
    verdict = {evidence.requirement_id: evidence.status for evidence in match.evidence}

    answers: list[SinceAnswer] = []
    for requirement in match.requirements:
        status = verdict.get(requirement.id, "missing")
        if status == "strong":
            continue
        hits, terms = naming_lines(requirement.text, added)
        if hits:
            answers.append(
                SinceAnswer(
                    requirement_id=requirement.id,
                    kind=requirement.kind,
                    status=status,
                    line_ids=hits[:MAX_LINES],
                    terms=terms,
                )
            )

    # Must-haves first; within that, the posting's own order, which a stable
    # sort preserves. A must-have the application could not show is the one
    # worth re-running for.
    answers.sort(key=lambda answer: 0 if answer.kind == "must" else 1)

    return SinceResult(
        match_id=match.id,
        days=_days_between(reference, moment),
        dated_from="sent" if sent else "checked",
        cv_changed=cv.hash != match.cv_hash,
        added=[line.id for line in added],
        answers=answers[:MAX_ANSWERS],
    )


def naming_lines(text: str, lines: list[CVLine]) -> tuple[list[str], list[str]]:
    """Which of ``lines`` name what ``text`` asks for, spelled as the CV does.

    The one rule both this module and `worth.py` depend on, so it lives in one
    place: the screen that asks "is this application worth another look" and
    the one that asks it of every application at once must never disagree
    about what counts as naming something.

    Returns the ids that named it and the terms they shared. A requirement the
    lexicon does not recognise returns nothing — staying silent is the only
    honest option, because a fuzzy hit would send someone to spend a model
    call re-running an application over two sentences that happen to share a
    word.
    """
    wanted = {key for key, _ in keys_for(text) if not key.startswith("text:")}
    if not wanted:
        return [], []

    hits: list[str] = []
    terms: dict[str, str] = {}
    for line in lines:
        spellings = DEFAULT_LEXICON.surfaces(line.text)
        shared = wanted & set(spellings)
        if not shared:
            continue
        hits.append(line.id)
        for key in sorted(shared):
            # The CV's own spelling, not the canonical term: it is the user's
            # own sentence being quoted back to them (`audit.py`).
            terms.setdefault(key, spellings[key])
    return hits, [terms[key] for key in sorted(terms)]


def parse_moment(value: str) -> datetime | None:
    """An ISO timestamp, whether it ends in ``Z`` or ``+00:00``.

    The UI writes `Date.toISOString()` (`…Z`) and the engine writes
    `datetime.isoformat()` (`…+00:00`), so these two are compared as instants
    and never as strings.

    Public because `rerun.py` needs the same reading of the same fields: two
    modules parsing `added_at` differently would disagree about which
    sentences arrived after an application went out, which is the one fact
    both of them are for.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _after(value: str, reference: datetime | None) -> bool:
    """Whether ``value`` happened after the application went out.

    An unreadable or missing reference means the app cannot tell, and a line
    it cannot date is not reported as new: the whole claim of this screen is
    that something arrived *after* the envelope.
    """
    moment = parse_moment(value)
    return bool(moment and reference and moment > reference)


def _days_between(reference: datetime | None, now: datetime) -> int | None:
    if reference is None:
        return None
    return max(0, (now - reference).days)
