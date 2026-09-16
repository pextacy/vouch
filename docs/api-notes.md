# Anna host API — verified notes

Phase 0 output. Every signature below was read from the Anna Developer Hub on
**16 September 2026** (`https://anna.partners/llms.txt` → the `.md` version of each
page) or from the public reference repo
`github.com/whtcjdtc2007/anna-executa-examples` at commit `main`.

**Rule:** code follows this file. If a call fails at runtime, re-read the page,
update this file, then change the code — never the other way round.

Legend: ✅ verified against docs · 🧪 verified against example source ·
⚠️ docs disagree with each other (decision recorded)

---

## 1. Manifest

| Fact | Value | Source |
|---|---|---|
| `schema` | `1` (no UI), `2` (UI), `3` (UI + structured `storage`, `permissions` removed) ✅ | `apps/app-manifest.md` |
| `form_factors` | lives at **`ui.form_factors`**, not top level. `["desktop"]` by default; add `"mobile"` to appear in the mobile launcher ✅ | `apps/app-ui-manifest.md`, `apps/app-mobile.md` |
| `permissions[]` | display-only on schema ≤ 2, **rejected on schema 3**. Never enforced anywhere ✅ | `apps/app-ui-manifest.md` §"Top-level permissions" |
| `storage` (schema 3) | `{ kv: bool, files: bool, scopes?: {user\|app\|tool: "r"\|"w"\|"rw"} }`. Mutually exclusive with `aps.*` in `host_capabilities` ✅ | `apps/app-manifest.md` §storage |
| `host_capabilities` | strict allow-list: `llm.sample`, `llm.complete`, `llm.embed`, `llm.agent.*`, `llm.image*`, `web.search`, `web.fetch`, `web.image_search`, `web.image_fetch`, `host.upload`, `aps.kv`, `aps.files`, `aps.scope.*` ✅ | `apps/app-manifest.md` |
| `required_executas[].tool_id` | must resolve to a published Executa **or** a `bundled:<handle>` reference resolved at publish time 🧪 | `anna-app-focus-flow/manifest.json` |
| `ui.host_api.tools` | `required:*` \| `optional:*` \| `required:<id>` \| `<id>` \| `bundled:<handle>`. Empty/omitted ⇒ every declared executa is callable ✅ | `apps/app-ui-host-api.md` §tools |
| `ui.views[].icon` | bundle-relative path ✅ | `reference/ui-manifest.md` |
| `dev` block | harness-only (`fixtures`, `mocks`, `seed_storage`, `user_id`); stripped by `anna-app publish` ✅ | `apps/local-dev.md` |
| CSP base | `default-src 'none'; script-src 'self' <sdk-origin>; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'` ✅ | `apps/app-ui-manifest.md` §csp_overrides |

**`csp_overrides` accepts only** `connect-src`, `img-src`, `media-src`, `font-src`,
`style-src` (`'self'`/hash/nonce only), `script-src` (`'self'`/`'wasm-unsafe-eval'`/hash/nonce only). ✅

> **Inline scripts are blocked.** `script-src` has no `'unsafe-inline'`, so
> `index.html` may only load external modules. Inline **styles** are allowed
> (`style-src 'unsafe-inline'`), but we don't use them.

### Decision — `bundled:<handle>` instead of a CHANGEME placeholder

`docs.md §1` originally planned a `tool-CHANGEME-…` placeholder rewritten by
`scripts/set-tool-id.py`. The reference app now uses a better mechanism:

- `manifest.json` references `bundled:receipts-engine`;
- `app.json.bundled_executas` maps the handle → `./executas/receipts-engine`;
- `anna-app apps publish` publishes the executa, substitutes the minted id into
  the manifest **in memory**, and writes `bundle/anna-tool-ids.js` setting
  `window.__ANNA_TOOL_IDS__ = { "receipts-engine": "<minted-id>" }`.

The UI reads that global with a dev fallback (`ui/src/lib/ids.ts`).
`scripts/set-tool-id.py` is kept for the manual path (pin a minted id into
`executa.json` + `pyproject.toml`) and for `status` verification.

---

## 2. Executa (plugin) protocol

Source: `reference/executa-protocol.md`, `reference/executa-lifecycle.md`,
`reference/executa-pitfalls.md`.

| Fact | Value |
|---|---|
| Transport | JSON-RPC 2.0 over stdio, one LF-delimited UTF-8 JSON object per line ✅ |
| `MAX_STDIO_MESSAGE_BYTES` | **512 KiB** soft cap per message; larger responses must use file transport ✅ |
| `MAX_READLINE_BYTES` | **2 MiB** hard cap on the host's reader — a longer line is a protocol violation ✅ |
| stdout | protocol only. One stray `print()` kills the plugin ✅ |
| `describe` result | the **bare** manifest dict (not wrapped) ✅ |
| `invoke` result | `{"success": true, "data": …, "tool": …}` — `success` defaults to `false` in the parser ✅ |
| Unknown method | must return `-32601` (the v1/v2 fallback depends on it) ✅ |
| Never `exit()` | main loop reads stdin until EOF ✅ |
| `initialize` | host sends `{protocolVersion: "2.0", host_capabilities: {...}}`; plugin echoes `protocolVersion` and advertises `client_capabilities: {sampling: {}}` 🧪 |
| Timeouts | initialize 5 s · describe 5 s · health 3 s · invoke 60 s default (override per tool via `tools[].timeout`) ✅ |
| Tool params | `parameters: [{name, type, description, required, default?, enum?, items?}]` — **not** MCP `input_schema` ✅ |
| `params.invoke_id` | per-invoke correlation id; must be echoed on every reverse RPC ✅ |
| `params.context.deadline_ms` | absolute epoch-ms deadline, when the host supplies one ✅ |

### Identity

`executa-pitfalls.md` says the minted `tool_id`, the `name` returned by
`describe`, and the archive's `manifest.json.name` must be **identical strings**.
The focus-flow example drops `name` from `MANIFEST` instead. ⚠️
**Decision:** the plugin reads `executa.json` next to the package and returns its
`tool_id` as `MANIFEST["name"]`. Both readings are satisfied and there is one
source of truth on disk.

---

## 3. Sampling (reverse RPC) — `sampling/createMessage`

Sources: `reference/executa-sampling.md` ✅ and `sdk/python/executa_sdk/sampling.py` 🧪
(the SDK is **ahead of the prose docs**).

Wire params (camelCase):

```jsonc
{ "jsonrpc": "2.0", "id": "<uuid-hex>", "method": "sampling/createMessage",
  "params": {
    "messages": [{"role": "user", "content": {"type": "text", "text": "…"}}],
    "maxTokens": 2048,
    "systemPrompt": "…",
    "temperature": 0.1,
    "includeContext": "none",          // only value supported in v1
    "responseFormat": {                 // ⬅ structured output DOES exist
      "type": "json_schema",
      "json_schema": { "name": "match_result", "strict": true, "schema": { … } }
    },
    "onUnsupported": "json_object",     // downgrade instead of failing with -32010
    "_clientTimeoutS": 60.0,
    "context": { "invoke_id": "<parent invoke id>" }
  } }
```

| Fact | Value |
|---|---|
| Pre-requisites | v2 negotiated + plugin manifest `host_capabilities: ["llm.sample"]` + user `sampling_grant` ✅ |
| `maxTokens` per call | ≤ **8 192** ✅ |
| Calls per `invoke_id` | ≤ **8** ✅ |
| Cumulative tokens per `invoke_id` | ≤ **32 000** — the cap is *per invoke*, not per call ✅ |
| `temperature` | host substitutes **0.7** when `None` → always pass it explicitly ✅ |
| `responseFormat` | L1 `{"type":"json_object"}` or L2 `json_schema` (`strict: true`) 🧪 |
| Schema limits | ≤ 32 KB serialized, depth ≤ 8, ≤ 512 nodes, name `^[a-zA-Z0-9_-]{1,64}$` 🧪 |
| Result shape | `{content: {type: "text", text: "…"}, model, usage, _meta: {responseFormat: {structuredValid, downgraded}}}` 🧪 |
| Output is **always a string** | the host never parses for you — parse + validate yourself 🧪 |
| Errors | `-32001` not_granted · `-32002` quota · `-32003` provider · `-32004` invalid · `-32005` timeout · `-32006` max_calls · `-32007` max_tokens · `-32008` not_negotiated · `-32009` user_denied · `-32010` unsupported_response_format ✅🧪 |

**Decision — no `executa-sdk` dependency.** The helper package used by the
examples (`executa-sdk`) is **not published on PyPI** (404) and the examples
resolve it through a relative `[tool.uv.sources]` path. We implement the three
frames we need (`initialize` handshake, `sampling/createMessage`,
`executa/progress`) in `receipts_engine/host/`, ~200 dependency-free lines that
mirror the verified wire format. This keeps the dependency list inside the
`CLAUDE.md` allow-list.

---

## 4. Progress — `executa/progress`

Source: `sdk/python/executa_sdk/progress.py` 🧪 + `apps/app-ui-host-api.md` ✅

A JSON-RPC **notification** (no `id`, host never replies):

```json
{"jsonrpc":"2.0","method":"executa/progress",
 "params":{"type":"tool_update","data":{…},"context":{"invoke_id":"<parent>"}}}
```

- `type` must be `"progress"` or `"tool_update"`; anything else is coerced.
- Without the parent `invoke_id` in `params.context` the event is **silently dropped**.
- Rate limit **50 events/s per invoke**; `data` ≤ **8 KB**; latest 500 kept.
- Progress only flows for **async** invokes (`tools.invokeAsync`). During a plain
  `tools.invoke` the notifications are dropped — the tool still works.

---

## 5. Host API from the bundle (iframe)

SDK: ES module at `/static/anna-apps/_sdk/latest/index.js`, `AnnaAppRuntime.connect()`. ✅
Responses are `{ok: true, result}` / `{ok: false, error: {code, message, details?}}`;
some namespaces resolve the payload directly. ⚠️ **Decision:** `lib/anna.ts`
unwraps defensively (`"ok" in r ? r.result : r`).

### `tools.*` ✅ (`reference/host-api-tools.md`)

| Method | Signature | Notes |
|---|---|---|
| `list` | `() => {tools: [{tool_id, status?}]}` | pure ACL projection, safe at boot |
| `invoke` | `({tool_id, method?, args?, timeoutMs?}) => payload` | `timeoutMs` clamped **1 s – 90 s**, default 65 s |
| `invokeAsync` | `({tool_id, method?, args?, timeoutMs?, clientTag?}) => {jobId, state, deadlineMs}` | **args cap 64 KB**; `timeoutMs` = job deadline, clamped 60 s – 24 h |
| `invokeAsyncAwait` | `(args, {onProgress, signal}) => payload` | SDK sugar: events + polling + abort |
| `getJob` | `({jobId, sinceSeq?, limit?}) => JobSnapshot` | authoritative; `jobId` `^tjob_[0-9a-f]{32}$` |
| `cancelJob` | `({jobId, reason?})` | cooperative, idempotent |
| `listJobs` | `({tool_id?, state?, clientTag?, since?, limit?})` | reload-recovery entry point |

Other limits: **5 active jobs per user** (`job_quota_exceeded`), 3 long jobs per
agent (`long_job_capacity`), **result cap 256 KB**.
`method` is **required** for mint-only tool ids (no `.`/`__` separator).

### `storage.*` ✅ (`apps/app-ui-host-api.md`)

`get({key})` · `set({key, value, if_match?, ttl_seconds?})` ·
`delete({key, if_match?})` · `list({prefix?, cursor?, limit?})`.
In production the handlers are APS-backed at `scope='app', owner=app_id`
(durable); in the local harness they operate on the window's 256 KB
`runtime_state`. A schema-3 `storage.kv` declaration makes this explicit.
`state_too_large` if a write would exceed 256 KB.

### `files.*` ✅ (`reference/host-api-files.md`)

Two-phase upload only — there is no `files.put(bytes)`:
`upload_init({path, content_type, size, ttl_seconds?, metadata?, if_match?})`
→ browser `PUT` to `put_url` with the **exact** `Content-Type` → `upload_finalize({path, etag?, size?})`.
`download({path, filename?})` is the **host-mediated save** — the host page clicks
a top-level anchor, so it works regardless of iframe sandbox tokens and the
presigned URL never enters app DOM. The iframe files surface always runs at
`scope=app, owner=window.app_id`.

### `web.*` ✅ (`reference/host-api-web.md`)

`fetch({urls (1–10), format?, max_chars?, timeout_ms?})` →
`{pages: [{url, final_url?, ok, title?, content?, truncated?, error?}]}` — same
length and order as the input, **per-item failure isolation**.
Gated by `ui.host_api.web` **and** the per-app `web_grant`, which is
**disabled by default**: the first call returns `APP_NOT_GRANTED`, which the app
should treat as "show the consent hint, offer paste instead".

### `window.*` ✅ — always granted; `set_title`, `resize`, `focus`, `close`, `open_view`, `report_error`.

### `chat.*` ⚠️ — `append_artifact` is implemented; `write_message` and
`read_history` are **stubs** (`not_implemented`). **Decision:** Receipts does not
call `chat.*` at all. The `#receipts` flow works through the Skill + the LLM's
`open_app_view` tool, which needs no `chat` grant.

---

## 6. Moving bytes between the iframe and the plugin

This is the one place where the platform has **no** direct channel, so it needed
a decision.

| Constraint | Consequence |
|---|---|
| `tools.invokeAsync` args cap 64 KB ✅ | a base64 PDF cannot ride an async invoke |
| Host reader `MAX_READLINE_BYTES` 2 MiB ✅ | a 2 MB PDF (2.7 MB base64) exceeds the stdio line limit even on a sync invoke |
| Plugin `storage_token` permits scopes `user` + `tool` only ✅ | the plugin cannot read the `scope=app` objects the iframe writes with `files.*` |
| iframe `files.*` is always `scope=app` ✅ | the reverse is also true |

**Decision — chunked upload over sync `tools.invoke`.**
The UI slices the file into **128 KiB base64 chunks** and calls
`engine(action="upload_chunk", upload_id, index, total, data_b64)` in sequence.
Each JSON-RPC line stays ≈ 130 KB — comfortably under the 512 KiB soft cap and
far under the 2 MiB hard cap. The engine buffers chunks **in memory only**
(never on disk — CV content must not be persisted outside the user's storage),
with a 10-minute TTL and a 2 MB hard ceiling that raises `file_too_large`.
`parse_cv` then references the `upload_id`. A typical 250 KB CV is 3 chunks.

**Decision — DOCX export returns bytes, not a file ref.**
`docs.md §3` planned `export_docx → {file_ref}` via plugin-side host upload. The
plugin cannot write to the app scope the iframe can read, so instead
`export_docx` returns `{filename, content_b64, mime}` (a 30–60 KB DOCX ≈ 80 KB
base64, well under the 512 KiB response cap). The UI writes it with
`files.upload_init` → `PUT` → `files.upload_finalize`, then calls `files.download`
to open the browser's save dialog.

---

## 7. Local harness

| Fact | Value |
|---|---|
| Discovery | `executas/<name>/`: `executa.json` (needs **both** `tool_id` and `type`) > `pyproject.toml` > `package.json` > `go.mod`+`executa.json` > `bin/<name>` ✅ |
| Python spawn | `uv run --project <dir> <tool_id>` — so `[project.scripts]` **must** contain a key equal to the `tool_id` ✅ |
| `app.json.bundled_executas` | an **object keyed by handle**, never an array ✅ |
| Storage backend | `--storage legacy` (in-memory, default) or `--storage aps` (real APS, needs `anna-app login`) ✅ |
| LLM | real by default (needs `anna-app login`); `--no-llm` → `llm_disabled`; `--mock-llm <fixture>` ✅ |
| Async jobs | full lifecycle implemented in-process; not persisted across harness restarts ✅ |
| Validate | `anna-app validate --strict` greps the bundle for `anna.<ns>.<method>` and asserts each is allow-listed ✅ |

`--strict` lexically strips string literals and comments first, so a diagnostic
string mentioning a method is not treated as a call.

---

## 8. Mobile review checklist (hard requirements once `"mobile"` is declared) ✅

Source: `apps/app-mobile.md`.

- Usable at **≥ 320 px** with no horizontal scrolling and no clipped controls.
- Safe areas: use `env(safe-area-inset-*)` **or** the shell-injected
  `--anna-safe-area-*` variables (both are `0` on desktop, so always safe).
- Touch targets **≥ 44 × 44 pt**.
- No hover-only interactions.
- No dependence on multi-window or window geometry.
- **Do not ship your own `<meta name="viewport">`** — the mobile shell injects it.
  Reviewers grep the bundle HTML for it.

---

## 9. Still unverified (needs a real account)

These could not be checked without a developer account and are the only open
items from `phases.md` Phase 0:

- [ ] Exact minted `tool_id` / `skill_id` strings.
- [ ] Whether the `receipts` slug is free.
- [ ] Real cost in credits of one `run_match` (measure with `anna-app dev --llm`).
- [ ] `sampling_grant` / `web_grant` defaults on a fresh install as the reviewer
      sees them.
- [ ] Whether `anna-app apps publish` rewrites `bundled:` refs for the **Skill**
      handle the same way it does for tools (the docs only show the tool case).
