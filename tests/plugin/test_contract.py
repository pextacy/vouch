"""Plugin contract: the wire shapes the Agent actually depends on.

The plugin is driven the way the host drives it — a real subprocess speaking
JSON-RPC over stdio — because every rule that breaks an Executa
(``describe`` wrapped, ``success`` omitted, an unknown method not answering
``-32601``, a stray write to stdout) is invisible to a unit test of the same
functions.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from ..conftest import SAMPLE_CV_LINES, build_docx, build_pdf

ENGINE_DIR = Path(__file__).resolve().parents[2] / "executas" / "receipts-engine"


class Plugin:
    """Minimal stand-in for the Agent's stdio client.

    One reader thread owns stdout and routes frames by id. Sharing the stream
    between per-call readers looked simpler and silently interleaved partial
    lines — which is also exactly how a real client corrupts the protocol.
    """

    def __init__(
        self,
        *,
        protocol: str = "2.0",
        sampler: Any = None,
        rate_limit: bool = False,
    ) -> None:
        # The suite drives dozens of invokes back to back, which is the shape
        # the limiter exists to refuse — so it is off unless a test is about
        # the limiter itself. `scripts/eval_match.py` turns it off for the same
        # reason, and both are harnesses rather than users.
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "receipts_engine.plugin"],
            cwd=ENGINE_DIR,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "RECEIPTS_RATE_LIMIT": "on" if rate_limit else "off"},
        )
        self._next_id = 0
        self._id_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._replies: queue.Queue[dict[str, Any]] = queue.Queue()
        #: Answers `sampling/createMessage`; `None` leaves reverse RPCs unanswered.
        self.sampler = sampler
        self.notifications: list[dict[str, Any]] = []
        self.stderr_lines: list[str] = []
        self.bad_lines: list[str] = []

        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

        self.initialize_result = self.call(
            "initialize",
            {"protocolVersion": protocol, "host_capabilities": {"llm.sample": True}},
        )["result"]

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # stdout is protocol-only: anything unparsable is a defect.
                self.bad_lines.append(line[:200])
                continue
            if "method" not in message:
                self._replies.put(message)
            elif message.get("id") is not None and self.sampler is not None:
                # A reverse RPC. The real host answers it on its own thread
                # while the invoke that raised it is still parked.
                threading.Thread(target=self._answer, args=(message,), daemon=True).start()
            else:
                self.notifications.append(message)

    def _answer(self, request: dict[str, Any]) -> None:
        text = self.sampler(request.get("params") or {})
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {"content": {"type": "text", "text": text}},
            }
        )

    def _send(self, frame: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        with self._write_lock:
            self.process.stdin.write(json.dumps(frame) + "\n")
            self.process.stdin.flush()

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.stderr_lines.append(line.rstrip())

    def call(
        self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 30.0
    ) -> dict[str, Any]:
        with self._id_lock:
            self._next_id += 1
            request_id = self._next_id
        frame: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            frame["params"] = params
        self._send(frame)

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"no response to {method!r} in {timeout}s")
            try:
                message = self._replies.get(timeout=remaining)
            except queue.Empty:
                continue
            if message.get("id") == request_id:
                return message
            # Another thread's reply: hand it back for its own `call` to find.
            self._replies.put(message)
            time.sleep(0.01)

    def invoke(
        self, *, timeout: float = 30.0, invoke_id: str = "test-invoke", **args: Any
    ) -> dict[str, Any]:
        return self.call(
            "invoke",
            {"tool": "engine", "arguments": args, "invoke_id": invoke_id},
            timeout=timeout,
        )

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            self.process.kill()


@pytest.fixture(scope="module")
def plugin() -> Any:
    client = Plugin()
    yield client
    client.close()


# ─── Handshake and manifest ───────────────────────────────────────────


def test_initialize_negotiates_v2_and_advertises_sampling(plugin: Plugin) -> None:
    assert plugin.initialize_result["protocolVersion"] == "2.0"
    assert plugin.initialize_result["client_capabilities"] == {"sampling": {}}


def test_a_v1_host_downgrades_without_advertising_sampling() -> None:
    client = Plugin(protocol="1.1")
    try:
        assert client.initialize_result["client_capabilities"] == {}
    finally:
        client.close()


def test_stdout_carries_json_rpc_only(plugin: Plugin) -> None:
    plugin.invoke(action="health")
    assert plugin.bad_lines == []


def test_describe_returns_the_bare_manifest(plugin: Plugin) -> None:
    reply = plugin.call("describe")
    manifest = reply["result"]
    # ToolManifest.from_dict reads these keys directly; a wrapper drops the plugin.
    assert manifest["name"]
    assert manifest["display_name"] == "Receipts Engine"
    assert manifest["tools"][0]["name"] == "engine"


def test_manifest_declares_the_sampling_capability(plugin: Plugin) -> None:
    manifest = plugin.call("describe")["result"]
    assert "llm.sample" in manifest["host_capabilities"]


def test_manifest_uses_the_parameters_shape_not_input_schema(plugin: Plugin) -> None:
    tool = plugin.call("describe")["result"]["tools"][0]
    assert "input_schema" not in tool
    assert isinstance(tool["parameters"], list)
    assert all({"name", "type", "description"} <= set(param) for param in tool["parameters"])


def test_every_action_is_listed_in_the_action_enum(plugin: Plugin) -> None:
    tool = plugin.call("describe")["result"]["tools"][0]
    action = next(param for param in tool["parameters"] if param["name"] == "action")
    assert set(action["enum"]) == {
        "health",
        "forget",
        "discard_upload",
        "upload_chunk",
        "parse_cv",
        "audit_cv",
        "check_document",
        "answer_question",
        "line_ledger",
        "recurring_gaps",
        "compare_postings",
        "interview_brief",
        "line_ledger",
        "since_applied",
        "compare_runs",
        "worth_rerunning",
        "run_match",
        "gaps",
        "tailor",
        "letter",
        "followup",
        "profile",
        "gaps",
        "export_docx",
        "export_cv",
    }


def test_the_description_names_every_action_exactly_once(plugin: Plugin) -> None:
    """The Agent reads this text to decide what to call.

    `gaps` was listed twice for a while — once where it belongs in the flow and
    once after `letter` — which is the kind of thing nothing catches, because
    the manifest still validates and every action still works.
    """
    tool = plugin.call("describe")["result"]["tools"][0]
    action = next(param for param in tool["parameters"] if param["name"] == "action")
    for name in action["enum"]:
        assert tool["description"].count(f"`{name}` (") == 1, name


def test_health_reports_ready(plugin: Plugin) -> None:
    assert plugin.call("health")["result"]["status"] == "healthy"


def test_unknown_method_returns_method_not_found(plugin: Plugin) -> None:
    reply = plugin.call("nonsense")
    assert reply["error"]["code"] == -32601


def test_unknown_tool_returns_method_not_found(plugin: Plugin) -> None:
    reply = plugin.call("invoke", {"tool": "not-the-engine", "arguments": {"action": "health"}})
    assert reply["error"]["code"] == -32601


def test_the_process_survives_every_call(plugin: Plugin) -> None:
    for _ in range(3):
        plugin.invoke(action="health")
    assert plugin.process.poll() is None


def test_logs_go_to_stderr_only(plugin: Plugin) -> None:
    plugin.invoke(action="health")
    assert any("Receipts Engine" in line for line in plugin.stderr_lines)


# ─── Actions ──────────────────────────────────────────────────────────


def test_health_action_wraps_its_payload(plugin: Plugin) -> None:
    result = plugin.invoke(action="health")["result"]
    assert result["success"] is True
    assert result["tool"] == "engine"
    assert result["data"]["healthy"] is True


def test_missing_action_is_an_invalid_params_error(plugin: Plugin) -> None:
    reply = plugin.call("invoke", {"tool": "engine", "arguments": {}})
    assert reply["error"]["code"] == -32602


def test_unknown_action_is_an_invalid_params_error(plugin: Plugin) -> None:
    reply = plugin.invoke(action="teleport")
    assert reply["error"]["code"] == -32602


def test_parse_cv_from_text(plugin: Plugin, sample_cv_text: str) -> None:
    result = plugin.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]
    assert result["success"] is True
    assert result["data"]["lines"][0]["id"] == "L1"


def test_a_short_cv_fails_without_reporting_success(plugin: Plugin) -> None:
    result = plugin.invoke(action="parse_cv", source="text", text="too short")["result"]
    assert result["success"] is False
    assert result["data"]["code"] == "cv_too_short"
    assert result["data"]["retriable"] is False


def test_error_payloads_carry_code_message_and_retriable(plugin: Plugin) -> None:
    data = plugin.invoke(action="parse_cv", source="text", text="x")["result"]["data"]
    assert set(data) >= {"code", "message", "retriable"}


def test_chunked_pdf_upload_round_trips(plugin: Plugin) -> None:
    payload = base64.b64encode(build_pdf(SAMPLE_CV_LINES)).decode("ascii")
    chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)]
    for index, chunk in enumerate(chunks):
        reply = plugin.invoke(
            action="upload_chunk",
            upload_id="up-1",
            index=index,
            total=len(chunks),
            data_b64=chunk,
            filename="cv.pdf",
        )["result"]
        assert reply["success"] is True
    assert reply["data"]["complete"] is True

    parsed = plugin.invoke(action="parse_cv", source="pdf", upload_id="up-1")["result"]
    assert parsed["success"] is True
    assert any("reconciliation" in line["text"] for line in parsed["data"]["lines"])


def test_chunked_docx_upload_round_trips(plugin: Plugin) -> None:
    payload = base64.b64encode(build_docx(SAMPLE_CV_LINES)).decode("ascii")
    chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)]
    for index, chunk in enumerate(chunks):
        plugin.invoke(
            action="upload_chunk",
            upload_id="up-docx",
            index=index,
            total=len(chunks),
            data_b64=chunk,
        )
    parsed = plugin.invoke(action="parse_cv", source="docx", upload_id="up-docx")["result"]
    assert parsed["success"] is True


def test_an_upload_can_only_be_consumed_once(plugin: Plugin) -> None:
    payload = base64.b64encode(build_pdf(SAMPLE_CV_LINES)).decode("ascii")
    plugin.invoke(action="upload_chunk", upload_id="up-2", index=0, total=1, data_b64=payload)
    plugin.invoke(action="parse_cv", source="pdf", upload_id="up-2")
    again = plugin.invoke(action="parse_cv", source="pdf", upload_id="up-2")["result"]
    assert again["success"] is False
    assert again["data"]["code"] == "upload_expired"


def test_out_of_order_chunks_are_rejected(plugin: Plugin) -> None:
    plugin.invoke(action="upload_chunk", upload_id="up-3", index=0, total=3, data_b64="AAAA")
    reply = plugin.invoke(action="upload_chunk", upload_id="up-3", index=2, total=3, data_b64="AAAA")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_discard_upload_drops_only_the_upload_it_names(plugin: Plugin) -> None:
    """The failure path used to call `forget`, which emptied every buffer.

    Two uploads in flight is the ordinary case for a user who picked the wrong
    file and picked again before the first finished.
    """
    def pending() -> int:
        return int(plugin.invoke(action="health")["result"]["data"]["pending_uploads"])

    plugin.invoke(action="upload_chunk", upload_id="keep-me", index=0, total=2, data_b64="AAAA")
    plugin.invoke(action="upload_chunk", upload_id="drop-me", index=0, total=2, data_b64="AAAA")
    before = pending()

    dropped = plugin.invoke(action="discard_upload", upload_id="drop-me")["result"]
    assert dropped["success"] is True
    assert dropped["data"]["dropped"] is True
    # One fewer, not all of them: the whole point of the action.
    assert pending() == before - 1

    # The survivor is still writable; the discarded one is gone.
    kept = plugin.invoke(
        action="upload_chunk", upload_id="keep-me", index=1, total=2, data_b64="AAAA"
    )["result"]
    assert kept["success"] is True
    gone = plugin.invoke(
        action="upload_chunk", upload_id="drop-me", index=1, total=2, data_b64="AAAA"
    )["result"]
    assert gone["success"] is False
    assert gone["data"]["code"] == "upload_expired"


def test_discarding_an_unknown_upload_is_not_an_error(plugin: Plugin) -> None:
    """The UI calls this on a failure path; it must not fail on top of a failure."""
    reply = plugin.invoke(action="discard_upload", upload_id="never-existed")["result"]
    assert reply["success"] is True
    assert reply["data"]["dropped"] is False


def test_discard_upload_needs_an_id(plugin: Plugin) -> None:
    reply = plugin.invoke(action="discard_upload")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_a_run_loop_is_rate_limited_before_it_reaches_the_model() -> None:
    """The refusal has to arrive as a normal failed invoke, not a protocol error.

    `rate_limited` is retriable and carries the wait, because waiting is the
    fix — the UI turns that into "Run it again in a moment" rather than a dead
    end the user has no move against.
    """
    client = Plugin(rate_limit=True)
    try:
        codes = [
            client.invoke(action="run_match", cv={}, posting_text="x")["result"]
            for _ in range(20)
        ]
    finally:
        client.close()

    refused = [reply for reply in codes if reply["data"].get("code") == "rate_limited"]
    assert refused, "a loop of twenty runs was never throttled"
    assert refused[0]["error"] == "rate_limited"
    assert refused[0]["data"]["retriable"] is True
    assert refused[0]["data"]["details"]["retry_after_s"] > 0


def _gap_sampling_reply(params: dict[str, Any]) -> str:
    """Answer the extract, match and gaps stages in one canned sampler."""
    message = params.get("messages", [{}])[0]
    prompt = str((message.get("content") or {}).get("text") or "")
    if "REQUIREMENTS THE CV DOES NOT PROVE" in prompt:
        return json.dumps(
            {
                "gaps": [
                    {
                        "requirement_id": "R1",
                        # Names the requirement, assumes nothing: must survive.
                        "question": "Have you ever written any Terraform, even once?",
                        "angle": "",
                        "line_ids": [],
                    }
                ]
            }
        )
    if "CANDIDATE CV LINES" in prompt:
        return json.dumps(
            {"evidence": [{"requirement_id": "R1", "status": "missing", "line_ids": [], "why": ""}]}
        )
    return json.dumps(
        {
            "posting_title": "Backend Engineer",
            "company": "Northwind",
            "requirements": [
                {
                    "id": "R1",
                    "text": "Terraform",
                    "kind": "must",
                    "category": "skill",
                    "source_quote": "",
                }
            ],
        }
    )


def test_audit_cv_reports_a_listed_skill_no_line_shows(plugin: Plugin) -> None:
    """Costs no model call, so it answers on the synchronous channel."""
    text = "\n".join(
        [
            "Dilek Aydin",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go for merchants. " * 3,
            "",
            "Skills",
            "Go, Kubernetes",
        ]
    )
    cv = plugin.invoke(action="parse_cv", source="text", text=text)["result"]["data"]
    reply = plugin.invoke(action="audit_cv", cv=cv)["result"]

    assert reply["success"] is True
    assert reply["data"]["cv_hash"] == cv["hash"]
    findings = reply["data"]["findings"]
    assert [f["subject"] for f in findings] == ["kubernetes"]
    assert findings[0]["kind"] == "skill_unevidenced"


def test_recurring_gaps_reports_what_keeps_coming_up(plugin: Plugin) -> None:
    """Answers on the synchronous channel: no model, no tokens."""
    items = [
        {"id": "m1#R1", "match": "m1", "text": "Kubernetes in production", "kind": "must", "status": "missing"},
        {"id": "m2#R4", "match": "m2", "text": "Experience running services on Kubernetes", "kind": "must", "status": "partial"},
        {"id": "m3#R2", "match": "m3", "text": "Kubernetes and Helm", "kind": "must", "status": "missing"},
        {"id": "m1#R7", "match": "m1", "text": "Terraform experience", "kind": "nice", "status": "strong"},
        {"id": "m2#R9", "match": "m2", "text": "Deep Terraform background", "kind": "nice", "status": "strong"},
    ]
    reply = plugin.invoke(action="recurring_gaps", items=items)["result"]

    assert reply["success"] is True
    data = reply["data"]
    assert data["matches"] == 3
    assert [g["key"] for g in data["groups"]] == ["kubernetes"]
    gap = data["groups"][0]
    assert (gap["asked"], gap["unproven"], gap["must"]) == (3, 3, 3)
    assert gap["surface"] == "Kubernetes"
    assert sorted(gap["ids"]) == ["m1#R1", "m2#R4", "m3#R2"]
    assert [g["key"] for g in data["strengths"]] == ["terraform"]


def test_recurring_gaps_needs_a_list(plugin: Plugin) -> None:
    reply = plugin.invoke(action="recurring_gaps")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_recurring_gaps_rejects_a_malformed_item(plugin: Plugin) -> None:
    reply = plugin.invoke(action="recurring_gaps", items=[{"id": "x", "text": "y"}])["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_compare_postings_ranks_by_what_the_cv_proves(plugin: Plugin) -> None:
    """Also synchronous and modelless: arithmetic over verdicts already made."""
    items = [
        {"id": "m1#R1", "match": "m1", "text": "Kubernetes in production", "kind": "must", "status": "missing"},
        {"id": "m1#R2", "match": "m1", "text": "Go experience", "kind": "must", "status": "strong"},
        {"id": "m2#R1", "match": "m2", "text": "Experience running services on Kubernetes", "kind": "must", "status": "missing"},
        {"id": "m2#R2", "match": "m2", "text": "PostgreSQL schema design", "kind": "must", "status": "strong"},
        {"id": "m2#R3", "match": "m2", "text": "Payments domain experience", "kind": "must", "status": "strong"},
    ]
    reply = plugin.invoke(action="compare_postings", items=items)["result"]

    assert reply["success"] is True
    data = reply["data"]
    assert data["postings"] == 2
    # Both leave Kubernetes unproved, so the one that proves more of the rest
    # comes first — and the unproved must-have is named on both.
    assert [column["match"] for column in data["columns"]] == ["m2", "m1"]
    assert all("Kubernetes" in column["blockers"] for column in data["columns"])
    assert [group["surface"] for group in data["shared_gaps"]] == ["Kubernetes"]
    # Proved here and not asked for there: the thing only a comparison can say.
    second = next(column for column in data["columns"] if column["match"] == "m2")
    assert "PostgreSQL" in second["edge"]


def test_compare_postings_says_nothing_about_one_application(plugin: Plugin) -> None:
    items = [
        {"id": "m1#R1", "match": "m1", "text": "Go experience", "kind": "must", "status": "strong"},
    ]
    reply = plugin.invoke(action="compare_postings", items=items)["result"]

    assert reply["success"] is True
    assert reply["data"]["postings"] == 1
    assert reply["data"]["columns"] == []


def test_compare_postings_needs_a_list(plugin: Plugin) -> None:
    reply = plugin.invoke(action="compare_postings")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_line_ledger_counts_what_each_cv_line_has_carried(plugin: Plugin) -> None:
    """Synchronous and modelless as well: citations that were already made."""
    text = "\n".join(
        [
            "Ada Lovelace",
            "",
            "Experience",
            "Northwind - Backend Engineer, 2019-2024",
            "Ran payment services on Kubernetes for three years, 1,200 merchants. " * 2,
            "Wrote the internal newsletter for two years. " * 2,
            "",
            "Skills",
            "Go, Kubernetes",
        ]
    )
    cv = plugin.invoke(action="parse_cv", source="text", text=text)["result"]["data"]
    worked = next(line["id"] for line in cv["lines"] if "Kubernetes for three" in line["text"])
    unasked = next(line["id"] for line in cv["lines"] if "newsletter" in line["text"])
    common = {"kind": "must", "status": "strong", "cv_hash": cv["hash"]}
    items = [
        {"id": "m1#R1", "match": "m1", "text": "Kubernetes in production", "line_ids": [worked], **common},
        {"id": "m2#R1", "match": "m2", "text": "Experience running services on Kubernetes", "line_ids": [worked], **common},
        {"id": "m3#R1", "match": "m3", "text": "Kubernetes and Helm", "line_ids": [worked], **common},
        # Another parse of the CV: the same id points at another sentence there.
        {"id": "m4#R1", "match": "m4", "text": "Kubernetes", "line_ids": [worked], "kind": "must", "status": "strong", "cv_hash": "another-parse"},
    ]

    reply = plugin.invoke(action="line_ledger", cv=cv, items=items)["result"]

    assert reply["success"] is True
    data = reply["data"]
    assert (data["applications"], data["skipped"]) == (3, 1)
    assert [line["id"] for line in data["working"]] == [worked]
    carried = data["working"][0]
    assert (carried["applications"], carried["decisive"]) == (3, 3)
    # Merged the three wordings into one demand, and the posting that also
    # asked for Helm is credited with that too.
    assert carried["proves"][0] == "Kubernetes"
    assert unasked in [line["id"] for line in data["idle"]]


def test_line_ledger_reads_a_cv_that_has_grown_since_those_applications(plugin: Plugin) -> None:
    """A gap answer moves the hash; refusing here would punish preparing."""
    cv = plugin.invoke(
        action="parse_cv",
        source="text",
        text="Ada Lovelace\n\nExperience\nRan services on Kubernetes for three years at Northwind. " * 3,
    )["result"]["data"]
    common = {"kind": "must", "status": "strong", "cv_hash": cv["hash"]}
    edited = dict(cv, hash=f"{cv['hash']}~e2")
    line = cv["lines"][-1]["id"]
    items = [
        {"id": f"m{n}#R1", "match": f"m{n}", "text": "Kubernetes", "line_ids": [line], **common}
        for n in range(3)
    ]

    reply = plugin.invoke(action="line_ledger", cv=edited, items=items)["result"]

    assert reply["success"] is True
    assert (reply["data"]["applications"], reply["data"]["skipped"]) == (3, 0)


def test_line_ledger_needs_a_cv_and_a_list(plugin: Plugin) -> None:
    for args in ({"items": []}, {"cv": {"version": 1, "hash": "h", "lines": [], "detected_language": "en"}}):
        reply = plugin.invoke(action="line_ledger", **args)["result"]
        assert reply["success"] is False
        assert reply["data"]["code"] == "invalid_args"


def test_since_applied_reports_what_the_cv_gained_after_it_went_out(plugin: Plugin) -> None:
    """No model here either: dates and a lexicon lookup over stored records."""
    text = "\n".join(
        [
            "Ada Lovelace",
            "",
            "Experience",
            "Northwind - Backend Engineer, 2019-2024",
            "Built payment reconciliation services in Go for 1,200 merchants. " * 3,
            "Migrated the reporting pipeline to PostgreSQL with no downtime. " * 3,
        ]
    )
    cv = plugin.invoke(action="parse_cv", source="text", text=text)["result"]["data"]
    # The sentence the user wrote into Receipts a week after applying.
    cv = dict(
        cv,
        hash=f"{cv['hash']}~e1",
        lines=[
            *cv["lines"],
            {
                "id": "L99",
                "text": "Owned the Kafka consumer rewrite at Northwind, 2023.",
                "section": "experience",
                "added_at": "2026-09-20T10:00:00Z",
            },
        ],
    )
    match = {
        "version": 1,
        "id": "m1",
        "created_at": "2026-09-10T09:00:00+00:00",
        "posting": {"hash": "p1", "language": "en", "title": "Backend Engineer"},
        "requirements": [
            {"id": "R1", "text": "Production experience with Kafka", "kind": "must", "category": "skill", "source_quote": "Kafka"},
            {"id": "R2", "text": "Backend engineering in Go", "kind": "must", "category": "skill", "source_quote": "Go"},
        ],
        "evidence": [
            {"requirement_id": "R1", "status": "missing", "line_ids": [], "why": ""},
            {"requirement_id": "R2", "status": "strong", "line_ids": ["L4"], "why": ""},
        ],
        "summary": {"total": 2, "strong": 1, "partial": 0, "missing": 1, "must_missing": 1, "sentence": ""},
        "cv_hash": "an-older-hash",
    }

    reply = plugin.invoke(action="since_applied", cv=cv, match=match, sent_at="2026-09-12T09:00:00Z")["result"]

    assert reply["success"] is True
    data = reply["data"]
    assert data["cv_changed"] is True
    assert data["added"] == ["L99"]
    assert [answer["requirement_id"] for answer in data["answers"]] == ["R1"]
    assert data["answers"][0]["terms"] == ["Kafka"]
    # Dated from what the user said, and the payload says which clock it used.
    assert data["dated_from"] == "sent"
    assert data["days"] >= 0


def test_since_applied_needs_a_cv_and_a_match(plugin: Plugin) -> None:
    reply = plugin.invoke(action="since_applied")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_compare_runs_credits_the_line_the_user_wrote_between_them(plugin: Plugin) -> None:
    """The payoff of the whole answer loop, and no model anywhere in it."""
    cv = {
        "version": 1,
        "hash": "h~e1",
        "detected_language": "en",
        "warnings": [],
        "lines": [
            {"id": "L2", "text": "Built payment services in Go at Northwind.", "section": "experience"},
            {
                "id": "L9",
                "text": "Owned the Kafka consumer rewrite at Northwind, 2023.",
                "section": "experience",
                "added_at": "2026-09-18T10:00:00Z",
            },
        ],
    }
    before = {'version': 1, 'id': 'm1', 'created_at': '2026-09-10T09:00:00+00:00', 'posting': {'hash': 'p1', 'language': 'en', 'title': 'Backend Engineer'}, 'requirements': [{'id': 'R1', 'text': 'Production experience with Kafka', 'kind': 'must', 'category': 'skill', 'source_quote': 'Production experience with Kaf'}], 'evidence': [{'requirement_id': 'R1', 'status': 'missing', 'line_ids': [], 'why': ''}], 'summary': {'total': 1, 'strong': 0, 'partial': 0, 'missing': 0, 'must_missing': 0, 'sentence': ''}, 'cv_hash': 'h'}
    after = {'version': 1, 'id': 'm2', 'created_at': '2026-09-24T09:00:00+00:00', 'posting': {'hash': 'p1', 'language': 'en', 'title': 'Backend Engineer'}, 'requirements': [{'id': 'R1', 'text': 'Kafka in production', 'kind': 'must', 'category': 'skill', 'source_quote': 'Kafka in production'}, {'id': 'R2', 'text': 'Kubernetes and Helm', 'kind': 'must', 'category': 'skill', 'source_quote': 'Kubernetes and Helm'}], 'evidence': [{'requirement_id': 'R1', 'status': 'strong', 'line_ids': ['L9'], 'why': ''}, {'requirement_id': 'R2', 'status': 'missing', 'line_ids': [], 'why': ''}], 'summary': {'total': 2, 'strong': 1, 'partial': 0, 'missing': 0, 'must_missing': 0, 'sentence': ''}, 'cv_hash': 'h'}

    reply = plugin.invoke(action="compare_runs", cv=cv, before=before, match=after)["result"]

    assert reply["success"] is True
    data = reply["data"]
    assert [change["surface"] for change in data["gained"]] == ["Kafka"]
    assert data["gained"][0]["credited"] is True
    assert data["added_between"] == ["L9"]
    assert data["days_between"] == 14
    # The newer run asks for something the older one never did: about the
    # reading, not about the candidate, so it is kept out of the gains. It
    # names two terms and is counted under each, the way every screen that
    # groups by lexicon counts a requirement naming two technologies.
    assert sorted(change["surface"] for change in data["differed"]) == ["Helm", "Kubernetes"]
    assert {change["direction"] for change in data["differed"]} == {"new_ask"}


def test_compare_runs_needs_both_runs(plugin: Plugin) -> None:
    cv = {"version": 1, "hash": "h", "lines": [], "detected_language": "en"}
    reply = plugin.invoke(action="compare_runs", cv=cv)["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_worth_rerunning_names_the_applications_the_cv_has_answered(plugin: Plugin) -> None:
    """The shelf-wide version of `since_applied`, and modelless like it."""
    cv = {
        "version": 1,
        "hash": "h~e1",
        "detected_language": "en",
        "warnings": [],
        "lines": [
            {"id": "L2", "text": "Built payment services in Go at Northwind.", "section": "experience"},
            {
                "id": "L9",
                "text": "Owned the Kafka consumer rewrite at Northwind, 2023.",
                "section": "experience",
                "added_at": "2026-09-20T10:00:00Z",
            },
        ],
    }
    sent_before = "2026-09-10T09:00:00+00:00"
    sent_after = "2026-09-22T09:00:00+00:00"
    items = [
        {"id": "m1#R1", "match": "m1", "text": "Production experience with Kafka", "kind": "must", "status": "missing", "created_at": sent_before},
        {"id": "m1#R2", "match": "m1", "text": "Go experience", "kind": "must", "status": "strong", "created_at": sent_before},
        # Sent after the line was written: that match already read it.
        {"id": "m2#R1", "match": "m2", "text": "Kafka in production", "kind": "must", "status": "missing", "created_at": sent_after},
    ]

    reply = plugin.invoke(action="worth_rerunning", cv=cv, items=items)["result"]

    assert reply["success"] is True
    data = reply["data"]
    assert data["applications"] == 2
    assert data["written"] == 1
    assert [row["match"] for row in data["items"]] == ["m1"]
    row = data["items"][0]
    assert row["terms"] == ["Kafka"]
    assert row["line_ids"] == ["L9"]
    assert (row["requirements"], row["must"], row["unproved"]) == (1, 1, 1)


def test_followup_declines_without_a_host_when_there_is_nothing_new(plugin: Plugin) -> None:
    """The refusal is decided from records, so it needs no sampling at all.

    Every other generated action in this plugin is untestable here for want of
    a host. This one answers, which is the property worth having: a candidate
    whose CV has not moved gets told so for free.
    """
    cv = {
        "version": 1,
        "hash": "h",
        "detected_language": "en",
        "warnings": [],
        "lines": [
            {"id": "L2", "text": "Built payment services in Go at Northwind.", "section": "experience"},
        ],
    }
    match = {
        "version": 1,
        "id": "m1",
        "created_at": "2026-09-10T09:00:00+00:00",
        "posting": {"hash": "p1", "language": "en", "title": "Backend Engineer"},
        "requirements": [
            {"id": "R1", "text": "Production experience with Kafka", "kind": "must", "category": "skill", "source_quote": "Kafka"},
        ],
        "evidence": [{"requirement_id": "R1", "status": "missing", "line_ids": [], "why": ""}],
        "summary": {"total": 1, "strong": 0, "partial": 0, "missing": 1, "must_missing": 1, "sentence": ""},
        "cv_hash": "h",
    }

    reply = plugin.invoke(action="followup", cv=cv, match=match, sent_at="2026-09-12T09:00:00Z")["result"]

    assert reply["success"] is True
    data = reply["data"]
    assert data["kind"] == "nothing_new"
    assert data["paragraphs"] == []
    assert data["dated_from"] == "sent"


def test_followup_needs_a_cv_and_a_match(plugin: Plugin) -> None:
    reply = plugin.invoke(action="followup")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_worth_rerunning_needs_a_cv_and_a_list(plugin: Plugin) -> None:
    cv = {"version": 1, "hash": "h", "lines": [], "detected_language": "en"}
    reply = plugin.invoke(action="worth_rerunning", cv=cv)["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_interview_brief_separates_a_receipt_from_a_listed_skill(plugin: Plugin) -> None:
    """No model either: the brief is arithmetic over records that already exist."""
    text = "\n".join(
        [
            "Dilek Aydin",
            "",
            "Experience",
            "Acme Payments - Backend Engineer, 2018-2024",
            "Built payment reconciliation services in Go for 1,200 merchants. " * 3,
            "",
            "Skills",
            "Go, Kubernetes",
        ]
    )
    cv = plugin.invoke(action="parse_cv", source="text", text=text)["result"]["data"]
    go_line = next(line["id"] for line in cv["lines"] if "reconciliation" in line["text"])
    skills_line = next(line["id"] for line in cv["lines"] if line["section"] == "skills")
    match = {
        "version": 1,
        "id": "m1",
        "created_at": "2026-09-19T09:00:00+00:00",
        "posting": {"hash": "p1", "language": "en", "title": "Backend Engineer"},
        "requirements": [
            {"id": "R1", "text": "Production Go", "kind": "must", "category": "skill", "source_quote": "Go"},
            {"id": "R2", "text": "Kubernetes", "kind": "must", "category": "skill", "source_quote": "k8s"},
            {"id": "R3", "text": "Kafka", "kind": "must", "category": "skill", "source_quote": "Kafka"},
        ],
        "evidence": [
            {"requirement_id": "R1", "status": "strong", "line_ids": [go_line], "why": ""},
            {"requirement_id": "R2", "status": "strong", "line_ids": [skills_line], "why": ""},
            {"requirement_id": "R3", "status": "missing", "line_ids": [], "why": ""},
        ],
        "summary": {"total": 3, "strong": 2, "partial": 0, "missing": 1, "must_missing": 1, "sentence": ""},
        "cv_hash": cv["hash"],
    }

    reply = plugin.invoke(action="interview_brief", cv=cv, match=match)["result"]

    assert reply["success"] is True
    data = reply["data"]
    assert data["cv_changed"] is False
    assert [(item["requirement_id"], item["risk"]) for item in data["risks"]] == [
        ("R3", "no_evidence"),
        ("R2", "listed_not_shown"),
    ]
    assert [item["requirement_id"] for item in data["proved"]] == ["R1"]


def test_interview_brief_accepts_a_cv_that_moved_after_the_application(
    plugin: Plugin, sample_cv_text: str
) -> None:
    """`tailor` refuses this; the brief must not — answering a gap moves the hash."""
    cv = plugin.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
    match = {
        "version": 1,
        "id": "m1",
        "created_at": "2026-09-19T09:00:00+00:00",
        "posting": {"hash": "p1", "language": "en"},
        "requirements": [
            {"id": "R1", "text": "Production Go", "kind": "must", "category": "skill", "source_quote": "Go"}
        ],
        "evidence": [{"requirement_id": "R1", "status": "missing", "line_ids": [], "why": ""}],
        "summary": {"total": 1, "strong": 0, "partial": 0, "missing": 1, "must_missing": 1, "sentence": ""},
        "cv_hash": cv["hash"] + "~e1",
    }

    reply = plugin.invoke(action="interview_brief", cv=cv, match=match)["result"]

    assert reply["success"] is True
    assert reply["data"]["cv_changed"] is True


def test_interview_brief_needs_a_match(plugin: Plugin) -> None:
    reply = plugin.invoke(action="interview_brief", cv={"version": 1})["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_audit_cv_needs_a_cv(plugin: Plugin) -> None:
    reply = plugin.invoke(action="audit_cv")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_gaps_returns_a_question_for_an_unproven_requirement(sample_cv_text: str) -> None:
    """The app's answer to its own third principle: a gap is a plan, not a shame."""
    client = Plugin(sampler=_gap_sampling_reply)
    try:
        cv = client.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
        match = client.invoke(
            action="run_match",
            cv=cv,
            posting_text="Backend Engineer. Requirements: Terraform experience. " * 6,
            timeout=25.0,
        )["result"]
        assert match["success"] is True

        reply = client.invoke(action="gaps", cv=cv, match=match["data"], timeout=25.0)["result"]
    finally:
        client.close()

    assert reply["success"] is True
    items = reply["data"]["items"]
    assert [item["requirement_id"] for item in items] == ["R1"]
    assert items[0]["question"] == "Have you ever written any Terraform, even once?"
    assert items[0]["templated"] is False
    assert items[0]["angle"] is None


def test_gaps_refuses_a_match_made_against_another_cv(plugin: Plugin, sample_cv_text: str) -> None:
    cv = plugin.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
    stale = {
        "version": 1,
        "id": "m1",
        "created_at": "2026-09-19T10:00:00+00:00",
        "posting": {"hash": "h", "language": "en"},
        "requirements": [],
        "evidence": [],
        "summary": {
            "total": 0,
            "strong": 0,
            "partial": 0,
            "missing": 0,
            "must_missing": 0,
            "sentence": "",
        },
        "cv_hash": "a-different-cv",
    }
    reply = plugin.invoke(action="gaps", cv=cv, match=stale)["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_parse_cv_without_an_upload_id_is_an_argument_error(plugin: Plugin) -> None:
    reply = plugin.invoke(action="parse_cv", source="pdf")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_run_match_without_sampling_fails_cleanly(sample_cv_text: str) -> None:
    # A v1 host offers no sampling channel, so run_match must surface
    # `sampling_unavailable` rather than hanging or reporting an empty success.
    client = Plugin(protocol="1.1")
    try:
        cv = client.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
        reply = client.invoke(
            action="run_match",
            cv=cv,
            posting_text="Requirements: 5 years of Go and Kubernetes experience. " * 6,
        )["result"]
    finally:
        client.close()
    assert reply["success"] is False
    assert reply["data"]["code"] == "sampling_unavailable"


def test_progress_events_are_emitted_during_a_run(sample_cv_text: str) -> None:
    client = Plugin(protocol="1.1")
    try:
        cv = client.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
        client.invoke(
            action="run_match",
            cv=cv,
            posting_text="Requirements: 5 years of Go and Kubernetes experience. " * 6,
        )
        events = [n for n in client.notifications if n.get("method") == "executa/progress"]
    finally:
        client.close()
    assert events, "run_match must report progress"
    first = events[0]["params"]
    assert first["context"]["invoke_id"] == "test-invoke"
    assert first["data"]["stage"] == "normalize"


def test_tailoring_a_match_from_another_cv_is_refused(plugin: Plugin, sample_cv_text: str) -> None:
    cv = plugin.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
    match = {
        "version": 1,
        "id": "m1",
        "created_at": "2026-09-16T00:00:00+00:00",
        "posting": {"hash": "h", "language": "en"},
        "requirements": [],
        "evidence": [],
        "summary": {
            "total": 0,
            "strong": 0,
            "partial": 0,
            "missing": 0,
            "must_missing": 0,
            "sentence": "",
        },
        "cv_hash": "a-different-cv",
    }
    reply = plugin.invoke(action="tailor", cv=cv, match=match)["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_export_docx_returns_openable_bytes(plugin: Plugin) -> None:
    tailor = {
        "version": 1,
        "match_id": "m1",
        "bullets": [
            {
                "source_line_ids": ["L6"],
                "original": "Built payment reconciliation services in Go.",
                "suggestion": "Built payment reconciliation services in Go.",
                "targets": ["R1"],
            }
        ],
    }
    result = plugin.invoke(
        action="export_docx", tailor_result=tailor, company="Northwind", role="Backend Engineer"
    )["result"]
    assert result["success"] is True
    assert result["data"]["filename"].endswith(".docx")

    import io

    import docx

    document = docx.Document(io.BytesIO(base64.b64decode(result["data"]["content_b64"])))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "reconciliation" in text


def test_export_cv_returns_the_users_own_lines(plugin: Plugin, sample_cv_text: str) -> None:
    """The CV back out: no model, no verifier, and not one word changed."""
    cv = plugin.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
    result = plugin.invoke(action="export_cv", cv=cv, mode="full")["result"]

    assert result["success"] is True
    assert result["data"]["filename"].startswith("cv-")
    assert result["data"]["lines"] == len(cv["lines"])

    import io

    import docx

    document = docx.Document(io.BytesIO(base64.b64decode(result["data"]["content_b64"])))
    rendered = [paragraph.text for paragraph in document.paragraphs]
    for line in cv["lines"]:
        assert line["text"] in rendered


def test_export_cv_rejects_a_mode_it_does_not_have(plugin: Plugin, sample_cv_text: str) -> None:
    cv = plugin.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
    reply = plugin.invoke(action="export_cv", cv=cv, mode="everything")["result"]

    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


def test_export_docx_needs_something_to_render(plugin: Plugin) -> None:
    reply = plugin.invoke(action="export_docx")["result"]
    assert reply["success"] is False
    assert reply["data"]["code"] == "invalid_args"


# ─── Concurrency ──────────────────────────────────────────────────────


def _canned_sampling_reply(params: dict[str, Any]) -> str:
    """Answer whichever pipeline stage asked, after a beat.

    The delay is the point: every worker must still be parked on its sampling
    call when the next reply arrives, which is the situation that used to
    deadlock the plugin.
    """
    message = params.get("messages", [{}])[0]
    prompt = str((message.get("content") or {}).get("text") or "")
    time.sleep(0.4)
    if "CANDIDATE CV LINES" in prompt:
        return json.dumps(
            {
                "evidence": [
                    {
                        "requirement_id": "R1",
                        "status": "strong",
                        "line_ids": ["L1"],
                        "why": "the line names Go",
                    }
                ]
            }
        )
    return json.dumps(
        {
            "posting_title": "Backend Engineer",
            "company": "Northwind",
            "requirements": [
                {
                    "id": "R1",
                    "text": "Go experience",
                    "kind": "must",
                    "category": "skill",
                    "source_quote": "",
                }
            ],
        }
    )


def test_sampling_replies_are_dispatched_while_every_worker_is_busy(
    sample_cv_text: str,
) -> None:
    # One more concurrent run than the plugin has invoke workers. Each one
    # parks waiting for a sampling reply, so the reply frames have to be read
    # by the thread that owns stdin — queueing them behind the invokes they
    # unblock is a deadlock, and it used to be one.
    client = Plugin(sampler=_canned_sampling_reply)
    runs = 5
    results: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    try:
        cv = client.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]

        def run(index: int) -> None:
            try:
                reply = client.invoke(
                    action="run_match",
                    cv=cv,
                    # Distinct text per run: a shared posting would be served
                    # from the requirement cache and never call the model.
                    posting_text=(
                        f"Backend Engineer #{index}. Requirements: Go experience. " * 6
                    ),
                    invoke_id=f"concurrent-{index}",
                    timeout=25.0,
                )
                results.append(reply["result"])
            except BaseException as exc:  # noqa: BLE001 — reported by the assertion
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(index,)) for index in range(runs)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=40)
    finally:
        client.close()

    assert not errors, f"concurrent run_match failed: {errors[0]!r}"
    assert len(results) == runs
    assert all(result["success"] is True for result in results)


def test_export_docx_flags_a_hand_edited_line_it_cannot_trace(
    plugin: Plugin, sample_cv_text: str
) -> None:
    # The user can edit a suggestion before accepting it, so what reaches the
    # document is not always what the verifier approved. With the CV attached,
    # the engine says so — in the payload and in the document's own footer.
    cv = plugin.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
    tailor = {
        "version": 1,
        "match_id": "m1",
        "bullets": [
            {
                "source_line_ids": ["L1"],
                "original": cv["lines"][0]["text"],
                "suggestion": "Increased revenue by 97% at Globex in 2011.",
                "targets": [],
            }
        ],
    }
    result = plugin.invoke(action="export_docx", tailor_result=tailor, cv=cv)["result"]
    assert result["success"] is True
    assert result["data"]["unverified"] == 1

    import io

    import docx

    document = docx.Document(io.BytesIO(base64.b64decode(result["data"]["content_b64"])))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "could not be traced" in text


def test_export_docx_keeps_the_plain_footer_when_every_line_traces(
    plugin: Plugin, sample_cv_text: str
) -> None:
    cv = plugin.invoke(action="parse_cv", source="text", text=sample_cv_text)["result"]["data"]
    line = cv["lines"][0]
    tailor = {
        "version": 1,
        "match_id": "m1",
        "bullets": [
            {
                "source_line_ids": [line["id"]],
                "original": line["text"],
                "suggestion": line["text"],
                "targets": [],
            }
        ],
    }
    result = plugin.invoke(action="export_docx", tailor_result=tailor, cv=cv)["result"]
    assert result["data"]["unverified"] == 0

    import io

    import docx

    document = docx.Document(io.BytesIO(base64.b64decode(result["data"]["content_b64"])))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "traceable to your CV" in text
