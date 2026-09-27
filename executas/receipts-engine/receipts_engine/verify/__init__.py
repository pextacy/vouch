"""The grounding verifier — no output reaches the UI without passing it."""

from .grounding import (
    Claim,
    SupportIndex,
    Verdict,
    Verifier,
    extract_claims,
    title_surfaces,
    titles_in,
    verify,
    year_ranges_in,
)
from .lexicon import CANONICAL, DEFAULT_LEXICON, TechLexicon

__all__ = [
    "CANONICAL",
    "DEFAULT_LEXICON",
    "Claim",
    "SupportIndex",
    "TechLexicon",
    "Verdict",
    "Verifier",
    "extract_claims",
    "title_surfaces",
    "titles_in",
    "verify",
    "year_ranges_in",
]
