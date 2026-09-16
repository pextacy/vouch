"""Upload buffering, schema generation and the deterministic summary."""

from __future__ import annotations

import base64
import json

import pytest

from receipts_engine.errors import EngineError
from receipts_engine.llm import extract_json, response_format, schema_for
from receipts_engine.llm.json_schema import MAX_NODES, MAX_SERIALIZED_BYTES
from receipts_engine.pipeline import sentence_for
from receipts_engine.schemas import ExtractionOutput, LetterOutput, MatchingOutput, TailorOutput
from receipts_engine.uploads import MAX_UPLOAD_BYTES, UploadBuffer

# ─── Upload buffer ────────────────────────────────────────────────────


def _b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def test_a_single_chunk_upload_round_trips() -> None:
    buffer = UploadBuffer()
    buffer.add_chunk(upload_id="u", index=0, total=1, data_b64=_b64(b"hello"), filename="cv.pdf")
    assert buffer.take("u") == (b"hello", "cv.pdf")


def test_chunks_are_reassembled_in_order() -> None:
    buffer = UploadBuffer()
    for index, part in enumerate([b"abc", b"def", b"ghi"]):
        buffer.add_chunk(upload_id="u", index=index, total=3, data_b64=_b64(part))
    assert buffer.take("u")[0] == b"abcdefghi"


def test_completion_is_reported_on_the_last_chunk() -> None:
    buffer = UploadBuffer()
    first = buffer.add_chunk(upload_id="u", index=0, total=2, data_b64=_b64(b"ab"))
    second = buffer.add_chunk(upload_id="u", index=1, total=2, data_b64=_b64(b"cd"))
    assert first["complete"] is False
    assert second["complete"] is True


def test_taking_an_incomplete_upload_is_refused() -> None:
    buffer = UploadBuffer()
    buffer.add_chunk(upload_id="u", index=0, total=2, data_b64=_b64(b"ab"))
    with pytest.raises(EngineError) as excinfo:
        buffer.take("u")
    assert excinfo.value.code == "invalid_args"


def test_an_out_of_order_chunk_is_refused() -> None:
    buffer = UploadBuffer()
    buffer.add_chunk(upload_id="u", index=0, total=3, data_b64=_b64(b"ab"))
    with pytest.raises(EngineError) as excinfo:
        buffer.add_chunk(upload_id="u", index=2, total=3, data_b64=_b64(b"cd"))
    assert excinfo.value.code == "invalid_args"


def test_a_continuation_without_a_first_chunk_has_expired() -> None:
    buffer = UploadBuffer()
    with pytest.raises(EngineError) as excinfo:
        buffer.add_chunk(upload_id="u", index=1, total=2, data_b64=_b64(b"ab"))
    assert excinfo.value.code == "upload_expired"


def test_non_base64_payloads_are_rejected() -> None:
    buffer = UploadBuffer()
    with pytest.raises(EngineError) as excinfo:
        buffer.add_chunk(upload_id="u", index=0, total=1, data_b64="not base64!!")
    assert excinfo.value.code == "invalid_args"


def test_exceeding_the_size_ceiling_is_rejected_mid_upload() -> None:
    buffer = UploadBuffer()
    chunk = _b64(b"x" * 90_000)
    total = MAX_UPLOAD_BYTES // 90_000 + 2
    with pytest.raises(EngineError) as excinfo:
        for index in range(total):
            buffer.add_chunk(upload_id="u", index=index, total=total, data_b64=chunk)
    assert excinfo.value.code == "file_too_large"


def test_an_oversized_chunk_is_rejected_outright() -> None:
    buffer = UploadBuffer()
    with pytest.raises(EngineError) as excinfo:
        buffer.add_chunk(upload_id="u", index=0, total=1, data_b64="A" * (400 * 1024))
    assert excinfo.value.code == "file_too_large"


def test_an_expired_upload_is_gone() -> None:
    buffer = UploadBuffer(ttl_s=-1.0)
    buffer.add_chunk(upload_id="u", index=0, total=1, data_b64=_b64(b"ab"))
    with pytest.raises(EngineError) as excinfo:
        buffer.take("u")
    assert excinfo.value.code == "upload_expired"


def test_taking_an_upload_clears_it() -> None:
    buffer = UploadBuffer()
    buffer.add_chunk(upload_id="u", index=0, total=1, data_b64=_b64(b"ab"))
    buffer.take("u")
    assert len(buffer) == 0


def test_concurrent_uploads_are_bounded() -> None:
    buffer = UploadBuffer()
    for index in range(10):
        buffer.add_chunk(upload_id=f"u{index}", index=0, total=2, data_b64=_b64(b"ab"))
    assert len(buffer) <= 4


def test_a_missing_upload_id_is_an_argument_error() -> None:
    buffer = UploadBuffer()
    with pytest.raises(EngineError) as excinfo:
        buffer.add_chunk(upload_id="", index=0, total=1, data_b64=_b64(b"ab"))
    assert excinfo.value.code == "invalid_args"


# ─── Generated JSON Schemas ───────────────────────────────────────────


@pytest.mark.parametrize("model", [ExtractionOutput, MatchingOutput, TailorOutput, LetterOutput])
def test_every_llm_schema_fits_the_host_limits(model: type) -> None:
    schema = schema_for(model)  # type: ignore[arg-type]
    payload = json.dumps(schema)
    assert len(payload.encode("utf-8")) <= MAX_SERIALIZED_BYTES
    assert payload.count(":") < MAX_NODES


@pytest.mark.parametrize("model", [ExtractionOutput, MatchingOutput, TailorOutput, LetterOutput])
def test_every_object_forbids_extra_properties(model: type) -> None:
    schema = schema_for(model)  # type: ignore[arg-type]

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)


def test_schemas_contain_no_unresolved_refs() -> None:
    assert "$ref" not in json.dumps(schema_for(ExtractionOutput))


def test_response_format_matches_the_host_envelope() -> None:
    fmt = response_format("receipts_requirements", ExtractionOutput)
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "receipts_requirements"


def test_an_invalid_schema_name_is_refused() -> None:
    with pytest.raises(ValueError, match="schema name"):
        response_format("not a valid name!", ExtractionOutput)


# ─── JSON extraction ──────────────────────────────────────────────────


def test_plain_json_is_parsed() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_fenced_json_is_parsed() -> None:
    assert extract_json('Sure:\n```json\n{"a": 1}\n```') == {"a": 1}


def test_json_surrounded_by_prose_is_parsed() -> None:
    assert extract_json('Here it is: {"a": 1} — hope that helps') == {"a": 1}


def test_braces_inside_strings_do_not_confuse_the_scanner() -> None:
    assert extract_json('prefix {"a": "} not the end {"} suffix') == {"a": "} not the end {"}


def test_unparseable_output_returns_none() -> None:
    assert extract_json("no json here") is None


def test_empty_output_returns_none() -> None:
    assert extract_json("   ") is None


# ─── Summary sentence ─────────────────────────────────────────────────


def test_english_summary_names_both_counts() -> None:
    assert sentence_for(14, 9, 2, "en") == (
        "9 of 14 requirements have evidence in your CV. 2 must-haves don't."
    )


def test_english_summary_is_singular_for_one_gap() -> None:
    assert sentence_for(10, 9, 1, "en").endswith("1 must-have doesn't.")


def test_summary_omits_the_warning_when_nothing_is_missing() -> None:
    assert sentence_for(10, 10, 0, "en") == "10 of 10 requirements have evidence in your CV."


def test_turkish_summary_is_written_in_turkish() -> None:
    assert sentence_for(14, 9, 2, "tr").startswith("14 gereksinimden 9 tanesi")
