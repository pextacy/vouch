"""Turn an uploaded CV or a pasted posting into text the pipeline can use."""

from .cv import parse_cv
from .posting import normalize_posting

__all__ = ["normalize_posting", "parse_cv"]
