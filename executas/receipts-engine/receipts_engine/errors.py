"""Error objects shared by every action.

Every failure the user can see is an ``EngineError`` carrying one of the codes
from ``docs.md §3``. The UI looks the code up in its i18n table, so the
``message`` here is a developer-facing fallback, never the string shown to a
user. ``retriable`` tells the UI whether to offer "Try again".
"""

from __future__ import annotations

from typing import Any, Final, Literal

ErrorCode = Literal[
    "file_too_large",
    "unreadable_file",
    "cv_too_short",
    "no_requirements_found",
    "model_output_invalid",
    "sampling_unavailable",
    "cancelled",
    "upload_expired",
    "invalid_args",
    "internal_error",
]

#: Codes whose failure is transient — the UI may offer "Try again".
RETRIABLE: Final[frozenset[str]] = frozenset(
    {"model_output_invalid", "sampling_unavailable", "upload_expired", "internal_error"}
)

_FALLBACK_MESSAGES: Final[dict[str, str]] = {
    "file_too_large": "File is larger than the 2 MB limit.",
    "unreadable_file": "No text could be extracted from this file.",
    "cv_too_short": "The CV has too little text to match against.",
    "no_requirements_found": "No hiring requirements could be read from this text.",
    "model_output_invalid": "The model did not return output matching the schema.",
    "sampling_unavailable": "The host could not run the model.",
    "cancelled": "Cancelled.",
    "upload_expired": "The upload buffer expired before it was used.",
    "invalid_args": "Arguments did not match the action contract.",
    "internal_error": "Unexpected engine failure.",
}


class EngineError(Exception):
    """A user-visible failure with a stable code.

    Raised anywhere in the pipeline and converted to ``{code, message,
    retriable}`` at the plugin boundary. Detail values are for the developer
    log only — they never carry CV content.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code: ErrorCode = code
        self.message = message or _FALLBACK_MESSAGES.get(code, code)
        self.details = details or {}
        super().__init__(f"{code}: {self.message}")

    @property
    def retriable(self) -> bool:
        return self.code in RETRIABLE

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retriable": self.retriable,
        }
        if self.details:
            out["details"] = self.details
        return out
