"""Turn a Pydantic model into a schema the host's strict mode accepts.

Never hand-write these — they would drift from the models the response is
validated against, and a schema that permits a shape the validator rejects
turns a model success into a user-visible failure.

Strict ``json_schema`` mode is fussy in three ways, all handled here:

* every property must appear in ``required`` (Pydantic omits defaulted ones);
* ``additionalProperties: false`` must be explicit on every object;
* ``$ref``/``$defs`` support varies by provider, so definitions are inlined.

Host limits: ≤ 32 KB serialised, depth ≤ 8, ≤ 512 nodes — asserted here so a
schema that would be rejected at runtime fails in the test suite instead.
"""

from __future__ import annotations

import json
from typing import Any, Final

from pydantic import BaseModel

MAX_SERIALIZED_BYTES: Final[int] = 32 * 1024
MAX_DEPTH: Final[int] = 8
MAX_NODES: Final[int] = 512

#: Keywords Pydantic emits that strict mode has no use for, and that only
#: consume the node budget.
_DROP_KEYS: Final[frozenset[str]] = frozenset({"title", "default", "examples", "$schema"})


class SchemaTooComplexError(RuntimeError):
    """The generated schema would be rejected by the sampling host."""


def schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Generate an inlined, strict-mode JSON Schema for ``model``."""
    raw: dict[str, Any] = dict(model.model_json_schema(ref_template="#/$defs/{model}"))
    defs: dict[str, Any] = raw.pop("$defs", {})
    inlined = _inline(raw, defs, depth=0)
    if not isinstance(inlined, dict):  # pragma: no cover - a model is always an object
        raise SchemaTooComplexError("top-level schema is not an object")
    _enforce_limits(inlined)
    return inlined


def _inline(node: Any, defs: dict[str, Any], *, depth: int) -> Any:
    if depth > MAX_DEPTH + 4:
        raise SchemaTooComplexError("schema nesting exceeds the host's depth budget")

    if isinstance(node, list):
        return [_inline(item, defs, depth=depth + 1) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        target = defs.get(ref.rsplit("/", 1)[-1])
        if target is None:
            raise SchemaTooComplexError(f"unresolved $ref {ref!r}")
        merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        return _inline(merged, defs, depth=depth + 1)

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROP_KEYS:
            continue
        out[key] = _inline(value, defs, depth=depth + 1)

    # Collapse the `anyOf: [X, null]` Pydantic emits for optionals into a
    # nullable type — strict mode understands a type union, not a bare anyOf
    # wrapper around a single real branch.
    out = _collapse_nullable(out)

    if out.get("type") == "object":
        properties = out.get("properties")
        if isinstance(properties, dict):
            out["required"] = list(properties.keys())
        out["additionalProperties"] = False
    return out


def _collapse_nullable(node: dict[str, Any]) -> dict[str, Any]:
    options = node.get("anyOf")
    if not isinstance(options, list) or len(options) != 2:
        return node
    non_null = [opt for opt in options if opt.get("type") != "null"]
    if len(non_null) != 1 or len(options) - len(non_null) != 1:
        return node
    collapsed = dict(non_null[0])
    inner = collapsed.get("type")
    if isinstance(inner, str):
        collapsed["type"] = [inner, "null"]
    rest = {k: v for k, v in node.items() if k != "anyOf"}
    return {**collapsed, **rest}


def _enforce_limits(schema: dict[str, Any]) -> None:
    payload = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    size = len(payload.encode("utf-8"))
    if size > MAX_SERIALIZED_BYTES:
        raise SchemaTooComplexError(f"schema is {size} B, host allows {MAX_SERIALIZED_BYTES} B")

    nodes = 0
    max_depth = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal nodes, max_depth
        nodes += 1
        max_depth = max(max_depth, depth)
        if isinstance(node, dict):
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                walk(value, depth + 1)

    walk(schema, 0)
    if nodes > MAX_NODES:
        raise SchemaTooComplexError(f"schema has {nodes} nodes, host allows {MAX_NODES}")
    if max_depth > MAX_DEPTH:
        raise SchemaTooComplexError(f"schema depth {max_depth} exceeds host limit {MAX_DEPTH}")


def response_format(name: str, model: type[BaseModel]) -> dict[str, Any]:
    """Build the ``responseFormat`` payload for ``sampling/createMessage``."""
    if not name.replace("_", "").replace("-", "").isalnum() or len(name) > 64:
        raise ValueError(f"schema name {name!r} must match ^[A-Za-z0-9_-]{{1,64}}$")
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema_for(model)},
    }
