"""The grounding verifier — no output reaches the UI without passing it."""

from .grounding import Claim, SupportIndex, Verdict, extract_claims, verify
from .lexicon import CANONICAL, DEFAULT_LEXICON, TechLexicon

__all__ = [
    "CANONICAL",
    "DEFAULT_LEXICON",
    "Claim",
    "SupportIndex",
    "TechLexicon",
    "Verdict",
    "extract_claims",
    "verify",
]
