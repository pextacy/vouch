"""Pydantic twins of the TypeScript interfaces in ``docs/docs.md §4``.

Two families live here:

* **Wire models** (``CVDoc``, ``MatchResult``, …) — what crosses the tool
  boundary to the UI.
* **LLM models** (``ExtractionOutput``, ``MatchingOutput``, …) — what the model
  is asked to produce. These are deliberately flatter and have **no optional
  fields and no defaults**, because the sampling host's strict ``json_schema``
  mode requires every property to be listed in ``required``.

Both use ``extra="forbid"``: a model that invents a field fails validation
instead of smuggling it through.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: Re-exported rather than restated. ``CheckedClaim.kind`` *is* a verifier
#: claim class (`docs.md §6`), and a second copy of the list here would be one
#: more thing to keep true the next time the verifier learns a new kind.
from .verify.grounding import ClaimKind

Section = Literal[
    "header",
    "summary",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "other",
]
Status = Literal["strong", "partial", "missing"]
Kind = Literal["must", "nice"]
Category = Literal["skill", "experience", "education", "domain", "soft", "logistics"]
Language = Literal["en", "tr", "other"]
Locale = Literal["en", "tr"]
Tone = Literal["plain", "warm", "formal"]
Length = Literal["short", "standard"]
Warning = Literal["multi_column_suspected", "tables_flattened", "truncated"]
CvFindingKind = Literal["skill_unevidenced", "title_unevidenced", "date_conflict"]
#: What an interviewer is most likely to press on, for one requirement. Named
#: from the evidence's *shape*, never from a judgement about the person: the
#: UI turns each into a sentence, in the user's language (`docs.md §3`).
BriefRisk = Literal[
    "no_evidence",
    "self_asserted",
    "listed_not_shown",
    "self_added",
    "related_only",
    "proved",
]
ClaimSource = Literal["bullet", "letter"]
#: What the CV could do with one question an employer asked. Named from the
#: *evidence*, never from a judgement about the candidate, and never a
#: sentence: the UI turns each into copy in the user's language (`docs.md §3`).
#:
#: ``not_about_you`` is the one this feature exists for. "Why do you want to
#: work here?" cannot be answered from a CV at all — a CV records what someone
#: did, not what they want — so the honest output is no output. Every other
#: tool in this category writes that paragraph anyway.
AnswerKind = Literal["answered", "no_evidence", "not_about_you"]

LineId = Annotated[str, StringConstraints(pattern=r"^L\d+$")]
RequirementId = Annotated[str, StringConstraints(pattern=r"^R\d+$")]


class Strict(BaseModel):
    """Base for every model in this module."""

    model_config = ConfigDict(extra="forbid", frozen=False)


# ─── Wire models ──────────────────────────────────────────────────────


class CVLine(Strict):
    id: LineId
    text: str
    section: Section
    #: ISO date the user added this line themselves, answering a gap question.
    #: A parsed line never carries one, so the UI can mark what came from the
    #: original document and what the person added afterwards — a line that
    #: became evidence should say where it came from.
    added_at: str | None = None


class CVDoc(Strict):
    version: Literal[1] = 1
    hash: str
    lines: list[CVLine]
    detected_language: Language
    warnings: list[Warning] = Field(default_factory=list)

    def text_by_id(self) -> dict[str, str]:
        return {line.id: line.text for line in self.lines}

    def numbered(self, ids: list[str] | None = None) -> str:
        """Render lines as ``L<n>: text`` — the only form the LLM ever sees."""
        wanted = set(ids) if ids is not None else None
        return "\n".join(
            f"{line.id}: {line.text}"
            for line in self.lines
            if wanted is None or line.id in wanted
        )


class Requirement(Strict):
    id: RequirementId
    text: Annotated[str, StringConstraints(max_length=120)]
    kind: Kind
    category: Category
    source_quote: Annotated[str, StringConstraints(max_length=200)]


class Evidence(Strict):
    requirement_id: RequirementId
    status: Status
    line_ids: list[LineId] = Field(default_factory=list)
    why: Annotated[str, StringConstraints(max_length=160)]
    #: Technologies the requirement named that the cited lines do not show.
    #: Present only on a `strong` verdict the guard cut back to `partial`
    #: (`pipeline/match.py`), written the way the **posting** spells them. No
    #: sentence: the UI says what it means, in the user's language.
    unshown: list[Annotated[str, StringConstraints(max_length=80)]] = Field(default_factory=list)


class PostingMeta(Strict):
    title: str | None = None
    company: str | None = None
    url: str | None = None
    hash: str
    language: Language


class MatchSummary(Strict):
    total: int
    strong: int
    partial: int
    missing: int
    must_missing: int
    sentence: str


class MatchResult(Strict):
    version: Literal[1] = 1
    id: str
    created_at: str
    posting: PostingMeta
    requirements: list[Requirement]
    evidence: list[Evidence]
    summary: MatchSummary
    cv_hash: str


class TailoredBullet(Strict):
    source_line_ids: list[LineId]
    original: str
    suggestion: str | None = None
    targets: list[RequirementId] = Field(default_factory=list)
    dropped_reason: Literal["unsupported_claims"] | None = None
    unsupported_tokens: list[str] = Field(default_factory=list)


class TailorResult(Strict):
    version: Literal[1] = 1
    match_id: str
    bullets: list[TailoredBullet]


class LetterParagraph(Strict):
    text: str
    line_ids: list[LineId] = Field(default_factory=list)


class CvFinding(Strict):
    """One thing in the user's own CV that an interviewer is likely to probe.

    No prose: the engine names the kind and the subject, and the UI supplies
    the sentence from its own string table, in the user's language — the same
    split error codes use (`docs.md §3`). An engine that phrased the accusation
    would be writing untranslated copy nobody reviewed.
    """

    kind: CvFindingKind
    #: The canonical term, for comparison and for grouping: ``grpc``,
    #: ``senior``, ``2019-2023``. Never a sentence.
    subject: Annotated[str, StringConstraints(max_length=80)]
    #: The same thing as the **CV** writes it — ``gRPC``, ``Senior``, ``k8s``.
    #: Showing someone the canonical form reads as the app not having looked
    #: properly: their skills list does not say "grpc", it says "gRPC". Equal
    #: to ``subject`` when the CV happens to write it that way, or when there
    #: is no distinct surface to recover.
    surface: Annotated[str, StringConstraints(max_length=80)] = ""
    line_ids: list[LineId] = Field(default_factory=list)


class CvAudit(Strict):
    version: Literal[1] = 1
    cv_hash: str
    findings: list[CvFinding] = Field(default_factory=list)


class CheckedClaim(Strict):
    """One fact in a pasted document that the CV cannot back.

    No sentence, the same rule as `CvFinding`: the engine names the claim
    class and quotes the document's own words, and the UI says what that
    means in the user's language (`docs.md §3`).
    """

    kind: ClaimKind
    #: Exactly as the checked document writes it — "40%", "Kubernetes",
    #: "Senior". Quoting it back is what lets the user find it in their file.
    surface: Annotated[str, StringConstraints(max_length=80)]


class CheckedLine(Strict):
    """One sentence of the document, and what it claims without evidence."""

    #: Position among the sentences the check read, so the screen lists them
    #: in the order they appear in the document the user is looking at.
    index: int
    text: Annotated[str, StringConstraints(max_length=400)]
    claims: list[CheckedClaim] = Field(default_factory=list)


class DocumentCheck(Strict):
    """The verifier's verdict on a document Receipts did not write.

    Nothing here is stored: the document arrives, is read, and is gone. What
    survives a check is whatever the user chose to add to their CV afterwards,
    in their own words — the same loop as a gap question.
    """

    version: Literal[1] = 1
    #: The CV the document was checked against.
    cv_hash: str
    #: Sentences read. The denominator, for the same reason `RecurringGroup`
    #: carries one: "6 sentences flagged" says nothing on its own.
    checked: int = 0
    #: Sentences carrying at least one unbacked claim — the true count, which
    #: may exceed ``len(flagged)`` when the cap cut the list.
    unbacked: int = 0
    flagged: list[CheckedLine] = Field(default_factory=list)
    #: True when the document was longer than the check reads.
    truncated: bool = False
    #: The posting's company and role, when a saved application was open. Both
    #: are blanked before checking — the name of the employer being written to
    #: is the address on the envelope, not a claim about the candidate — and
    #: the screen says which words it disregarded rather than deciding quietly.
    masked: list[str] = Field(default_factory=list)


class RecurringInput(Strict):
    """One requirement from one past application, as the UI replays it.

    The replay feed, and deliberately one shape rather than three: three
    screens read the user's saved applications — what keeps coming up, which
    one to spend the hour on, and which CV lines do the work — and a second
    builder projecting the same records differently is a second thing that can
    drift (`lib/recurring.replayItems` is the only one).

    ``match`` is an opaque grouping key — the engine never interprets it, it
    only counts distinct values, so "asked in 7 applications" means seven
    applications and not seven bullet points in the same posting.
    """

    id: str
    match: str
    text: Annotated[str, StringConstraints(max_length=200)]
    kind: Kind
    status: Status
    #: The lines this requirement was matched to. Read by ``line_ledger``
    #: alone; `recurring_gaps` and `compare_postings` count verdicts and never
    #: look at them.
    line_ids: list[LineId] = Field(default_factory=list)
    #: When this application was run (`MatchResult.created_at`). Read by
    #: ``worth_rerunning`` alone, which needs to know which of the user's own
    #: lines each application could not possibly have seen.
    created_at: str = ""
    #: The CV this application was checked against (`MatchResult.cv_hash`).
    #: Also the ledger's alone, and it is what keeps that screen honest: a
    #: line id is a position, so a citation only means something against the
    #: document it was written for (`ledger.base_hash`).
    cv_hash: str = ""


class RecurringGroup(Strict):
    """One thing the market kept asking this person for."""

    #: Canonical lexicon term when one matched, else a normalised text key.
    key: Annotated[str, StringConstraints(max_length=120)]
    #: How the postings write it. Never empty — the UI renders it directly.
    surface: Annotated[str, StringConstraints(max_length=120)]
    #: ``must`` when any application asked for it as a must-have; that is the
    #: one that decides whether an application was worth sending.
    kind: Kind
    #: Distinct applications that asked. The denominator — without it
    #: "unproven 15 times" says nothing about whether that is most of them.
    asked: int
    #: Of those, how many the CV could not prove.
    unproven: int
    #: Of those, how many asked for it as a must-have.
    must: int
    ids: list[str] = Field(default_factory=list)
    #: The distinct wordings that were grouped, so the screen can show what it
    #: merged and the user can disagree with it rather than trust it.
    texts: list[str] = Field(default_factory=list)


class RecurringResult(Strict):
    version: Literal[1] = 1
    #: Distinct applications the report is drawn from.
    matches: int = 0
    #: Asked more than once and never proved — what to actually go learn.
    groups: list[RecurringGroup] = Field(default_factory=list)
    #: Asked more than once and always proved. A report that is only a list of
    #: failures stops being read — the same reason `summarize.py` drops its
    #: second sentence when there is nothing to warn about.
    strengths: list[RecurringGroup] = Field(default_factory=list)


class CompareColumn(Strict):
    """One saved application, as a comparison with the others reads it.

    Counts, not a score. Every number here is a tally of verdicts the match
    already recorded, so the user can check any of them against the match map
    it came from — which is the one thing a fit percentage can never offer.
    """

    #: The match id the UI sent. The engine never reads it, only groups by it;
    #: the role and the company stay in the UI, which is where the copy lives.
    match: str
    asked: int
    proved: int
    related: int
    must_asked: int
    must_proved: int
    #: Must-haves this posting asks for and the CV cannot prove — the reason to
    #: spend the hour somewhere else. Lexicon surfaces, else the posting's own
    #: wording.
    blockers: list[str] = Field(default_factory=list)
    #: Proved here, and not asked for by at least one of the others. What only
    #: a comparison can say: where the evidence already in hand is worth most.
    edge: list[str] = Field(default_factory=list)


class CompareResult(Strict):
    version: Literal[1] = 1
    #: Distinct applications compared. Below two there are no columns at all.
    postings: int = 0
    #: Ranked, fewest unproved must-haves first.
    columns: list[CompareColumn] = Field(default_factory=list)
    #: Asked by every one of them and proved in none — one answer here changes
    #: every application on the screen.
    shared_gaps: list[RecurringGroup] = Field(default_factory=list)
    #: Asked by every one of them and proved every time.
    shared_proved: list[RecurringGroup] = Field(default_factory=list)


class LedgerLine(Strict):
    """One CV line, and what it has actually carried.

    No text and no section: the caller is holding the CV these ids came from,
    and a second copy of the sentence could disagree with the document the
    user is reading it next to — the same rule `BriefItem` follows.
    """

    id: LineId
    #: Distinct applications that cited it. The numerator; ``applications`` on
    #: the result is the denominator, and neither means anything alone.
    applications: int = 0
    #: Requirements it was accepted as evidence for, across those.
    citations: int = 0
    #: Of those, how many were must-haves.
    must: int = 0
    #: Must-haves where this was the **only** line cited. The application was
    #: resting on this one sentence, which is worth knowing before an
    #: interviewer reads it.
    decisive: int = 0
    #: What the postings called the things it answered, grouped by the lexicon
    #: `recurring_gaps` uses, most-asked first.
    proves: list[str] = Field(default_factory=list)
    #: The user wrote this line here, answering a gap (``CVLine.added_at``).
    added: bool = False


class LedgerResult(Strict):
    """What every line of the CV has proved, and what none of it has."""

    version: Literal[1] = 1
    #: Applications the ledger counted. Below `ledger.MIN_MATCHES` the lists
    #: are empty and the screen says so rather than ranking a CV from one
    #: posting's opinion of it.
    applications: int = 0
    #: Applications left out because they were checked against a different
    #: version of this CV, where the same line ids mean different sentences.
    #: Reported rather than swallowed: a quietly smaller denominator is the
    #: failure this screen exists to avoid.
    skipped: int = 0
    #: CV lines that could be cited — everything but the header, which is a
    #: name and a phone number rather than evidence.
    eligible: int = 0
    #: Of those, how many have been evidence at least once.
    cited: int = 0
    #: Cited lines, most applications first.
    working: list[LedgerLine] = Field(default_factory=list)
    #: Lines no application has ever cited. Not a cut list — see `ledger.py`.
    idle: list[LedgerLine] = Field(default_factory=list)
    #: The lines the user added themselves, and what they have proved since.
    added: list[LedgerLine] = Field(default_factory=list)


class SinceAnswer(Strict):
    """A requirement the application could not show, and what the CV now names.

    Deliberately not called evidence. Deciding that a sentence *proves* a
    requirement is the match's job — a model call with a verifier behind it —
    and this is a lexicon hit between two strings. It is a reason to run the
    match again, which is exactly what the screen says.
    """

    requirement_id: RequirementId
    kind: Kind
    #: The verdict this requirement got when the application went out.
    status: Status
    #: Lines the user has added since, which name the same thing.
    line_ids: list[LineId] = Field(default_factory=list)
    #: The terms they share, spelled as the **CV** writes them — it is the
    #: user's own new sentence being quoted back (`CvFinding.surface`).
    terms: list[Annotated[str, StringConstraints(max_length=80)]] = Field(default_factory=list)


class SinceResult(Strict):
    """What has happened to the CV since one application went out."""

    version: Literal[1] = 1
    match_id: str
    #: Days since it was sent, or None when nothing datable was recorded.
    days: int | None = None
    #: Whether ``days`` counts from the day the user marked it sent, or from
    #: the day the match was run. Records written before the tracker stamped
    #: its statuses only have the second, and the copy differs.
    dated_from: Literal["sent", "checked"] = "checked"
    #: The CV is not the document this application was checked against.
    cv_changed: bool = False
    #: Lines the user has written into the CV since it went out.
    added: list[LineId] = Field(default_factory=list)
    #: Must-haves first. Empty is the common answer, and the screen is written
    #: for it: most weeks nothing has changed.
    answers: list[SinceAnswer] = Field(default_factory=list)


#: How one demand moved between two runs of the same posting. Read off two
#: verdicts, never judged: ``gained`` and ``lost`` are both just a change of
#: rank, and the two ``*_ask`` values are about the postings differing rather
#: than about the candidate.
RunDirection = Literal["gained", "lost", "same", "new_ask", "dropped_ask"]


class RunChange(Strict):
    """One thing both runs were asked about, and what each of them said."""

    #: Canonical lexicon term when one matched, else a normalised text key —
    #: the same grouping `recurring_gaps` and `compare_postings` use, because
    #: two runs of one posting word their requirements differently and
    #: matching them on `R3` would compare two unrelated demands.
    key: Annotated[str, StringConstraints(max_length=120)]
    surface: Annotated[str, StringConstraints(max_length=120)]
    kind: Kind
    #: What the older run said. ``None`` when it never asked.
    before: Status | None = None
    #: What the newer run said. ``None`` when it no longer asks.
    after: Status | None = None
    direction: RunDirection
    #: What the newer run cited for it.
    line_ids: list[LineId] = Field(default_factory=list)
    #: The newer run is standing on a line the user wrote after the older one.
    #: Set only on a gain, and only where the citation proves it — anything
    #: else moved for reasons this comparison cannot see, and it says nothing
    #: rather than taking the credit.
    credited: bool = False
    #: The wordings that were grouped, so the user can disagree with the
    #: pairing rather than trust it (`RecurringGroup.texts`).
    texts: list[str] = Field(default_factory=list)


class RunDiff(Strict):
    """Two runs of one posting, lined up."""

    version: Literal[1] = 1
    before_id: str
    after_id: str
    #: Days between the two runs; None when either date is unreadable.
    days_between: int | None = None
    #: Each run's own summary, quoted rather than recomputed. The totals can
    #: differ — the posting is re-read each time — and saying so is the point
    #: of showing both.
    before_strong: int = 0
    before_total: int = 0
    after_strong: int = 0
    after_total: int = 0
    #: Lines the user wrote between the two runs: the only thing in the CV the
    #: older run could not have seen.
    added_between: list[LineId] = Field(default_factory=list)
    #: Unproved then, proved now. The screen this module exists for.
    gained: list[RunChange] = Field(default_factory=list)
    #: And the other way. A record that only showed gains would be a
    #: congratulation, not a record.
    lost: list[RunChange] = Field(default_factory=list)
    #: Unproved in both runs — what is still worth answering.
    still: list[RunChange] = Field(default_factory=list)
    #: Asked by one run and not the other. About the postings, not the CV.
    differed: list[RunChange] = Field(default_factory=list)


class WorthItem(Strict):
    """One saved application the CV has since gained an answer for.

    The engine never sees the role or the company — ``match`` is the opaque
    key the UI sent, and the copy lives where the tracker's own wording does
    (`RecurringInput`).
    """

    match: str
    #: Requirements this application could not prove, whatever has happened
    #: since. The denominator: "2 of the 5 it could not show" is a different
    #: sentence from "2 of the 2".
    unproved: int = 0
    #: Of those, how many the CV now names.
    requirements: int = 0
    #: Of those, how many were must-haves — what decided the application.
    must: int = 0
    #: The terms, spelled as the CV writes them.
    terms: list[Annotated[str, StringConstraints(max_length=80)]] = Field(default_factory=list)
    #: The lines that named them, all written after this application went out.
    line_ids: list[LineId] = Field(default_factory=list)
    #: The posting's own wordings, so the row can be checked rather than
    #: trusted.
    texts: list[Annotated[str, StringConstraints(max_length=200)]] = Field(default_factory=list)


class WorthResult(Strict):
    """Every application worth running again, across the whole shelf."""

    version: Literal[1] = 1
    #: Applications read. The denominator for "3 of your 18".
    applications: int = 0
    #: Lines the user has written into this CV at all. When this is zero the
    #: screen has a different thing to say: there is nothing new to check
    #: against, and answering a gap question is what starts it.
    written: int = 0
    #: Must-haves first. Empty is the ordinary answer and the screen is
    #: written for it.
    items: list[WorthItem] = Field(default_factory=list)


class GapItem(Strict):
    """One requirement the CV does not prove, and the question that asks about it."""

    requirement_id: RequirementId
    question: Annotated[str, StringConstraints(max_length=200)]
    #: What in the CV is already adjacent, when anything is. Absent rather than
    #: stretched: an angle that failed the verifier is dropped, not softened.
    angle: Annotated[str, StringConstraints(max_length=200)] | None = None
    line_ids: list[LineId] = Field(default_factory=list)
    #: True when the model's own phrasing failed verification and the
    #: deterministic fallback was used instead. Surfaced rather than hidden so a
    #: prompt regression shows up as a count in the eval, instead of quietly
    #: flattening every question into the same template.
    templated: bool = False


class GapResult(Strict):
    version: Literal[1] = 1
    match_id: str
    items: list[GapItem] = Field(default_factory=list)


class AnswerSentence(Strict):
    """One sentence of an answer, and the CV lines underneath it."""

    text: Annotated[str, StringConstraints(max_length=400)]
    line_ids: list[LineId] = Field(default_factory=list)


class QuestionAnswer(Strict):
    """What the CV can say about one question an employer asked."""

    #: The question as the user pasted it, echoed back so the screen pairs the
    #: two without depending on order.
    question: Annotated[str, StringConstraints(max_length=300)]
    kind: AnswerKind
    #: Empty unless ``kind`` is ``answered`` — enforced in the pipeline, not
    #: merely expected of the model.
    sentences: list[AnswerSentence] = Field(default_factory=list)
    #: Sentences the verifier refused. Surfaced rather than hidden: an answer
    #: that lost half of itself is worth knowing about before it is pasted
    #: into a form, and a prompt regression shows up here as a count.
    dropped: int = 0


class AnswerResult(Strict):
    version: Literal[1] = 1
    #: The application the questions came with, when there was one. Absent for
    #: a question that arrived by email, which is most of them after the first
    #: round.
    match_id: str | None = None
    items: list[QuestionAnswer] = Field(default_factory=list)


#: Why the follow-up screen says what it says. ``nothing_new`` is the refusal
#: the feature exists for: an application that has gone quiet and a CV that
#: has not moved leaves nothing worth a stranger's minute, and the app writes
#: nothing rather than the warm paragraph every other tool sends.
FollowupKind = Literal["new_evidence", "nothing_new"]


class LetterResult(Strict):
    version: Literal[1] = 1
    match_id: str
    tone: Tone
    paragraphs: list[LetterParagraph]
    placeholders: list[str] = Field(default_factory=list)


class ProfileResult(Strict):
    """A headline and an About section, written from the CV and nothing else.

    The only generated surface in this app with no posting behind it: a
    profile has to be true of the person on any day, to any reader, so there
    is no requirement text to lend it vocabulary and no employer to please.
    What survives is what the CV can show.
    """

    version: Literal[1] = 1
    cv_hash: str
    #: One line, under 120 characters. Empty when nothing survived the
    #: verifier — which the screen says rather than hiding.
    headline: Annotated[str, StringConstraints(max_length=200)] = ""
    #: The lines the headline stands on.
    headline_line_ids: list[LineId] = Field(default_factory=list)
    #: Same shape and same contract as a letter's paragraphs.
    about: list[LetterParagraph] = Field(default_factory=list)


class FollowupResult(Strict):
    """A grounded follow-up note, or the reasoned refusal to write one."""

    version: Literal[1] = 1
    match_id: str
    kind: FollowupKind
    #: Days since it went out, and which clock that is (`SinceResult`). The
    #: model is never told either: the screen says it, from the record.
    days: int | None = None
    dated_from: Literal["sent", "checked"] = "checked"
    #: Same shape and same contract as a cover letter's paragraphs — text the
    #: verifier passed, with the CV lines it stands on.
    paragraphs: list[LetterParagraph] = Field(default_factory=list)
    #: What the reader must still fill in by hand.
    placeholders: list[str] = Field(default_factory=list)
    #: The lines the note is built on, all written after the application went
    #: out. Empty when ``kind`` is ``nothing_new``.
    line_ids: list[LineId] = Field(default_factory=list)
    #: What those lines name, spelled as the CV spells it.
    terms: list[Annotated[str, StringConstraints(max_length=80)]] = Field(default_factory=list)


class BriefClaim(Strict):
    """A sentence the user already sent, and the CV lines underneath it.

    Copied verbatim from what the app produced and the user accepted — a
    bullet or a letter paragraph. The brief never re-words it: the whole point
    is that this is the wording the interviewer is holding.
    """

    source: ClaimSource
    text: Annotated[str, StringConstraints(max_length=800)]
    line_ids: list[LineId] = Field(default_factory=list)


class BriefItem(Strict):
    """One requirement, the evidence behind it, and what was claimed about it.

    No requirement text and no line text: the caller already has the match and
    the CV, and copying either here would let the brief and the match map
    disagree about what a line says.
    """

    requirement_id: RequirementId
    kind: Kind
    risk: BriefRisk
    #: Cited lines that still exist in the CV being briefed against.
    line_ids: list[LineId] = Field(default_factory=list)
    claims: list[BriefClaim] = Field(default_factory=list)


class Assertion(Strict):
    """The user disagreeing with a verdict, recorded beside it.

    The match this app produced is never rewritten. A model that missed a
    requirement is wrong, and the person whose career it is gets to say so —
    but their correction stays *theirs*, labelled as such everywhere it
    travels, and it never becomes a verdict the app made.
    """

    requirement_id: RequirementId
    #: The CV lines the user says cover it. Their pick, in the order picked.
    line_ids: list[LineId] = Field(default_factory=list)


class InterviewBrief(Strict):
    """What to be ready for, built only from what was already verified."""

    version: Literal[1] = 1
    match_id: str
    #: The CV this brief was built from — not necessarily the one the match
    #: was made against.
    cv_hash: str
    #: True when the CV moved after this application was sent, which means the
    #: document the interviewer is holding is not the one on screen.
    cv_changed: bool = False
    #: Ranked: must-haves first, then by how hard the question will be.
    risks: list[BriefItem] = Field(default_factory=list)
    #: The requirements with evidence worth walking in with.
    proved: list[BriefItem] = Field(default_factory=list)
    #: Sentences that were sent but back no single requirement.
    loose_claims: list[BriefClaim] = Field(default_factory=list)


# ─── LLM output models ────────────────────────────────────────────────
#
# Flat, all-required, no defaults — strict `json_schema` mode rejects a
# property that is not in `required`, and a default would let the model omit
# the field and still validate, which hides a failure we want to see.


class LlmRequirement(Strict):
    id: RequirementId
    text: Annotated[str, StringConstraints(max_length=120)]
    kind: Kind
    category: Category
    source_quote: Annotated[str, StringConstraints(max_length=200)]


class ExtractionOutput(Strict):
    posting_title: str
    company: str
    requirements: list[LlmRequirement]


class LlmEvidence(Strict):
    requirement_id: RequirementId
    status: Status
    line_ids: list[str]
    why: Annotated[str, StringConstraints(max_length=160)]


class MatchingOutput(Strict):
    evidence: list[LlmEvidence]


class LlmBullet(Strict):
    source_line_ids: list[str]
    suggestion: str
    targets: list[str]


class TailorOutput(Strict):
    bullets: list[LlmBullet]


class LlmParagraph(Strict):
    text: str
    line_ids: list[str]


class ProfileOutput(Strict):
    headline: str
    headline_line_ids: list[str]
    about: list[LlmParagraph]


class LetterOutput(Strict):
    paragraphs: list[LlmParagraph]


class LlmGap(Strict):
    requirement_id: str
    question: str
    #: Empty string when nothing in the CV is adjacent. Required rather than
    #: optional because strict `json_schema` mode has no way to say "may be
    #: omitted", and an honest blank is a real answer here.
    angle: str
    line_ids: list[str]


class GapOutput(Strict):
    gaps: list[LlmGap]


class LlmAnswerVerdict(Strict):
    #: Which question, by position in the list it was given. An index rather
    #: than the question text: asked to echo it, a model tidies it, and then
    #: the screen shows the user a question nobody asked them.
    index: int
    kind: AnswerKind


class LlmAnswerSentence(Strict):
    index: int
    text: str
    line_ids: list[str]


class AnswerOutput(Strict):
    """Two flat lists rather than sentences nested inside answers.

    A sentence list inside an answer list inside the envelope is ten levels of
    JSON Schema and the host caps a structured request at eight
    (``llm/json_schema.py``). Flattening costs the model one extra ``index``
    per sentence and buys per-sentence citations, which is what lets the
    screen show the CV line under each claim rather than under the paragraph.
    """

    verdicts: list[LlmAnswerVerdict]
    sentences: list[LlmAnswerSentence]
