# Receipts — Technical & Operational Plan

This document covers **how** we build and **how** we grow. For what we build see `prd.md`; for contracts, schemas and the design system see `docs.md`.

---

## 1. Architecture decisions (final)

| Decision | Choice | Rationale |
|---|---|---|
| App type | Anna App, manifest `schema: 2`, UI bundle + 1 Tool Executa + 1 Skill | Review requires "interactive UI + working backend"; mirrors the `anna-app-focus-flow` reference app. |
| Backend language | **Python 3.12**, distributed with `uv` | Mature PDF/DOCX parsing and DOCX generation; default flavour in Anna's examples. |
| LLM access | **Reverse sampling** from the Executa (`sampling/createMessage`) with `responseFormat: json_schema` and `onUnsupported: "json_object"` | No API keys; billing and model selection handled by Anna; BYOK users count automatically. The host returns a string either way, so the engine parses and validates it itself. |
| Long-running work | `tools.invokeAsync` from the bundle + `emit_progress` from the plugin | Synchronous `tools.invoke` is capped at 90 s; progress events drive the highlighter animation. |
| Frontend | **Vite + Preact + TypeScript + plain CSS with tokens** | Small bundle, CSP-friendly external ES module; no Tailwind/shadcn — the main source of the "vibe-coded" look. |
| State | Anna `storage.*` (APS KV) | No external database; per-user isolation and quotas enforced by the host. |
| Posting URL | Host `web` API from the bundle | No external dependency; falls back to paste. |
| File output | Engine generates DOCX → host upload → bundle `files.download` | Real save dialog for the user. |
| External services | **None** | Third-party outages are not remediated by the program. |
| License | MIT (code) | Community visibility, DoraHacks BUIDL. |

> ✅ **Verified against the live platform**, not assumed: the published docs,
> the shipped `@anna-ai/app-schema` bundle and the reference example repo. Each
> call carries the signature it was written against in a comment beside it.
> Four facts changed the design: `form_factors` lives inside `ui`; the shipped
> validator caps `schema` at 2; there is no byte channel between the iframe and
> the plugin (hence chunked upload); and an inner failure reaches the UI as
> `tool_failed` with only a message, so the error code travels in that string.

## 2. System diagram

```
┌─────────────────────────── Anna UI Runtime (sandboxed iframe) ──────────────────────────┐
│  bundle/ (Preact SPA)                                                                    │
│   ├─ screens: Onboarding · AddCv · CvPreview · CvAudit · Profile · Check · NewMatch ·    │
│               Progress · MatchMap · Tailor · Letter · Gaps · Answers · Interview ·       │
│               Share · Tracker · Worth · Since · Followup · Changed · Recurring ·         │
│               Compare · Ledger · Settings                                                │
│   ├─ lib/anna.ts      → AnnaAppRuntime.connect(), typed wrappers                          │
│   ├─ lib/store.ts     → storage.get/set (master CV, matches index, match records)         │
│   └─ lib/engine.ts    → tools.invokeAsyncAwait({action:"run_match", ...}, onProgress)     │
└──────────────┬───────────────────────────────────────────────────────────────────────────┘
               │ host RPC (tools.*, storage.*, web.*, files.*)
               ▼
┌──────────────────────── Anna Host / Agent ────────────────────────┐
│  dispatcher ── ACL (manifest.ui.host_api) ── billing ── APS        │
└──────────────┬─────────────────────────────────────────────────────┘
               │ JSON-RPC 2.0 over stdio
               ▼
┌──────────────── executas/receipts-engine (Python) ─────────────────┐
│ plugin.py            describe / invoke → dispatcher(action)         │
│ parse/cv.py          PDF (pypdf) · DOCX (python-docx) · text → CVDoc│
│ parse/posting.py     text cleanup, trimming                         │
│ host/sampling.py     reverse sampling over stdio, one call per id    │
│ llm/client.py        json_schema + parse + retry, per-invoke budget  │
│ pipeline/extract.py  requirement extraction                         │
│ pipeline/match.py    evidence matching                              │
│ pipeline/tailor.py   bullet tailoring                               │
│ pipeline/letter.py   cover letter                                   │
│ pipeline/gaps.py     one question per unproven requirement          │
│ pipeline/answer.py   the application form's own questions           │
│ pipeline/followup.py the note after the silence — or the refusal    │
│ pipeline/profile.py  a headline and an About, from the CV alone     │
│ — the readers below spend no model call and no token: —             │
│ audit.py             what the CV cannot back up                     │
│ check.py             the verifier, turned on a document we did not  │
│                      write                                          │
│ interview.py         what this application must back up             │
│ recurring.py         what keeps coming up across applications       │
│ compare.py           which saved application to spend the hour on   │
│ ledger.py            which CV lines have carried an application     │
│ since.py             what the CV gained after one application went  │
│                      out                                            │
│ worth.py             the same question, asked of the whole shelf    │
│ rerun.py             what two runs of one posting say differently   │
│ verify/grounding.py  "Invent nothing" deterministic verifier        │
│ export/docx.py       DOCX out: tailored output, and the CV itself   │
└─────────────────────────────────────────────────────────────────────┘
executas/receipts-coach/SKILL.md → #receipts chat behavior
```

## 3. Repository layout

```
receipts/
├── app.json                      # listing metadata (slug, name, category)
├── manifest.json                 # AppManifest schema 2
├── package.json                  # @anna-ai/cli devDependency, scripts
├── docs/                         # the only prose in the repository
│   ├── CLAUDE.md                 # how to work in here
│   ├── prd.md                    # scope, acceptance criteria, metrics
│   ├── plan.md                   # this file
│   └── docs.md                   # tool contract, schemas, verifier, design system, copy
├── ui/                           # frontend source (Vite)
│   ├── index.html
│   ├── vite.config.ts            # outDir: ../bundle, no inline scripts
│   ├── src/
│   │   ├── main.tsx  app.tsx  router.ts  state.ts
│   │   ├── screens/  components/  lib/  i18n/{en,tr}.json
│   │   └── styles/{tokens.css, base.css, marks.css, app.css}
│   └── public/{icon.svg, fonts/*.woff2}
├── bundle/                       # BUILD OUTPUT — never edit by hand
├── executas/
│   ├── receipts-engine/
│   │   ├── executa.json  pyproject.toml
│   │   └── receipts_engine/{plugin.py, parse/, llm/, pipeline/, verify/, export/, schemas.py, prompts/}
│   └── receipts-coach/SKILL.md   # the Skill's body, loaded into the prompt
├── fixtures/                     # sample CVs/postings + recorded dev sessions (jsonl)
├── tests/
│   ├── plugin/                   # pytest + anna-executa-test
│   ├── verify/                   # verifier unit tests (most critical)
│   ├── parse/  pipeline/  engine/
│   └── ui/                       # vitest + mountBundle
├── scripts/{set-tool-id.py, eval_match.py, fabricating_sampler.py,
│           screenshots.mjs, a11y.mjs, typography.mjs, preview-flow.mjs}
└── listing/screenshots/          # store assets, regenerated by scripts/screenshots.mjs
```

## 4. Engine pipeline (run_match)

```
run_match(cv_doc, posting_text, locale)
  1. normalize   → clean posting text, trim to 3k tokens                   progress 5%
  2. extract     → LLM#1: requirements [{id,text,kind,category}]           progress 25%  (emit as they arrive)
  3. match       → LLM#2: per requirement {status, line_ids, why}          progress 70%  (emit partial results)
  4. guard       → do line_ids exist in the CV? if not, downgrade to missing progress 85%
  5. summarize   → deterministic counts + summary sentence (no LLM)        progress 95%
  6. return MatchResult                                                    progress 100%
```

- `tailor`, `letter` and `gaps` are separate actions, called only when the user asks (cost control).
- `gaps` is the one pipeline that runs *toward* the CV rather than out of it.
  It takes the requirements the match could not prove and returns a question
  for each; the user's typed answer is appended to the CV by the UI, verbatim,
  as a line marked `added_at`. The engine never writes it — the only admissible
  source for a fact about someone's career is that person. A match re-run after
  an answer is also a second Qualified App Run, which is where the retention
  argument for the feature comes from.
- Every LLM call: `temperature ≤ 0.2`, `json_schema` required, one retry on a schema failure and one on a transient host failure (provider error, timeout) inside the per-invoke budget, then a meaningful error. A quota or grant failure is never retried — the next attempt fails the same way and spends what the user has left.
- Line ids are generated deterministically from CV text; the LLM receives `L12: …` and returns ids only.
- The requirement cache stores **non-empty** extractions only. Caching the
  empty one pinned `no_requirements_found` on that posting for a month, so the
  "Run it again" the error tells the user to try was answered by the cached
  failure and never reached the model.
- **Qualified run moment:** when `run_match` successfully returns a `MatchResult`. An empty requirement list is not success → `no_requirements_found` error and the message "This text doesn't look like a job posting."

## 5. The "Invent nothing" verifier (the heart of the product)

Full algorithm in `docs.md §6`. Summary: **claims** are extracted from the
generated text — numbers *with their unit*, including ones written as words
("forty percent", "six weeks", "doubled"); dates and durations; tech and tool
lexicon matches; capitalised proper nouns; job titles — and each is looked for
in the cited CV lines. Comparison is whole-word, so "metadata" does not
evidence "Meta" and "seniority" does not evidence "Senior", while a Turkish
case suffix ("Ankarada") and a spelling-only difference ("Node.js" ↔ "node js")
still do. Any claim not found is a violation → one repair call naming the
offending words → if violations remain, the output is dropped and the user is
told why. Pure Python, no LLM, 76 unit tests.

Reproducible evidence, all of it regenerable from this repository: **76
verifier unit tests**, and `pnpm eval:adversarial` — 12/12 cases, tailor
leakage 0, letter leakage 0 across 46 paragraphs, 26 of 28 suggestions kept.
(An earlier "155 of 156 fabrications rejected" figure was measured by hand
against the v1.0.1 rules and no longer describes them; nothing in the repo
regenerates it, so it is not repeated as a current claim.)

The known limits are structural and written down in `docs.md §6`: the verifier
grounds facts, not relations, so a CV saying "managed Google Ads" supports a
sentence saying "worked at Google".

**v1.0.2 — the letter could not name its own recipient.** `letter.v1` handed
the model the real `ROLE:` and `COMPANY:` and asked for placeholders only when
they were unknown, so whenever they were known the model wrote them — and the
verifier, correctly, cannot ground the name of the company the candidate is
applying *to* against a CV that has never heard of it. The opening was repaired
away at the cost of an extra model call, and the letter began mid-argument with
no greeting. `letter.v2` never tells the model either name, so it cannot guess
one, and `pipeline.resolve_placeholders` fills them in at the point of use —
the DOCX and the letter screen — leaving the stored text exactly as the
verifier approved it. Adversarial eval: **34 surviving paragraphs before, 46
after**, leakage still 0.

**v1.0.2 — the posting-vocabulary leak.** The rule that let a posting lend its
wording was shaped "allowed unless the tech lexicon knows it", so an unknown
word was an allowed word — and the unknown words in a posting are the product
and vendor names. `verify/concepts.py` inverts it: a lone word is lent only if
it is a listed concept, and a phrase only if it runs to two capitalised words.
The adversarial sampler now plants an unknown vendor in the posting's own
requirements and claims it in a bullet; the old rule leaks it **10 times across
the 12 cases**, the new one not at all.

## 6. Frontend plan

- **State:** Preact signals; one async state machine per screen (`idle → running → done | error`).
- **Router:** small hash-based router (don't rely on the History API inside the iframe).
- **SDK:** `AnnaAppRuntime.connect()`; without a host (plain browser preview) use a fixture-backed stub + visible "Preview mode" banner.
- **CSP:** no inline scripts/styles; fonts self-hosted in `public/fonts`; no external CDNs.
- **Size budget:** JS ≤ 90 KB gzip, CSS ≤ 20 KB, fonts ≤ 180 KB total.
  Measured at v1.0.1: **JS 28.9 KB gzip, CSS 4.0 KB gzip, fonts 172 KB.**
  The fonts are the variable originals from the Google Fonts repo, subset to
  Latin + Latin-Extended-A with `pyftsubset` (so Turkish is covered) and served
  as WOFF2 — 176 KB for two families against 290 KB for the four unsubset
  Google slices.
- **Responsive:** single column at 360 px; two panels (requirements | CV) at ≥ 900 px.
- **Design system and screens:** `docs.md §8–9`. The one bold element: highlighter marks.

### Dependency justifications (`CLAUDE.md` requires one per dependency)

| Dependency | Where | Why |
|---|---|---|
| `preact`, `@preact/signals` | bundle | Named in `CLAUDE.md`. 28 KB gzip total for the whole app. |
| `pydantic` | engine | Every LLM response is validated against a model, and the same models generate the JSON Schema sent to the host. Hand-writing either would let them drift. |
| `pypdf`, `python-docx` | engine | PDF and DOCX text extraction, and DOCX generation for export. |
| `rapidfuzz` | engine | Reserved for near-duplicate requirement merging; not on a hot path yet. |
| `vitest`, `@anna-ai/cli` | dev | Bundle tests and the official harness/validator. |
| `pytest`, `anna-executa-test`, `ruff`, `mypy` | dev | Engine tests and static checks. |
| `playwright-core` | dev | Drives an already-installed Chromium for `scripts/screenshots.mjs`, `scripts/a11y.mjs` and `scripts/typography.mjs`. The anti-vibe-code review is a looking exercise; the accessibility rules and the type system are measurements. A build that only compiles proves none of the three. **Never bundled** — it is a tooling dependency and appears nowhere in `ui/package.json`. |
| `fonttools[woff]` | build, one-off | Subsets the two typefaces to Latin + Turkish. Run by hand, not in CI; the outputs are committed. |

**Not** taken: `executa-sdk` (the helper used by Anna's own examples) is not
published on PyPI and the examples resolve it through a relative path. The
three frames Receipts needs — the v2 handshake, `sampling/createMessage` and
`executa/progress` — are ~200 dependency-free lines in
`receipts_engine/host/`, written against the verified wire format.

## 7. Test strategy

| Layer | Tool | Coverage |
|---|---|---|
| Verifier | pytest | Invented numbers/names/tools, unit and word-boundary collisions, synonym rewrites (must pass), Turkish casefolding and suffixes, 73 cases |
| Parsing | pytest | Single/multi-column PDF, DOCX tables, empty file, >2 MB, encrypted PDF |
| Plugin contract | anna-executa-test | describe, every action, error codes, progress events |
| LLM output quality | fixture eval script | Golden set 12 CVs × 12 postings; requirement extraction F1 ≥ 0.85, false "strong" ≤ 5%, tailor **and cover-letter** leakage 0 |
| Bundle | vitest + mountBundle | Screen states, no calls outside the ACL, empty/error states |
| End-to-end | `anna-app dev` record/replay | Happy path + 5 error paths as jsonl fixtures |
| Accessibility | `scripts/a11y.mjs` | AA contrast against the real composited background, accessible names, visible focus, 44 px tap targets, heading order, pointer-only controls — 17 screens × 2 widths × 2 themes, fails the build on a violation |
| Environments | Cloud Agent + Local Agent | Mandatory manual pass before submission — **needs an Anna account** |

Counts at v1.1: **293 engine tests** (76 of them on the verifier, 10 on the
rate limiter, plus a concurrency case that drives five overlapping invokes
through a real subprocess) and **115 bundle tests**; `ruff` and `mypy --strict` clean;
`anna-app validate --strict` clean; `pnpm a11y` reports no findings across all
68 screen/width/theme combinations; all seven recordings pass
`anna-app fixture verify`.

Seven of those seventeen screens are reached by running the flow rather than by
opening a route (`scripts/preview-flow.mjs`: add a CV, paste a posting, run the
match, with the stub answering and no model involved — and, for the recurring
report, two more postings, because the engine says nothing below three
applications and a harness that never gets there would be auditing a state no
user sees). `#/match/example` is read-only by design, so an audit that only opened routes never rendered Accept,
Skip, Edit, the edit box, the tone and length switches, a tracker row, its
status select, or the delete confirmation — the controls the product is made
of. The same flow feeds the Tailor, cover-letter and tracker screenshots, for
the same reason: a store listing that shows the output and none of the verbs
undersells the app and tells a reviewer nothing about whether it works.

**The eval harness is wired and proven; the model numbers are not in yet.**
`scripts/eval_match.py` spawns the plugin, acts as its host, and forwards
`sampling/createMessage` to whatever `--sampling-cmd` names — so it needs a
model to produce a real F1.

The adversary is committed, so the grounding half of the eval runs offline and
in CI with no account and no credits: `pnpm eval:adversarial` points the
harness at `scripts/fabricating_sampler.py`, which answers every sampling call
with schema-valid output that invents a percentage, a spelled-out number, an
employer, a team size or a tool the source lines do not contain, cites a CV
line that does not exist once every four requirements, and complies only when
asked to repair. Current run: **12/12 cases complete, tailor leakage 0, letter
leakage 0 across 34 paragraphs, 26 of 28 suggestions kept** — the verifier
catches what it cannot support in bullets and in letter paragraphs alike, and
the repair call rescues most of them rather than dropping the line. That last
number is the one that keeps the first two honest: a verifier that rejected
everything would also report zero leakage, so `--adversarial` fails a run that
keeps nothing. `RECEIPTS_EVAL_VERBOSE=1` shows the plugin log deciding it.

`--adversarial` reports F1 and the false-strong rate but does not gate on them:
against a scripted sampler they measure the script's keyword matching, not a
model, and are not reportable. For those two, run it against a real host with
`--sampling-cmd`, or `--record` once and `--replay` after.

## 8. Timeline (last revised: Saturday, September 19, 2026)

| Dates | Phase | Output |
|---|---|---|
| Sep 16–17 | Phase 0 — Setup & verification | Account, developer activation, minted IDs, scaffold, host API facts verified and recorded in code |
| Sep 17–19 | Phase 1 — Engine | Parsing, sampling, extract/match, verifier, tests |
| Sep 18–21 | Phase 2 — UI | Tokens, components, all screens, i18n |
| Sep 21–22 | Phase 3 — Integration | Async flow, tailor/letter/export, tracker, mobile, Cloud Agent test |
| Sep 22–23 | Phase 4 — Listing & submission | Screenshots, copy, video, **submit for review** |
| Sep 23–Oct 1 | Phase 5 — Launch prep | Content, community warm-up, DoraHacks BUIDL; fix & resubmit if rejected |
| Oct 1 → | Phase 6 — Launch & growth | 500 MAU (October), 1,000+ (November) |
| Monthly | Phase 7 — Maintenance | prd.md §10 releases |

Reality check: review takes up to 5 business days and results are sent in batches on Mondays and Thursdays. A Sep 22 submission → result Sep 28 or Oct 1 at the earliest. The September Launch Boost is therefore not targeted; **October is the first qualifying month.**

## 9. Growth plan (the MAU engine)

**Allowed:** normal marketing, content, communities, creator partnerships, free access. **Prohibited:** rewards per run, giveaways, reciprocal usage groups, micro-task sites, runs from own/team accounts.

| Channel | Tactic | Measurement |
|---|---|---|
| Anna Store page | SEO page at `/store/@handle/receipts`; clear screenshots; `?action=install` link | Store → install rate |
| Reddit (r/resumes, r/jobs, r/cscareerquestions, r/careerguidance) | Rule-compliant posts: "I built a CV tailoring tool that refuses to invent anything — honest feedback wanted"; value first, link second | `?ref=reddit` |
| LinkedIn (EN + TR) | 3 posts/week: anonymized match-map visuals, "why invented CV claims blow up in interviews" | `?ref=linkedin` |
| University career clubs & bootcamps | Free workshop: "Tailor your CV to a posting in 5 minutes — honestly" | `?ref=campus-<name>` |
| Discord/Telegram job-search communities | Promotion with moderator permission | `?ref=community-<name>` |
| Anna ecosystem | Builder Discord showcase, forum build post, marketing support package applications | `?ref=anna` |
| Content SEO | Blog post: "An ATS-friendly CV without lying" | `?ref=blog` |

**Target funnel (October):** ~6,000 link visits → 25% install (1,500) → 45% first match (~675) → ≥ 500 Qualified MAU with repeat use.

**Shareability:** "Copy summary" on the match map (summary text without personal data + app link), and since v1.3 **"Make a card"** (`prd.md` F22) — a 1200×630 image of the match built from counts and enums only, so it carries no CV line, no employer and no wording from the posting. The role title is the single opt-in exception. That is the anonymised match-map visual this table's LinkedIn row has always assumed; before it existed the only way to make one was to photograph a screen full of the user's own career. Brand hook for content: *"Show your receipts."* No automatic sharing.

## 10. Demo video script (90 s)

| Sec | Visual | Voiceover |
|---|---|---|
| 0–8 | Another AI tool's invented bullet ("increased revenue by 40%") gets struck through | "Most AI resume tools make things up. Recruiters notice." |
| 8–20 | Receipts opens, CV already saved, posting pasted | "Receipts starts from what you've actually done." |
| 20–40 | Progress: requirements appear, yellow marks sweep as evidence is found | "Every requirement is checked against a real line in your CV." |
| 40–55 | Match map: evidenced / related / no evidence; tapping evidence highlights line L23 | "You see the evidence — and the honest gaps." |
| 55–72 | Tailor: suggestion with source chip; one suggestion shows "couldn't strengthen without inventing" | "If your CV can't prove it, it doesn't get written." |
| 72–84 | Cover letter with citations, DOCX download | "A cover letter that comes with receipts." |
| 84–90 | Logo + subtitle + Anna Store link | "Receipts. Tailor every application. Invent nothing." |

## 11. Cost estimate (per user, informational)

Match: ~3 calls, ~15k input + ~3k output tokens. Tailor: 1–2 calls. Letter: 1–2 calls. Exact credit cost depends on Anna pricing; measure with `anna-app dev --llm` and record it here. Optimizations: cache parsed CVs; cache requirement extraction by posting hash.
