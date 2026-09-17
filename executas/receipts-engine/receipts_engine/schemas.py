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


class LetterResult(Strict):
    version: Literal[1] = 1
    match_id: str
    tone: Tone
    paragraphs: list[LetterParagraph]
    placeholders: list[str] = Field(default_factory=list)


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


class LetterOutput(Strict):
    paragraphs: list[LlmParagraph]
