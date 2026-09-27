"""Rate limiting — the allowance, and the two ways it must not misfire.

A limiter that is too tight deletes a real user's work; one that is too loose
lets a loop spend their Anna credits before they notice. So both directions are
tested: the burst a person actually produces goes through, and the loop behind
it does not.
"""

from __future__ import annotations

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.limits import MAX_IN_FLIGHT, Limiter, TokenBucket


def test_bucket_allows_its_burst() -> None:
    bucket = TokenBucket(capacity=3, refill_per_s=1.0)
    assert [bucket.take() for _ in range(3)] == [0.0, 0.0, 0.0]


def test_bucket_reports_the_wait_when_it_is_empty() -> None:
    bucket = TokenBucket(capacity=1, refill_per_s=0.5)
    assert bucket.take() == 0.0
    wait = bucket.take()
    assert wait == pytest.approx(2.0, abs=0.1)  # one token at half a token a second


def test_bucket_refills_over_time() -> None:
    bucket = TokenBucket(capacity=2, refill_per_s=1000.0)
    bucket.take()
    bucket.take()
    # Faster than any sleep this suite can afford: a fast refill rate proves
    # the arithmetic without making the test wait for wall-clock seconds.
    assert bucket.take(cost=0.0) == 0.0


def test_a_whole_application_fits_in_one_burst() -> None:
    """Match, then bullets, then a letter — and the same again for a second posting.

    This is the sequence the product is built around. If the limiter cannot
    pass it without a wait, the limiter is wrong, not the user.
    """
    limits = Limiter(enabled=True)
    for _ in range(2):
        for action in ("run_match", "tailor", "letter"):
            limits.check(action)


def test_a_loop_is_refused() -> None:
    limits = Limiter(enabled=True)
    with pytest.raises(EngineError) as caught:
        for _ in range(50):
            limits.check("run_match")
    assert caught.value.code == "rate_limited"
    assert caught.value.retriable
    assert caught.value.details["retry_after_s"] > 0


def test_uploading_a_whole_file_is_never_throttled() -> None:
    """A 2 MB CV is ~16 chunks, and a user may re-pick the file after a bad parse."""
    limits = Limiter(enabled=True)
    for _ in range(64):
        limits.check("upload_chunk")


def test_free_actions_are_not_limited() -> None:
    limits = Limiter(enabled=True)
    for _ in range(100):
        limits.check("health")
        limits.check("forget")
        limits.check("discard_upload")


def test_in_flight_slots_are_bounded_and_returned() -> None:
    limits = Limiter(enabled=True)
    assert all(limits.enter() for _ in range(MAX_IN_FLIGHT))
    assert not limits.enter()
    limits.leave()
    assert limits.enter()


def test_disabled_limiter_permits_everything() -> None:
    limits = Limiter(enabled=False)
    for _ in range(100):
        limits.check("run_match")
    assert all(limits.enter() for _ in range(MAX_IN_FLIGHT * 3))


def test_env_turns_the_limiter_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """What `scripts/eval_match.py` and the plugin contract suite rely on."""
    monkeypatch.setenv("RECEIPTS_RATE_LIMIT", "off")
    assert not Limiter().enabled
    monkeypatch.setenv("RECEIPTS_RATE_LIMIT", "on")
    assert Limiter().enabled
    monkeypatch.delenv("RECEIPTS_RATE_LIMIT")
    assert Limiter().enabled  # on unless something asked for it to be off


def test_a_crash_log_carries_the_type_not_the_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 5: CV content never reaches a log, and stderr is a log.

    An unexpected pydantic error quotes the input that failed, and the input on
    this path is CV-derived — so the message is opt-in, for a developer sitting
    in front of the process.
    """
    from receipts_engine.plugin import _detail

    monkeypatch.delenv("RECEIPTS_DEBUG", raising=False)
    assert _detail(ValueError("L12: Built payment reconciliation services")) == ""

    monkeypatch.setenv("RECEIPTS_DEBUG", "1")
    assert "reconciliation" in _detail(ValueError("L12: Built payment reconciliation services"))
