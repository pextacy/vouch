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
    ) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "receipts_engine.plugin"],
            cwd=ENGINE_DIR,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
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
        "upload_chunk",
        "parse_cv",
        "run_match",
        "tailor",
        "letter",
        "export_docx",
    }


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
