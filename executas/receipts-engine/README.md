# receipts-engine

The Executa plugin behind [Receipts](../../README.md): a JSON-RPC 2.0 process
on stdio that parses a CV, extracts a posting's requirements, matches them, and
refuses to write anything the CV cannot prove.

One tool method, `engine`, with an `action` discriminator — one Executa row per
app, rather than a new catalogue entry every time the product grows a verb.

```
action           LLM   what it does
───────────────  ────  ───────────────────────────────────────────────────────
health            –    liveness, and whether sampling is negotiated
upload_chunk      –    one 128 KiB base64 slice of a CV file
parse_cv          –    PDF / DOCX / text → numbered lines with stable ids
run_match         2    the primary function; async, with progress events
tailor           1–2   rewrite bullets, verify, repair once, drop
letter           1–2   cover letter, same loop, per paragraph
export_docx       –    render the accepted output; returns base64
```

## Layout

| Path | What it is |
|---|---|
| `plugin.py` | The stdio loop and the action dispatcher. Read this first. |
| `host/` | The Anna wire protocol: frames, invoke context, progress, sampling. Dependency-free. |
| `parse/` | CV → `CVDoc`, posting → trimmed text. No model involved. |
| `llm/` | Schema generation, the one typed call, JSON extraction, retry. |
| `pipeline/` | extract → match → guard → summarize, plus tailor and letter. |
| `verify/` | The grounding verifier and the technology lexicon. |
| `export/` | DOCX generation. |
| `prompts/` | Versioned prompt files. A change here means rerunning the eval. |

## Working on it

```bash
uv sync --extra dev
uv run pytest ../../tests -q          # 187 tests
uv run ruff check .
uv run mypy receipts_engine
```

Drive it by hand the way the Agent does:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"describe"}' | uv run python -m receipts_engine.plugin
```

From the repository root, `anna-app dev` spawns this plugin as
`uv run --project . tool-dev-receipts-engine` and proxies the real dispatcher to
it — so `pnpm exec anna-app dev` is the fastest way to exercise the whole thing.

## Three rules that break an Executa

1. **stdout is protocol-only.** Logs go to stderr, through
   `host.frames.log`. One stray `print` and the plugin stops being useful.
2. **Never exit after a response.** The reader loop runs until stdin closes,
   because the host's replies to *our* reverse RPCs arrive on the same pipe.
3. **`describe` returns the bare manifest; `invoke` returns
   `{"success": true, "data": …}`.** The host's parser defaults `success` to
   `false`, so omitting it fails the call silently.

Full protocol notes, with the limits that shaped this design, are in
[`docs/api-notes.md`](../../docs/api-notes.md).
