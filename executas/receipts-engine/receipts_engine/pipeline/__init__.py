"""The pipelines: match, tailor, letter, gaps, answers, follow-up — and the prompts they use."""

from .answer import answer_questions
from .followup import write_followup
from .gaps import plan_gaps
from .letter import resolve_placeholders, write_letter
from .profile import write_profile
from .run import clear_requirement_cache, run_match
from .summarize import sentence_for, summarize
from .tailor import tailor_bullets

__all__ = [
    "answer_questions",
    "clear_requirement_cache",
    "plan_gaps",
    "resolve_placeholders",
    "run_match",
    "sentence_for",
    "summarize",
    "tailor_bullets",
    "write_followup",
    "write_letter",
    "write_profile",
]
