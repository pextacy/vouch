# CLAUDE.md — Receipts

Project instructions for Claude Code (and other coding agents). Read at the start of every session.

## Project summary
Receipts is an Anna App for the Anna AI OS Marketplace. The user pastes a job posting; the app extracts its requirements, matches each one to evidence in the user's saved CV lines, then generates tailored CV bullets and a cover letter **grounded only in facts the CV contains**. The product's differentiator and promise: **"Invent nothing."** The name comes from "show me the receipts" — every claim comes with proof.

Goal: earn monthly grants in the Anna Founding Builder Program through Qualified App MAU (500+ in October, 1,000+ in November).

## Read first
| File | When |
|---|---|
| `prd.md` | Feature scope, acceptance criteria, metrics |
| `plan.md` | Architecture, repo layout, test strategy, timeline, growth |
| `docs.md` | Tool contract, schemas, prompts, verifier, design system, screen copy |
| `phases.md` | Current phase and tasks; check items off when done |
| `docs/api-notes.md` | Verified Anna host API signatures (created in Phase 0) |

## Anna platform knowledge — source hierarchy
1. `docs/api-notes.md` (verified in this project)
2. `https://anna.partners/llms.txt` → append `.md` to any `/developers/**` page for raw Markdown
3. `github.com/whtcjdtc2007/anna-executa-examples` → `examples/anna-app-focus-flow` (reference app)
4. General training knowledge — **do not trust it for Anna.** The APIs change quickly.

Never write a host API call by guessing its signature. Read the docs, record it in `api-notes.md`, then code.

## Known platform facts (verified in Phase 0 — `docs/api-notes.md` is authoritative)
- `tool_id`s are **minted** server-side; never invent them. The manifest
  references `bundled:receipts-engine` and the publish flow substitutes the
  minted id, writing `bundle/anna-tool-ids.js` for the UI. Local dev runs on
  `tool-dev-receipts-engine`.
- The dev id must be **identical** in three places: `executas/receipts-engine/executa.json`,
  `pyproject.toml` (name + `[project.scripts]` key), `ui/src/lib/ids.ts`.
  `python scripts/set-tool-id.py status` checks it.
- Bundle call shape: `anna.tools.invoke({ tool_id, method: "engine", args: { action, ... } })`. Runtime ACL is enforced by `manifest.ui.host_api`; `permissions[]` is display/audit only but has a restricted vocabulary.
- The SDK loads as an external ES module; **CSP blocks inline scripts.** No inline `<script>` or `style` attributes in `index.html`.
- `AnnaAppRuntime.connect()` throws outside the iframe → fall back to stub mode and show `PreviewBanner`.
- `tools.invoke` is capped at 90 s → `run_match`, `tailor`, `letter` run as async jobs; the plugin sends `executa/progress`.
- **The host strips the `{success, data}` envelope.** A successful invoke
  resolves with the payload directly; a failed one rejects as `tool_failed`
  keeping only `result.error`. So the plugin puts the bare error **code** there
  and the UI supplies the sentence.
- **No direct byte channel** between the iframe and the plugin: async args cap
  at 64 KB and the stdio reader at 2 MiB. CV files arrive as 128 KiB base64
  chunks over the sync channel; `export_docx` returns base64 back.
- Sampling structured output is `responseFormat` on the wire, with
  `onUnsupported: "json_object"`. Caps are **per invoke**: 8 calls, 32k tokens.
- Plugin stdout is **JSON-RPC only**. Logs go to stderr. A single stray `print` to stdout breaks the protocol.
- APS `storage` holds all user state. The engine writes **nothing** to disk — CV bytes live in memory for the length of one parse and are then dropped.
- After editing the plugin: `uv tool install . --reinstall --no-cache`.
- A failed or empty run never returns success (critical for MAU counting and review).

## Architecture boundaries
- `ui/` is source. `bundle/` is build output — **never edit by hand**.
- Business logic and LLM calls live in the **engine** (Python). The UI handles presentation, state and host API calls only.
- LLM access only through reverse sampling. **No** API keys, `.env` files or external HTTP services.
- Before adding any npm/pip dependency, record the justification in `plan.md`. Allowed UI deps: `preact`, `@preact/signals`, `@anna-ai/app-runtime`. Allowed Python: `pydantic`, `pypdf`, `python-docx`, `rapidfuzz`, (dev) `pytest`, `anna-executa-test`, `ruff`, `mypy`. Dev-only tooling added since: `playwright-core` (screenshots) and `fonttools[woff]` (font subsetting, run by hand) — both justified in `plan.md §6`.

## Non-negotiable product rules
1. **Invent nothing.** Tailor and letter output never reaches the UI without passing `verify/grounding.py`. Never delete or skip tests to loosen the verifier. For a false positive: add a test, narrow the rule.
2. CV lines go to the LLM as `L<n>: text`; the LLM returns ids; the engine validates ids.
3. All LLM output is validated with Pydantic schemas (`extra="forbid"`); schemas are generated from models.
4. Prompt files are versioned (`*.v1.md`). Prompt change → run `scripts/eval_match.py` and put results in the PR description.
5. CV content is never logged and never stored outside storage.
6. Example/demo mode never calls the LLM.

## Frontend rules — must not look vibe-coded
Design system is `docs.md §8`. Summary and prohibitions:
- No colors, spacing or font sizes outside the tokens. Colors: `--paper --sheet --ink --graphite --rule --marker --pencil --tab`.
- Typefaces: UI = Schibsted Grotesk; document surfaces = Source Serif 4. No other fonts, no monospace.
- **The single bold element is the highlighter mark** (`--marker`). Yellow appears nowhere else.
- FORBIDDEN: Tailwind, shadcn, off-the-shelf icon libraries, gradients, glassmorphism, neon glow, emoji icons, circular score gauges, red/green traffic-light badges, grids of identical shadowed cards, ALL-CAPS eyebrow labels, `A · B · C` meta strings, `→` in buttons, single-word emphasis in headings, fade-slide-up entrances on every section, receipt clip-art / zigzag paper edges / dot-matrix fonts, marketing words like "Unlock / Supercharge / Seamless / magic".
- Radius hierarchy: sheet 2px, input 6px, button 8px, tab 10px.
- Shadow only on `DocumentSheet`.
- Status is expressed by color + shape + text (strong = full mark + "Evidenced", partial = underline + "Related", missing = brackets + "No evidence yet").
- Copy is sentence case and active voice; buttons say exactly what they do; errors don't apologize and give the fix. Copy comes from `docs.md §9` — don't make it up.
- After every UI change: take screenshots at 360 px and 1280 px and check them against the Phase 2 anti-vibe-code audit in `phases.md`.
- Accessibility: visible focus (`2px solid var(--pencil)`), full keyboard support, `prefers-reduced-motion`, AA contrast.

## Code style
- TypeScript `strict`, `noUncheckedIndexedAccess`. No `any`. One component per file, named exports.
- CSS: `.css` next to each component, class names `block__elem--mod`; keep selector specificity low, no `!important`.
- Python 3.12, type hints required, `ruff` + `mypy --strict` (engine package).
- Error objects everywhere are `{ code, message, retriable }`; codes from the `docs.md §3` table.
- Comments explain "why", not "what".

## Commands
```bash
pnpm install
pnpm build                        # ui → bundle
pnpm --dir ui dev                 # UI in stub mode
anna-app dev                      # harness http://localhost:5180
anna-app dev --llm                # real sampling
anna-app validate --strict        # before every commit
cd executas/receipts-engine && uv sync --extra dev && uv run pytest ../../tests -q
uv run ruff check . && uv run mypy receipts_engine
python scripts/eval_match.py fixtures/golden
```

## How to work
- Before starting a task, check the current phase in `phases.md`; don't do out-of-phase work.
- Small testable steps: test first (especially `verify/` and `parse/`), then code.
- A task is finished when tests are green, `anna-app validate --strict` is clean, and the `phases.md` box is checked.
- When uncertain: follow a decision in `docs.md` if one exists; otherwise implement the simplest safe option and add a "Decision:" note to `docs.md`.
- If docs and code diverge, don't move on silently; update one of them.
- Runs from developer/test accounts don't count toward MAU, and bulk automated runs can be flagged as cheating; load-test only in the local harness.

## Definition of Done
- [ ] Acceptance criteria match `prd.md`
- [ ] Unit + contract tests green; eval thresholds met (if engine changed)
- [ ] Empty, loading and error states implemented
- [ ] EN + TR strings added
- [ ] 360 px and desktop screenshots reviewed; anti-vibe-code audit clean
- [ ] `anna-app validate --strict` clean
- [ ] Related docs updated
