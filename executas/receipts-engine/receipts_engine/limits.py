"""Rate limits for the actions that spend something.

The host already enforces quotas — ``job_quota_exceeded`` on the job API,
``-32002`` on sampling — so this is not the meter. It is the thing that keeps a
runaway client from reaching the meter: a retry loop with no backoff, a held
key, a script pointed at the primary function. All three spend the *user's*
Anna credits, and the first the user would hear about it is a quota error.

Three buckets, sized by what the action costs:

=========  ====================  ===========================================
model      6 burst, 1 per 20 s   ``run_match`` / ``tailor`` / ``letter`` /
                                 ``gaps`` — the actions that call the model
parse      8 burst, 1 per 5 s    ``parse_cv`` — no model, but PDF extraction
                                 is the most CPU the plugin ever does
upload     80 burst, 4 per s     ``upload_chunk`` — a 2 MB file is ~16 of
                                 them and a re-upload must not be throttled
=========  ====================  ===========================================

The model bucket is the one with a judgement call in it. A person tailoring an
application runs one match, then asks for bullets, then a letter: three calls
in a minute or two, and the next posting is minutes away. Six in a burst covers
that with room to spare, and one every twenty seconds sustained is far above
human pace — but a script that wants a hundred runs finds itself waiting.

``RECEIPTS_RATE_LIMIT=off`` turns the whole thing off, which is what the eval
harness does: ``scripts/eval_match.py`` drives twelve cases through one process
back to back, and that is the shape this exists to stop.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Final

from .errors import EngineError

MODEL_CAPACITY: Final[float] = 6.0
MODEL_REFILL_PER_S: Final[float] = 1.0 / 20.0

PARSE_CAPACITY: Final[float] = 8.0
PARSE_REFILL_PER_S: Final[float] = 1.0 / 5.0

UPLOAD_CAPACITY: Final[float] = 80.0
UPLOAD_REFILL_PER_S: Final[float] = 4.0

#: Invokes the process will hold at once. The pool runs four; the rest queue,
#: and an unbounded queue is just a slower way to run out of memory. Sixteen is
#: four deep per worker — more than a UI can produce, less than a loop can.
MAX_IN_FLIGHT: Final[int] = 16

_ENV_FLAG: Final[str] = "RECEIPTS_RATE_LIMIT"


class TokenBucket:
    """Classic token bucket. Thread-safe; invokes arrive on a pool."""

    def __init__(self, capacity: float, refill_per_s: float) -> None:
        self.capacity = capacity
        self.refill_per_s = refill_per_s
        self._tokens = capacity
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def take(self, cost: float = 1.0) -> float:
        """Spend ``cost`` tokens. Returns 0.0 on success, else seconds to wait."""
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self.capacity, self._tokens + (now - self._updated) * self.refill_per_s
            )
            self._updated = now
            if self._tokens >= cost:
                self._tokens -= cost
                return 0.0
            missing = cost - self._tokens
            return missing / self.refill_per_s if self.refill_per_s > 0 else float("inf")


class Limiter:
    """Every limit the plugin enforces, in one place so it can be turned off."""

    #: Which bucket an action draws on. An action absent from here is free:
    #: ``health``, ``forget`` and ``discard_upload`` cost nothing to serve and
    #: throttling them would make the failure paths worse, not better.
    BUCKETS: Final[dict[str, str]] = {
        "run_match": "model",
        "tailor": "model",
        "letter": "model",
        "followup": "model",
        "profile": "model",
        "gaps": "model",
        "answer_question": "model",
        "parse_cv": "parse",
        "audit_cv": "parse",
        # Free of model cost, but it reads up to 20k characters of pasted text
        # and it is the one action a user can fire by holding a paste shortcut.
        "check_document": "parse",
        "recurring_gaps": "parse",
        "compare_postings": "parse",
        "interview_brief": "parse",
        "line_ledger": "parse",
        "since_applied": "parse",
        "compare_runs": "parse",
        "worth_rerunning": "parse",
        "upload_chunk": "upload",
        "export_docx": "parse",
        "export_cv": "parse",
    }

    def __init__(self, *, enabled: bool | None = None) -> None:
        self.enabled = _enabled_by_default() if enabled is None else enabled
        self._buckets = {
            "model": TokenBucket(MODEL_CAPACITY, MODEL_REFILL_PER_S),
            "parse": TokenBucket(PARSE_CAPACITY, PARSE_REFILL_PER_S),
            "upload": TokenBucket(UPLOAD_CAPACITY, UPLOAD_REFILL_PER_S),
        }
        self._in_flight = 0
        self._lock = threading.Lock()

    # — per-action —

    def check(self, action: str) -> None:
        """Raise ``rate_limited`` when ``action`` has run out of allowance."""
        if not self.enabled:
            return
        name = self.BUCKETS.get(action)
        if name is None:
            return
        wait = self._buckets[name].take()
        if wait > 0:
            raise EngineError(
                "rate_limited",
                f"{action} is rate limited",
                details={"retry_after_s": round(wait, 1), "bucket": name},
            )

    # — process-wide —

    def enter(self) -> bool:
        """Claim one in-flight slot. False when the process is saturated."""
        if not self.enabled:
            return True
        with self._lock:
            if self._in_flight >= MAX_IN_FLIGHT:
                return False
            self._in_flight += 1
            return True

    def leave(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight


def _enabled_by_default() -> bool:
    return os.environ.get(_ENV_FLAG, "").strip().lower() not in {"off", "0", "false", "no"}
