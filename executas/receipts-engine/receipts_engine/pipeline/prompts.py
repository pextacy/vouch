"""Load and fill the versioned prompt files.

Prompts live in ``prompts/*.v1.md`` rather than in Python strings so a change to
one is a reviewable diff on its own, and so the version in the filename is the
thing `scripts/eval_match.py` reports against.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Final

_PROMPT_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "prompts"

LANGUAGE_NAMES: Final[dict[str, str]] = {"en": "English", "tr": "Turkish"}


@functools.lru_cache(maxsize=16)
def load(name: str) -> str:
    """Read one prompt file. Cached — the files never change at runtime."""
    path = _PROMPT_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"missing prompt file: {path}")
    return path.read_text(encoding="utf-8").strip()


def render(name: str, **values: str) -> str:
    """Fill the ``{placeholders}`` in a prompt file."""
    text = load(name)
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def language_name(locale: str) -> str:
    return LANGUAGE_NAMES.get(locale, "English")
