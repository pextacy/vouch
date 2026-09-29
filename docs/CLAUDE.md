# CLAUDE.md — Receipts

Project instructions for Claude Code (and other coding agents). Read at the start of every session.

## Project summary
Receipts is an Anna App for the Anna AI OS Marketplace. The user pastes a job posting; the app extracts its requirements, matches each one to evidence in the user's saved CV lines, then generates tailored CV bullets and a cover letter **grounded only in facts the CV contains**. The product's differentiator and promise: **"Invent nothing."** The name comes from "show me the receipts" — every claim comes with proof.

Goal: earn monthly grants in the Anna Founding Builder Program through Qualified App MAU (500+ in October, 1,000+ in November).

## Read first
All of them live in `docs/`, beside this file.

| File | When |
|---|---|
| `prd.md` | Feature scope, acceptance criteria, metrics |
| `plan.md` | Architecture, repo layout, test strategy, growth |
| `docs.md` | Tool contract, schemas, prompts, verifier, design system, screen copy |
| `privacy.md` | The public privacy page behind `app.json.privacy_url` — any change to what is stored, sent or deleted must update it |

## Anna platform knowledge — source hierarchy
1. The facts recorded below, and the comments beside each call in the code
2. `https://anna.partners/llms.txt` → append `.md` to any `/developers/**` page for raw Markdown
3. `github.com/whtcjdtc2007/anna-executa-examples` → `examples/anna-app-focus-flow` (reference app)
4. General training knowledge — **do not trust it for Anna.** The APIs change quickly.

Never write a host API call by guessing its signature. Read the docs first, then code, and record what you verified in a comment where the call is made.

## Known platform facts (verified against the live host docs)
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
- `tools.invoke` is capped at 90 s → `run_match`, `tailor`, `letter` and `gaps` run as async jobs; the plugin sends `executa/progress`.
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
- Sampling replies arrive on the same pipe as invokes: the **reader thread**
  dispatches them itself, never the invoke pool, or parked workers deadlock.
- A response over the 512 KiB stdio cap is answered with `-32603`. Never spill
  a body to a temp file — it would be CV-derived text on disk (rule 5).
- APS `storage` holds all user state. The engine writes **nothing** to disk — CV bytes live in memory for the length of one parse and are then dropped.
- After editing the plugin: `uv tool install . --reinstall --no-cache`.
- A failed or empty run never returns success (critical for MAU counting and review).
- A transient sampling failure (provider error, timeout) is retried once inside
  the per-invoke budget; a quota or grant failure is not, because the next
  attempt fails the same way and spends what the user has left.
- **The docs do not say whether one plugin process serves one user.** They say
  the Agent owns "a single, long-running process" and that the binary "lives
  wherever the user installed it", which reads as per-user but is nowhere
  stated. So nothing in the engine may *depend* on it: an upload is named by an
  unguessable id and that id is the only thing that entitles a caller to those
  bytes (`crypto.randomUUID`, never `Math.random`), and a cleanup path drops
  the upload it names rather than every buffer. `forget` is the user's own
  "delete all my data" and stays a hammer.
- **Rate limits are ours, not the host's** (`limits.py`). The host meters
  credits; these keep a runaway client from reaching the meter on the user's
  bill. Three buckets — model 6 burst / 1 per 20 s, parse 8 / 1 per 5 s, upload
  80 / 4 per s — plus a 16-invoke in-flight cap, because the pool's queue is
  unbounded. `RECEIPTS_RATE_LIMIT=off` for harnesses only: `eval_match.py` and
  the plugin contract suite set it, because twelve cases back to back is the
  shape the limiter exists to refuse.

## Architecture boundaries
- `ui/` is source. `bundle/` is build output — **never edit by hand**.
- Business logic and LLM calls live in the **engine** (Python). The UI handles presentation, state and host API calls only.
- LLM access only through reverse sampling. **No** API keys, `.env` files or external HTTP services.
- Before adding any npm/pip dependency, record the justification in `plan.md`. Allowed UI deps: `preact`, `@preact/signals`, `@anna-ai/app-runtime`. Allowed Python: `pydantic`, `pypdf`, `python-docx`, `rapidfuzz`, (dev) `pytest`, `anna-executa-test`, `ruff`, `mypy`. Dev-only tooling: `playwright-core` (screenshots, the accessibility audit and the type-system audit) and `fonttools[woff]` (font subsetting, run by hand) — both justified in `plan.md §6`.

## Non-negotiable product rules
1. **Invent nothing.** Tailor and letter output never reaches the UI without passing `verify/grounding.py`, and since v1.3 the **verdict** is guarded too: a `strong` whose requirement names a technology must cite a line that contains it, or the citation is repaired from elsewhere in the CV, or the verdict falls to `partial` (`pipeline/match.py`, `docs.md §6`). Keep that rule narrow — only `strong`, only technologies, never titles or durations — because a false downgrade costs more than the leak it prevents. Never delete or skip tests to loosen the verifier. For a false positive: add a test, narrow the rule. Any rule whose shape is "allowed unless we recognise it" is a leak waiting for the next product name — the posting-vocabulary rule was one, and `verify/concepts.py` inverted it (`docs.md §6`).
2. CV lines go to the LLM as `L<n>: text`; the LLM returns ids; the engine validates ids.
   The posting's own wording is the one thing that may lend a *concept* to
   generated text (`verify/concepts.py`) — and `profile` is the case with no
   posting at all, so it passes no `posting_vocab` and every term in it has to
   come from a CV line. A generated surface with nothing behind it gets the
   strictest rule, not the loosest.
3. All LLM output is validated with Pydantic schemas (`extra="forbid"`); schemas are generated from models.
4. Prompt files are versioned (`*.v1.md`). Prompt change → run
   `pnpm eval:adversarial` (offline, gates leakage) and, when a host is
   reachable, `pnpm eval -- --sampling-cmd <cmd>` for the quality numbers.
   Put both tables in the PR description.
5. CV content is never logged and never stored outside storage.
6. Example/demo mode never calls the LLM.
7. What the user edits by hand is theirs, but the document never claims it was
   checked: `export_docx` re-verifies every accepted line against the CV and the
   footer only makes the "traceable to your CV" claim when nothing failed.
   `export_cv` makes no claim at all and has no verifier step, because it
   composes nothing: every paragraph in it is a stored `CVLine.text`, byte for
   byte. If that ever stops being true, it needs a verifier like everything
   else that writes.
8. **A gap is closed by asking, never by writing.** The same holds for an
   audit finding, for a sentence `check_document` flagged in a document the app
   did not write, and for a form question `answer_question` could not answer: the engine says what the CV cannot back up, the user says
   where it happened, and their sentence — not a generated one — becomes the
   line. Every path goes through one primitive (`state.appendAnswer`), so they
   cannot drift apart. `check_document` also holds the one piece of text the
   user never agreed to store: it is read once and written nowhere, which is
   rule 5 applied to a document the app did not ask for. `gaps` returns questions;
   the answer is the user's sentence, stored verbatim as a CV line marked
   `added_at`, and nothing generated ever becomes evidence. The question is
   verified against the CV **plus its requirement's text** (it is about the
   requirement, not the candidate); the optional `angle` is a claim and gets
   the ordinary strict rule, dropped rather than softened (`docs.md §3`).
9. **Some questions have no answer in a CV, and the app writes nothing.**
   `answer_question` returns `not_about_you` for a question about what the
   candidate wants — why this company, what excites them — because a CV records
   what someone did and holds no evidence of wanting anything. That refusal is
   enforced in `pipeline/answer.py`, not requested of the model: prose arriving
   under that kind is discarded unread, and an "answered" whose every sentence
   failed verification is downgraded rather than reported as thin. The form's
   questions are never a source; only the CV is, plus the open application's
   requirements for general concepts, the same rule the letter uses.
10. **A correction is the user's, and it never becomes a verdict.**
    `assertEvidence` writes to `StoredMatch.assertions`, beside the match —
    never into `match.evidence`. That is what keeps the summary counts the
    app's own claim, keeps the cross-application screens counting what the
    market could see, and keeps `tailor` and `letter` building from evidence
    the verifier produced. The interview brief is the only reader, where it
    surfaces as `self_asserted`. Only the constructive direction is offered:
    the app missing something the CV shows, never the app being talked out of
    something it found.
11. **The engine finds, the UI phrases.** `CvFinding` carries a `kind` and two
   bare terms, never a sentence, the same split error codes use — an engine
   that worded the accusation would be shipping untranslated copy. Render
   `surface` (the CV's own spelling), never `subject` (the canonical term the
   engine compared with). `BriefItem.risk` is the same contract for the
   interview brief: the engine names the *shape* of the evidence
   (`listed_not_shown`, `self_added`, …) and the UI supplies the sentence.

10. **A citation only counts against the document it was made for.** A line
    id is a position, not a sentence: `L12` in a re-parsed CV is a different
    line, so any screen that reads citations across applications has to check
    the CV first. `lib/cv.markEdited` suffixes the hash (`~e3`) when a line is
    added or fixed, so the hash *base* is the parsed document — matching bases
    are counted, the rest are dropped **and reported** (`LedgerResult.skipped`,
    `ledger.base_hash`). Never silently narrow a denominator: a smaller sample
    nobody mentioned is how a true count becomes a false statement.

11. **Credit is a claim, and it needs a receipt like any other.** The app may
    say the user's own sentence caused a result only where it can point at
    that sentence: `RunChange.credited` is set on a gain whose newer run cites
    a line written after the older run, and the UI withdraws it if that line
    has since left the CV (`lib/rerun.renderable`). Everything else that
    improved is reported without an explanation, because "you did this"
    is exactly as much a fabrication as an invented metric when nothing in
    the record shows it. The same rule governs the softer words: a lexicon hit
    between a new CV line and a requirement is reported as *naming* the thing
    (`since_applied`), never as proving it — proving is what `run_match` and
    the verifier are for.

## Frontend rules — must not look vibe-coded
Design system is `docs.md §8`. Summary and prohibitions:
- No colors, spacing or font sizes outside the tokens. The one exception is
  `lib/share.ts`, the card built to leave the account: a downloaded SVG cannot
  resolve a custom property, so it carries the §8.2 values as named literals
  (`docs.md §8.9`). Nothing else may. Colors: `--paper --sheet --ink --graphite --rule --marker --pencil --on-pencil --tab`. Text on `--pencil` uses `--on-pencil`, never a literal white: the dark theme's pencil is pale and white reads at 2.3:1 on it.
- Typefaces: UI = Schibsted Grotesk; document surfaces = Source Serif 4. No other fonts, no monospace.
- **The single bold element is the highlighter mark** (`--marker`). Yellow appears nowhere else — and the mark is a mark *over text*, never a border, a background or a row bullet (`docs.md §8.5`).
- **Button weight is meaning, not decoration.** `button` = the screen's one action; `--secondary` = its peers; `--quiet` = a row action or a utility; `--danger` = the irreversible one (ink outline, filling on hover) and every `ConfirmDialog` confirm. No red: the palette does not have one (`docs.md §8.5`).
- **Tracking follows the size and leading follows the family.** A heading rule that drops below 23 px resets `--track`; a rule that sets `font-family` sets `line-height` with it. `pnpm type` measures both on the built bundle, the way `pnpm a11y` measures contrast — neither is a matter of opinion once it is written down.
- FORBIDDEN: Tailwind, shadcn, off-the-shelf icon libraries, gradients, glassmorphism, neon glow, emoji icons, circular score gauges, red/green traffic-light badges, grids of identical shadowed cards, ALL-CAPS eyebrow labels, `A · B · C` meta strings, `→` in buttons, single-word emphasis in headings, fade-slide-up entrances on every section, receipt clip-art / zigzag paper edges / dot-matrix fonts, marketing words like "Unlock / Supercharge / Seamless / magic".
- Radius hierarchy: sheet 2px, input 6px, button 8px, tab 10px.
- Shadow only on `DocumentSheet`.
- Status is expressed by color + shape + text (strong = full mark + "Evidenced", partial = underline + "Related", missing = brackets + "No evidence yet").
- Copy is sentence case and active voice; buttons say exactly what they do; errors don't apologize and give the fix. Copy comes from `docs.md §9` — don't make it up.
- After every UI change: run `pnpm a11y` (contrast, focus, tap targets,
  headings) and `pnpm type` (scale, family, weight, tracking, leading,
  measure) — both read the computed styles off the built bundle and both fail
  on a violation — then take screenshots at 360 px and 1280 px and look at
  them against the prohibitions above. The two audits measure what can be
  measured so the looking can be spent on what cannot.
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
pnpm check                        # typecheck · bundle tests · engine tests · validate --strict
pnpm lint:engine                  # ruff + mypy --strict
pnpm a11y                         # accessibility audit over the built bundle
pnpm type                         # type-system audit over the built bundle
pnpm screenshots                  # 360 px and 1280 px (add --dark for the dark set)
pnpm eval -- --sampling-cmd <cmd> # match quality against the golden set
pnpm eval:adversarial             # leakage gate, offline — no model needed
anna-app dev                      # harness http://localhost:5180
anna-app dev --llm                # real sampling
anna-app validate --strict        # before every commit
```

## How to work
- Small testable steps: test first (especially `verify/` and `parse/`), then code.
- A task is finished when tests are green and `anna-app validate --strict` is clean.
- When uncertain: follow a decision in `docs.md` if one exists; otherwise implement the simplest safe option and add a "Decision:" note to `docs.md`.
- If docs and code diverge, don't move on silently; update one of them.
- Runs from developer/test accounts don't count toward MAU, and bulk automated runs can be flagged as cheating; load-test only in the local harness.

## Definition of Done
- [ ] Acceptance criteria match `prd.md`
- [ ] Unit + contract tests green; `pnpm eval:adversarial` passes and the
      quality thresholds are met (if the engine or a prompt changed)
- [ ] Empty, loading and error states implemented
- [ ] EN + TR strings added — and no string left in the table that nothing renders
- [ ] `pnpm a11y` and `pnpm type` clean; 360 px and desktop screenshots
      reviewed against the prohibitions above
- [ ] `pnpm check` and `pnpm lint:engine` clean
- [ ] Related docs updated — `docs/` and the root `README.md` are the only
      prose in the repository, so a change that makes a sentence there false is
      not finished
