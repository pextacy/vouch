# Receipts — Technical & Operational Plan

This document covers **how** we build and **how** we grow. For what we build see `prd.md`; for contracts and the design system see `docs.md`; for the step-by-step task list see `phases.md`.

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

> ✅ **Verified in Phase 0.** Every signature is recorded in
> [`docs/api-notes.md`](docs/api-notes.md), read from the live docs, the
> published `@anna-ai/app-schema` bundle, and the reference example repo. Four
> of them changed the design: `form_factors` lives inside `ui`; the shipped
> validator caps `schema` at 2; there is no byte channel between the iframe and
> the plugin (hence chunked upload); and an inner failure reaches the UI as
> `tool_failed` with only a message, so the error code travels in that string.

## 2. System diagram

```
┌─────────────────────────── Anna UI Runtime (sandboxed iframe) ──────────────────────────┐
│  bundle/ (Preact SPA)                                                                    │
│   ├─ screens: Onboarding · CV · NewMatch · Progress · MatchMap · Tailor · Letter · Tracker │
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
│ llm/sampling.py      reverse sampling + json_schema + retry         │
│ pipeline/extract.py  requirement extraction                         │
│ pipeline/match.py    evidence matching                              │
│ pipeline/tailor.py   bullet tailoring                               │
│ pipeline/letter.py   cover letter                                   │
│ verify/grounding.py  "Invent nothing" deterministic verifier        │
│ export/docx.py       DOCX generation → host upload                  │
└─────────────────────────────────────────────────────────────────────┘
executas/receipts-coach/SKILL.md → #receipts chat behavior
```

## 3. Repository layout

```
receipts/
├── CLAUDE.md  prd.md  plan.md  docs.md  phases.md
├── README.md                     # public
├── app.json                      # listing metadata (slug, name, category)
├── manifest.json                 # AppManifest schema 2
├── package.json                  # @anna-ai/cli devDependency, scripts
├── ui/                           # frontend source (Vite)
│   ├── index.html
│   ├── vite.config.ts            # outDir: ../bundle, no inline scripts
│   ├── src/
│   │   ├── main.tsx  app.tsx  router.ts
│   │   ├── screens/  components/  lib/  i18n/{en,tr}.json
│   │   └── styles/{tokens.css, base.css, marks.css}
│   └── public/{icon.svg, fonts/*.woff2}
├── bundle/                       # BUILD OUTPUT — never edit by hand
├── executas/
│   ├── receipts-engine/
│   │   ├── executa.json  pyproject.toml  README.md
│   │   └── receipts_engine/{plugin.py, parse/, llm/, pipeline/, verify/, export/, schemas.py, prompts/}
│   └── receipts-coach/SKILL.md
├── fixtures/                     # sample CVs/postings + recorded dev sessions (jsonl)
├── tests/
│   ├── plugin/                   # pytest + anna-executa-test
│   ├── verify/                   # verifier unit tests (most critical)
│   └── ui/                       # vitest + mountBundle
├── scripts/{set-tool-id.py, eval_match.py}
├── docs/api-notes.md             # host API signatures verified in Phase 0
└── listing/                      # icon, screenshots, store copy
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

- `tailor` and `letter` are separate actions, called only when the user asks (cost control).
- Every LLM call: `temperature ≤ 0.2`, `json_schema` required, one retry on schema failure, then a meaningful error.
- Line ids are generated deterministically from CV text; the LLM receives `L12: …` and returns ids only.
- **Qualified run moment:** when `run_match` successfully returns a `MatchResult`. An empty requirement list is not success → `no_requirements_found` error and the message "This text doesn't look like a job posting."

## 5. The "Invent nothing" verifier (the heart of the product)

Full algorithm in `docs.md §6`. Summary: **claim tokens** are extracted from generated text (numbers, percentages, currency, dates; capitalized proper nouns; tech/tool lexicon matches; titles) and searched for in the normalized union of the cited CV lines. Any token not found is a violation → one repair call with the violation list → if violations remain, the output is dropped. The verifier is pure Python, uses no LLM, and targets 100% unit-test coverage.

## 6. Frontend plan

- **State:** Preact signals; one async state machine per screen (`idle → running → done | error`).
- **Router:** small hash-based router (don't rely on the History API inside the iframe).
- **SDK:** `AnnaAppRuntime.connect()`; without a host (plain browser preview) use a fixture-backed stub + visible "Preview mode" banner.
- **CSP:** no inline scripts/styles; fonts self-hosted in `public/fonts`; no external CDNs.
- **Size budget:** JS ≤ 90 KB gzip, CSS ≤ 20 KB, fonts ≤ 180 KB total.
  Measured at v1.0: **JS 28.4 KB gzip, CSS 3.9 KB gzip, fonts 172 KB.**
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
| `playwright-core` | dev | Drives an already-installed Chromium for `scripts/screenshots.mjs`. Added in Phase 2 because the anti-vibe-code audit and the 360/1280 review are looking exercises, and a build that only compiles proves nothing about them. **Never bundled** — it is a tooling dependency and appears nowhere in `ui/package.json`. |
| `fonttools[woff]` | build, one-off | Subsets the two typefaces to Latin + Turkish. Run by hand, not in CI; the outputs are committed. |

**Not** taken: `executa-sdk` (the helper used by Anna's own examples) is not
published on PyPI and the examples resolve it through a relative path. The
three frames Receipts needs — the v2 handshake, `sampling/createMessage` and
`executa/progress` — are ~200 dependency-free lines in
`receipts_engine/host/`, written against the verified wire format.

## 7. Test strategy

| Layer | Tool | Coverage |
|---|---|---|
| Verifier | pytest | Invented numbers/names/tools, synonym rewrites (must pass), Turkish casefolding, 40+ cases |
| Parsing | pytest | Single/multi-column PDF, DOCX tables, empty file, >2 MB, encrypted PDF |
| Plugin contract | anna-executa-test | describe, every action, error codes, progress events |
| LLM output quality | fixture eval script | Golden set 12 CVs × 12 postings; requirement extraction F1 ≥ 0.85, false "strong" ≤ 5% |
| Bundle | vitest + mountBundle | Screen states, no calls outside the ACL, empty/error states |
| End-to-end | `anna-app dev` record/replay | Happy path + 5 error paths as jsonl fixtures |
| Environments | Cloud Agent + Local Agent | Mandatory manual pass before submission — **needs an Anna account** |

Counts at v1.0: **187 engine tests** (59 of them on the verifier alone) and
**47 bundle tests**; `ruff` and `mypy --strict` clean; `anna-app validate
--strict` clean; all seven recordings pass `anna-app fixture verify`.

**The eval harness is wired and proven, the numbers are not in yet.**
`scripts/eval_match.py` spawns the plugin, acts as its host, and forwards
`sampling/createMessage` to whatever `--sampling-cmd` names — so it needs a
model to produce a real figure. Smoke-tested against a deliberately naive
stub sampler that marks every requirement "strong": all 12 golden cases ran,
requirement F1 came out at 0.881, and the run **failed** on a false-strong rate
of 0.307 — which is the metric doing exactly its job. Tailor leakage was 0 even
against that sampler, because the verifier drops what it cannot support
regardless of what produced it. Run it for real with
`--sampling-cmd`, or `--record`/`--replay` for CI.

## 8. Timeline (today: Wednesday, September 16, 2026)

| Dates | Phase | Output |
|---|---|---|
| Sep 16–17 | Phase 0 — Setup & verification | Account, developer activation, minted IDs, scaffold, `api-notes.md` |
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
| Content SEO | README + blog: "An ATS-friendly CV without lying" | `?ref=blog` |

**Target funnel (October):** ~6,000 link visits → 25% install (1,500) → 45% first match (~675) → ≥ 500 Qualified MAU with repeat use.

**Shareability:** "Copy summary" on the match map (summary text without personal data + app link). Brand hook for content: *"Show your receipts."* No automatic sharing.

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

Match: ~3 calls, ~15k input + ~3k output tokens. Tailor: 1–2 calls. Letter: 1–2 calls. Exact credit cost depends on Anna pricing; measure with `anna-app dev --llm` in Phase 0 and record in `docs/api-notes.md`. Optimizations: cache parsed CVs; cache requirement extraction by posting hash.
