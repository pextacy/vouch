"""Stage 5 — counts and the one-line summary. No model involved.

Deterministic on purpose: the number the user screenshots and the number the
tracker stores must be the same number, and neither should cost a token.
"""

from __future__ import annotations

from ..schemas import Evidence, MatchSummary, Requirement


def summarize(
    requirements: list[Requirement], evidence: list[Evidence], locale: str
) -> MatchSummary:
    by_id = {item.requirement_id: item for item in evidence}
    strong = partial = missing = must_missing = 0

    for req in requirements:
        status = by_id[req.id].status if req.id in by_id else "missing"
        if status == "strong":
            strong += 1
        elif status == "partial":
            partial += 1
        else:
            missing += 1
            if req.kind == "must":
                must_missing += 1

    total = len(requirements)
    return MatchSummary(
        total=total,
        strong=strong,
        partial=partial,
        missing=missing,
        must_missing=must_missing,
        sentence=sentence_for(total, strong + partial, must_missing, locale),
    )


def sentence_for(total: int, evidenced: int, must_missing: int, locale: str) -> str:
    """"9 of 14 requirements have evidence in your CV. 2 must-haves don't."

    The second sentence is omitted when there is nothing to report — a summary
    that always ends in a warning stops being read.
    """
    if locale == "tr":
        head = f"{total} gereksinimden {evidenced} tanesi CV'nizde kanıtlanıyor."
        if must_missing == 1:
            return f"{head} 1 zorunlu madde için kanıt yok."
        if must_missing > 1:
            return f"{head} {must_missing} zorunlu madde için kanıt yok."
        return head
    head = f"{evidenced} of {total} requirements have evidence in your CV."
    if must_missing == 1:
        return f"{head} 1 must-have doesn't."
    if must_missing > 1:
        return f"{head} {must_missing} must-haves don't."
    return head
