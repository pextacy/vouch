#!/usr/bin/env python3
"""Measure match quality against the golden set.

    python scripts/eval_match.py fixtures/golden                # live host
    python scripts/eval_match.py fixtures/golden --replay runs/ # recorded
    python scripts/eval_match.py fixtures/golden --record runs/ # live + save

**Run this on every prompt change** and paste the table into the PR
(``CLAUDE.md`` rule 4). A prompt edit that lifts one number and quietly drops
another is the failure this exists to catch.

Thresholds:

===========================  ========
requirement extraction F1    ≥ 0.85
false "strong" rate          ≤ 5%
tailor leakage               0
letter leakage               0
===========================  ========

**How the model is reached.** The engine asks its host for completions over
reverse RPC, so this script *is* the host: it spawns the plugin, answers
``sampling/createMessage``, and forwards each request to the command given by
``--sampling-cmd`` (a program that reads one JSON request on stdin and writes
one JSON result on stdout). ``--replay`` answers from a recorded run instead,
which is what CI uses — deterministic, offline, and honest about what it
measures: the pipeline around the model, not the model.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "executas" / "receipts-engine"

F1_THRESHOLD = 0.85
FALSE_STRONG_THRESHOLD = 0.05
LEAKAGE_THRESHOLD = 0

#: An adversarial run (see ``scripts/fabricating_sampler.py``) gates on the
#: deterministic half only. Zero leakage is trivial for a verifier that drops
#: everything, so the run must also keep at least one honest suggestion.
MIN_KEPT_ADVERSARIAL = 1

#: ``RECEIPTS_EVAL_VERBOSE=1`` lets the plugin's stderr log through, which is
#: where the verifier says what it dropped and what it repaired.
VERBOSE = bool(os.environ.get("RECEIPTS_EVAL_VERBOSE"))


# ─── Plugin driver ────────────────────────────────────────────────────


class EngineHost:
    """Drives the plugin the way the Anna Agent does, answering reverse RPCs."""

    def __init__(self, sampling_cmd: list[str] | None, replay: list[str] | None) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "receipts_engine.plugin"],
            cwd=ENGINE_DIR,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None if VERBOSE else subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            # Twelve cases back to back through one process is precisely the
            # traffic `limits.py` refuses. A harness is not a user, and a run
            # that measured the rate limiter instead of the pipeline would
            # report a quality regression that is not there.
            env={**os.environ, "RECEIPTS_RATE_LIMIT": "off"},
        )
        self.sampling_cmd = sampling_cmd
        self.replay = list(replay) if replay is not None else None
        self.recorded: list[str] = []
        self.sampling_calls = 0
        self._replies: dict[int | str, dict[str, Any]] = {}
        self._lock = threading.Condition()
        self._next_id = 0
        threading.Thread(target=self._pump, daemon=True).start()
        self.call("initialize", {"protocolVersion": "2.0", "host_capabilities": {"llm.sample": True}})

    def _pump(self) -> None:
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                print(f"! non-JSON on stdout: {line[:120]}", file=sys.stderr)
                continue
            method = message.get("method")
            if method == "sampling/createMessage":
                threading.Thread(
                    target=self._answer_sampling, args=(message,), daemon=True
                ).start()
            elif method:
                continue  # progress notifications
            else:
                with self._lock:
                    self._replies[message["id"]] = message
                    self._lock.notify_all()

    def _answer_sampling(self, request: dict[str, Any]) -> None:
        self.sampling_calls += 1
        try:
            text = self._complete(request["params"])
            result = {"content": {"type": "text", "text": text}, "model": "eval"}
            self._send({"jsonrpc": "2.0", "id": request["id"], "result": result})
        except Exception as exc:  # noqa: BLE001 - report as a host-side failure
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "error": {"code": -32003, "message": f"{type(exc).__name__}: {exc}"},
                }
            )

    def _complete(self, params: dict[str, Any]) -> str:
        if self.replay is not None:
            if not self.replay:
                raise RuntimeError("recording exhausted — re-record it")
            return self.replay.pop(0)
        if not self.sampling_cmd:
            raise RuntimeError("no --sampling-cmd and no --replay: nothing can answer the model")
        completed = subprocess.run(
            self.sampling_cmd,
            input=json.dumps(params),
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
        )
        text = completed.stdout.strip()
        self.recorded.append(text)
        return text

    def _send(self, frame: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def call(self, method: str, params: dict[str, Any], *, timeout: float = 300.0) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        with self._lock:
            while request_id not in self._replies:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"{method} timed out")
                self._lock.wait(remaining)
            return self._replies.pop(request_id)

    def invoke(self, **args: Any) -> dict[str, Any]:
        reply = self.call(
            "invoke", {"tool": "engine", "arguments": args, "invoke_id": f"eval-{self._next_id}"}
        )
        if "error" in reply:
            raise RuntimeError(reply["error"]["message"])
        return reply["result"]

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()


# ─── Scoring ──────────────────────────────────────────────────────────


@dataclass
class CaseScore:
    case_id: str
    ok: bool
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    strong_claims: int = 0
    false_strong: int = 0
    leaks: int = 0
    bullets_kept: int = 0
    bullets_total: int = 0
    letter_leaks: int = 0
    letter_paragraphs: int = 0
    answer_leaks: int = 0
    answer_sentences: int = 0
    followup_leaks: int = 0
    followup_paragraphs: int = 0
    profile_leaks: int = 0
    profile_parts: int = 0
    answers_refused: int = 0
    seconds: float = 0.0
    error: str = ""
    notes: list[str] = field(default_factory=list)


def score_case(case: dict[str, Any], result: dict[str, Any]) -> CaseScore:
    expected = case["expected_requirements"]
    produced = result["requirements"]

    matched = _align(expected, produced)
    true_positives = sum(1 for value in matched.values() if value is not None)
    precision = true_positives / len(produced) if produced else 0.0
    recall = true_positives / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    status_of = {item["requirement_id"]: item["status"] for item in result["evidence"]}
    strong_claims = 0
    false_strong = 0
    notes: list[str] = []
    for spec in expected:
        produced_req = matched.get(spec["key"])
        if produced_req is None:
            continue
        actual = status_of.get(produced_req["id"], "missing")
        wanted = case["expected_status"][spec["key"]]
        if actual == "strong":
            strong_claims += 1
            # A "strong" on something the golden set calls absent or merely
            # related is the error that costs a user an interview.
            if wanted in {"missing", "partial"}:
                false_strong += 1
                notes.append(f"{spec['key']}: strong, expected {wanted}")
        elif actual != wanted:
            notes.append(f"{spec['key']}: {actual}, expected {wanted}")

    return CaseScore(
        case_id=case["id"],
        ok=True,
        precision=precision,
        recall=recall,
        f1=f1,
        strong_claims=strong_claims,
        false_strong=false_strong,
        notes=notes,
    )


def _align(expected: list[dict[str, Any]], produced: list[dict[str, Any]]) -> dict[str, Any]:
    """Greedy word-overlap alignment between expected and produced requirements.

    Exact string equality would measure phrasing, not extraction; overlap of
    content words measures whether the same requirement was found.
    """
    remaining = list(produced)
    out: dict[str, Any] = {}
    for spec in expected:
        wanted = _content_words(spec["text"])
        best: tuple[float, dict[str, Any] | None] = (0.0, None)
        for candidate in remaining:
            overlap = wanted & _content_words(candidate["text"])
            if not wanted:
                continue
            ratio = len(overlap) / len(wanted)
            if ratio > best[0]:
                best = (ratio, candidate)
        if best[0] >= 0.5 and best[1] is not None:
            out[spec["key"]] = best[1]
            remaining.remove(best[1])
        else:
            out[spec["key"]] = None
    return out


_STOPWORDS = {
    "a", "an", "and", "or", "the", "with", "of", "in", "on", "for", "to", "experience",
    "strong", "working", "knowledge", "deneyimi", "deneyim", "ile", "ve", "bilgisi",
}


def _content_words(text: str) -> set[str]:
    sys.path.insert(0, str(ENGINE_DIR))
    from receipts_engine.text import normalize

    return {word for word in normalize(text).split() if word not in _STOPWORDS and len(word) > 1}


def count_leaks(tailor: dict[str, Any]) -> int:
    """Suggestions that reached the caller carrying unsupported claims.

    Should always be zero by construction — the verifier drops them — so a
    non-zero count means the verifier was bypassed, not that the model got
    creative.
    """
    sys.path.insert(0, str(ENGINE_DIR))
    from receipts_engine.verify import verify

    leaks = 0
    for bullet in tailor["bullets"]:
        suggestion = bullet.get("suggestion")
        if not suggestion:
            continue
        if not verify(suggestion, [bullet["original"]]).ok:
            leaks += 1
    return leaks


def count_letter_leaks(letter: dict[str, Any], cv: dict[str, Any]) -> tuple[int, int]:
    """Paragraphs that reached the caller carrying unsupported claims.

    A paragraph is checked against the lines it cites; one that cites nothing
    (the closing) is checked against the whole CV, which is the same rule
    `pipeline/letter.py` applies before it returns.
    """
    sys.path.insert(0, str(ENGINE_DIR))
    from receipts_engine.verify import verify

    by_id = {line["id"]: line["text"] for line in cv["lines"]}
    all_lines = list(by_id.values())

    leaks = 0
    paragraphs = letter.get("paragraphs", [])
    for paragraph in paragraphs:
        text = paragraph.get("text", "").strip()
        if not text:
            continue
        cited = [by_id[line] for line in paragraph.get("line_ids", []) if line in by_id]
        if not verify(text, cited or all_lines).ok:
            leaks += 1
    return leaks, len(paragraphs)


def count_profile_leaks(profile: dict[str, Any], cv: dict[str, Any]) -> tuple[int, int]:
    """Profile text that reached the caller carrying unsupported claims.

    The strictest of the four generated surfaces, because it is the only one
    with no posting behind it: there is no requirement wording to lend a
    concept, so every term has to come from the CV. The headline counts as a
    part of its own — a fabricated headline is the line a recruiter reads
    first.
    """
    sys.path.insert(0, str(ENGINE_DIR))
    from receipts_engine.verify import verify

    by_id = {line["id"]: line["text"] for line in cv["lines"]}
    all_lines = list(by_id.values())

    leaks = 0
    parts = 0
    headline = profile.get("headline", "").strip()
    if headline:
        parts += 1
        cited = [by_id[line] for line in profile.get("headline_line_ids", []) if line in by_id]
        if not verify(headline, cited or all_lines).ok:
            leaks += 1
    for paragraph in profile.get("about", []):
        text = paragraph.get("text", "").strip()
        if not text:
            continue
        parts += 1
        cited = [by_id[line] for line in paragraph.get("line_ids", []) if line in by_id]
        if not verify(text, cited or all_lines).ok:
            leaks += 1
    return leaks, parts


def count_followup_leaks(followup: dict[str, Any], cv: dict[str, Any]) -> tuple[int, int]:
    """Follow-up paragraphs that reached the caller carrying unsupported claims.

    The fourth generated surface, and the one with the narrowest licence: a
    follow-up may only stand on the lines written *after* the application went
    out, so a paragraph that reaches back into the rest of the CV is already
    out of bounds. Counted the way the letter is counted — against the lines
    the paragraph itself cites.
    """
    sys.path.insert(0, str(ENGINE_DIR))
    from receipts_engine.verify import verify

    by_id = {line["id"]: line["text"] for line in cv["lines"]}
    all_lines = list(by_id.values())

    leaks = 0
    paragraphs = followup.get("paragraphs", [])
    for paragraph in paragraphs:
        text = paragraph.get("text", "").strip()
        if not text:
            continue
        cited = [by_id[line] for line in paragraph.get("line_ids", []) if line in by_id]
        if not verify(text, cited or all_lines).ok:
            leaks += 1
    return leaks, len(paragraphs)


def _cv_with_a_later_line(cv: dict[str, Any], match: dict[str, Any]) -> dict[str, Any] | None:
    """The CV plus one line the user wrote after this application went out.

    The follow-up declines unless something has changed, which is the point of
    the feature and useless for a leakage gate: nothing generated means
    nothing to check. So the harness produces the condition the screen is for
    — a sentence naming what the application could not show — and dated past
    any run of this script, because the engine compares it against the match's
    own timestamp.
    """
    sys.path.insert(0, str(ENGINE_DIR))
    from receipts_engine.recurring import keys_for

    unproved = {
        item["requirement_id"]
        for item in match.get("evidence", [])
        if item.get("status") != "strong"
    }
    # It has to be a requirement the lexicon knows: `since_applied` only lights
    # up on a canonical term, so a synthetic line about "5+ years of backend
    # engineering" would leave the note with nothing to say and the gate with
    # nothing to measure.
    wanted = next(
        (
            req
            for req in match.get("requirements", [])
            if req["id"] in unproved
            and any(not key.startswith("text:") for key, _ in keys_for(req["text"]))
        ),
        None,
    )
    if wanted is None:
        return None
    highest = max(
        (int(line["id"][1:]) for line in cv["lines"] if line["id"][1:].isdigit()), default=0
    )
    line = {
        "id": f"L{highest + 1}",
        "text": f"Owned the work behind {wanted['text']} end to end.",
        "section": "experience",
        "added_at": "2099-01-01T00:00:00Z",
    }
    return dict(cv, lines=[*cv["lines"], line])


def count_answer_leaks(answers: dict[str, Any], cv: dict[str, Any]) -> tuple[int, int, int]:
    """Form answers that reached the caller carrying unsupported claims.

    The third generated surface, and the one an adversarial sampler has the
    easiest time with: the question itself names the technology it wants, so a
    model that treats the question as a source produces a fluent, specific,
    entirely invented answer. Returns leaks, sentences, and how many questions
    the engine declined to answer — the last one because a gate that only
    counted leaks would pass a build that answered nothing at all.
    """
    sys.path.insert(0, str(ENGINE_DIR))
    from receipts_engine.verify import verify

    by_id = {line["id"]: line["text"] for line in cv["lines"]}

    leaks = 0
    sentences = 0
    refused = 0
    for item in answers.get("items", []):
        if item.get("kind") != "answered":
            refused += 1
            # A refusal that smuggled prose through is a leak whatever it is
            # labelled: the label is the promise (`pipeline/answer.py`).
            leaks += len(item.get("sentences", []))
            continue
        for sentence in item.get("sentences", []):
            text = sentence.get("text", "").strip()
            if not text:
                continue
            sentences += 1
            cited = [by_id[line] for line in sentence.get("line_ids", []) if line in by_id]
            # No `or all_lines` fallback, unlike the letter: an answer sentence
            # is required to cite, and one that did not should never have been
            # kept in the first place.
            if not cited or not verify(text, cited).ok:
                leaks += 1
    return leaks, sentences, refused


# ─── Runner ───────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    cases = sorted(Path(args.golden).glob("*.json"))
    if not cases:
        print(f"no cases in {args.golden}", file=sys.stderr)
        return 2

    record_dir = Path(args.record) if args.record else None
    replay_dir = Path(args.replay) if args.replay else None
    if record_dir:
        record_dir.mkdir(parents=True, exist_ok=True)

    scores: list[CaseScore] = []
    for path in cases:
        case = json.loads(path.read_text(encoding="utf-8"))
        replay = None
        if replay_dir:
            recording = replay_dir / f"{case['id']}.json"
            if not recording.is_file():
                scores.append(CaseScore(case["id"], ok=False, error="no recording"))
                continue
            replay = json.loads(recording.read_text(encoding="utf-8"))

        host = EngineHost(args.sampling_cmd, replay)
        started = time.monotonic()
        try:
            cv = host.invoke(action="parse_cv", source="text", text=case["cv"])
            _require(cv, "parse_cv")
            match = host.invoke(
                action="run_match",
                cv=cv["data"],
                posting_text=case["posting"],
                locale=case["language"],
            )
            _require(match, "run_match")
            score = score_case(case, match["data"])

            tailor = host.invoke(
                action="tailor", cv=cv["data"], match=match["data"], locale=case["language"]
            )
            if tailor.get("success"):
                score.leaks = count_leaks(tailor["data"])
                bullets = tailor["data"]["bullets"]
                score.bullets_total = len(bullets)
                score.bullets_kept = sum(1 for item in bullets if item.get("suggestion"))

            # The letter is the riskier surface — longer, more fluent, and the
            # fluent part is where a model reaches for a number nobody gave it.
            # Measuring only the bullets left that half of the promise ungated.
            letter = host.invoke(
                action="letter",
                cv=cv["data"],
                match=match["data"],
                locale=case["language"],
                tone="plain",
                length="short",
            )
            if letter.get("success"):
                score.letter_leaks, score.letter_paragraphs = count_letter_leaks(
                    letter["data"], cv["data"]
                )

            # The form's questions are the surface where the prompt injection
            # and the fabrication arrive in the same sentence: the question
            # names the tool it wants, so a model that reads it as a source
            # writes a specific, fluent, invented answer. Cases carry their own
            # questions when they have them; otherwise the requirement texts
            # are turned into questions, which is what a screening form does.
            answers = host.invoke(
                action="answer_question",
                cv=cv["data"],
                match=match["data"],
                questions=_questions_for(case, match["data"]),
                locale=case["language"],
            )
            if answers.get("success"):
                (
                    score.answer_leaks,
                    score.answer_sentences,
                    score.answers_refused,
                ) = count_answer_leaks(answers["data"], cv["data"])
            # The follow-up is the one surface that has to be *given* a
            # reason to exist before it can leak anything.
            grown = _cv_with_a_later_line(cv["data"], match["data"])
            if grown is not None:
                followup = host.invoke(
                    action="followup",
                    cv=grown,
                    match=match["data"],
                    locale=case["language"],
                )
                if followup.get("success"):
                    score.followup_leaks, score.followup_paragraphs = count_followup_leaks(
                        followup["data"], grown
                    )

            # The profile has no posting behind it at all, which is why it
            # is worth gating separately: nothing lends it a concept.
            profile = host.invoke(action="profile", cv=cv["data"], locale=case["language"])
            if profile.get("success"):
                score.profile_leaks, score.profile_parts = count_profile_leaks(
                    profile["data"], cv["data"]
                )

            score.seconds = time.monotonic() - started
            scores.append(score)

            if record_dir:
                (record_dir / f"{case['id']}.json").write_text(
                    json.dumps(host.recorded, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except Exception as exc:  # noqa: BLE001 - one bad case must not end the run
            scores.append(
                CaseScore(case["id"], ok=False, error=f"{type(exc).__name__}: {exc}")
            )
        finally:
            host.close()

    return report(scores, as_json=args.json, adversarial=args.adversarial)


def _questions_for(case: dict[str, Any], match: dict[str, Any]) -> list[str]:
    """The case's own questions, or ones built from what the posting asked.

    Built rather than written into every golden file: the point of the gate is
    that a question naming a technology must not license a claim about it, and
    a requirement the CV cannot prove is exactly that question.
    """
    written = case.get("questions")
    if isinstance(written, list) and written:
        return [str(text) for text in written][:5]
    unproven = {
        item["requirement_id"]
        for item in match.get("evidence", [])
        if item.get("status") != "strong"
    }
    asked = [
        f"Describe your experience with {req['text']}."
        for req in match.get("requirements", [])
        if req["id"] in unproven
    ]
    return asked[:3] or ["Describe your most relevant experience for this role."]


def _require(result: dict[str, Any], action: str) -> None:
    if not result.get("success"):
        raise RuntimeError(f"{action}: {result.get('data', {}).get('code', 'failed')}")


def report(scores: list[CaseScore], *, as_json: bool, adversarial: bool = False) -> int:
    done = [score for score in scores if score.ok]
    f1 = sum(score.f1 for score in done) / len(done) if done else 0.0
    strong_total = sum(score.strong_claims for score in done)
    false_strong_total = sum(score.false_strong for score in done)
    false_strong_rate = false_strong_total / strong_total if strong_total else 0.0
    leaks = sum(score.leaks for score in done)
    letter_leaks = sum(score.letter_leaks for score in done)
    kept = sum(score.bullets_kept for score in done)
    bullets_total = sum(score.bullets_total for score in done)

    answer_leaks = sum(score.answer_leaks for score in scores)
    answer_sentences = sum(score.answer_sentences for score in scores)
    followup_leaks = sum(score.followup_leaks for score in scores)
    followup_paragraphs = sum(score.followup_paragraphs for score in scores)
    profile_leaks = sum(score.profile_leaks for score in scores)
    profile_parts = sum(score.profile_parts for score in scores)
    grounding_ok = (
        leaks <= LEAKAGE_THRESHOLD
        and letter_leaks <= LEAKAGE_THRESHOLD
        and answer_leaks <= LEAKAGE_THRESHOLD
        and followup_leaks <= LEAKAGE_THRESHOLD
        and profile_leaks <= LEAKAGE_THRESHOLD
    )
    if adversarial:
        # F1 and the false-"strong" rate measure whatever answered the sampling
        # calls. Against a scripted adversary that is the script, so gating on
        # them would report a keyword heuristic as a model regression.
        passed = len(done) == len(scores) and grounding_ok and kept >= MIN_KEPT_ADVERSARIAL
    else:
        passed = (
            len(done) == len(scores)
            and f1 >= F1_THRESHOLD
            and false_strong_rate <= FALSE_STRONG_THRESHOLD
            and grounding_ok
        )

    if as_json:
        print(
            json.dumps(
                {
                    "cases": len(scores),
                    "completed": len(done),
                    "f1": round(f1, 3),
                    "false_strong_rate": round(false_strong_rate, 4),
                    "tailor_leaks": leaks,
                    "letter_leaks": letter_leaks,
                    "bullets_kept": kept,
                    "bullets_total": bullets_total,
                    "adversarial": adversarial,
                    "passed": passed,
                    "per_case": [score.__dict__ for score in scores],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if passed else 1

    print(f"{'case':22} {'F1':>6} {'P':>6} {'R':>6} {'strong':>7} {'false':>6} {'leak':>5}  {'s':>5}")
    print("-" * 74)
    for score in scores:
        if not score.ok:
            print(f"{score.case_id:22} {'— ' + score.error}")
            continue
        print(
            f"{score.case_id:22} {score.f1:6.2f} {score.precision:6.2f} {score.recall:6.2f} "
            f"{score.strong_claims:7d} {score.false_strong:6d} {score.leaks:5d} {score.seconds:5.1f}"
        )
        for note in score.notes:
            print(f"{'':22}   · {note}")
    print("-" * 74)
    informational = "   (informational — measures the sampler)" if adversarial else ""
    print(f"requirement F1        {f1:.3f}   (threshold ≥ {F1_THRESHOLD}){informational}")
    print(
        f"false 'strong' rate   {false_strong_rate:.3f}   "
        f"(threshold ≤ {FALSE_STRONG_THRESHOLD}) [{false_strong_total}/{strong_total}]{informational}"
    )
    print(f"tailor leakage        {leaks}       (threshold ≤ {LEAKAGE_THRESHOLD})")
    letter_paragraphs = sum(score.letter_paragraphs for score in done)
    print(
        f"letter leakage        {letter_leaks}       "
        f"(threshold ≤ {LEAKAGE_THRESHOLD}) [{letter_leaks}/{letter_paragraphs} paragraphs]"
    )
    print(
        f"answer leakage        {answer_leaks}       "
        f"(threshold ≤ {LEAKAGE_THRESHOLD}) [{answer_leaks}/{answer_sentences} sentences]"
    )
    print(
        f"followup leakage      {followup_leaks}       "
        f"(threshold ≤ {LEAKAGE_THRESHOLD}) [{followup_leaks}/{followup_paragraphs} paragraphs]"
    )
    print(
        f"profile leakage       {profile_leaks}       "
        f"(threshold ≤ {LEAKAGE_THRESHOLD}) [{profile_leaks}/{profile_parts} parts]"
    )
    # Zero leakage is also what a verifier that rejects everything reports.
    floor = f"(threshold ≥ {MIN_KEPT_ADVERSARIAL})" if adversarial else "(not gated)"
    print(f"suggestions kept      {kept}       {floor} [{kept}/{bullets_total} bullets]")
    print(f"\n{'PASS' if passed else 'FAIL'}: {len(done)}/{len(scores)} cases completed")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("golden", nargs="?", default=str(REPO_ROOT / "fixtures" / "golden"))
    parser.add_argument(
        "--sampling-cmd",
        nargs="+",
        help="program that reads a sampling request on stdin and writes the completion on stdout",
    )
    parser.add_argument("--record", help="directory to write the model responses into")
    parser.add_argument("--replay", help="directory of recorded responses to answer from")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--adversarial",
        action="store_true",
        help=(
            "the sampler fabricates on purpose (scripts/fabricating_sampler.py): "
            "gate on leakage and on keeping the honest suggestions, and report "
            "F1 and the false-'strong' rate as informational"
        ),
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
