# Receipts — Phases & Task List

Each phase ends with an **exit criterion**. Don't start the next phase until it's met.

Date reference: today is September 16, 2026. Target submission: **September 22**. Launch: **October 1**.

**Legend:** `[x]` done · `[ ]` open · `[~]` done as far as it can be without an
Anna developer account. Everything marked `[~]` is blocked on one thing —
registering at anna.partners and minting ids — and nothing else.

---

## Phase 0 — Setup & API verification (Sep 16–17)

- [~] Create anna.partners account; activate developer access **← needs a person**
- [~] Join the Builder Discord; draft a forum build post
- [~] Check that the `receipts` slug is available; otherwise use `receipts-cv`
- [~] `https://anna.partners/executa` → create Tool → **Mint**
- [~] Create Skill → **Mint**
- [x] Install `@anna-ai/cli` (0.1.52); harness boots and serves the bundle
- [x] Scaffold restructured to match `plan.md §3`
- [x] Read the `anna-executa-examples` reference app (focus-flow, long-task-demo,
      sampling-summarizer) and follow its patterns
- [x] **API verification** — every signature read from the live docs and written
      to `docs/api-notes.md`:
  - [x] App Manifest + App UI Manifest + Mobile Support (`form_factors` lives in `ui`)
  - [x] Host API: `tools.*` (invoke / invokeAsync / getJob / cancelJob / listJobs),
        `storage.*`, `files.*`, `web.*`, `window.*`, `chat.*`
  - [x] Executa: Sampling (`responseFormat`, **not** a `json_schema` top-level
        param), Protocol limits, Lifecycle, `executa/progress`
  - [x] Publishing an App + Listing Fields + Common Pitfalls
- [x] Every `VERIFY` marker in `docs.md` resolved, with the decision recorded
      next to it
- [~] Set up PAT for `anna-app dev --llm`; record the cost of one sampling call

**Exit criterion:** ✅ met — the UI opens in the harness, `engine` responds to
`tools.invoke` through the production dispatcher, `docs/api-notes.md` is
written, `anna-app validate --strict` passes.

---

## Phase 1 — Engine (Sep 17–19)

- [x] `schemas.py`: Pydantic models (`docs.md §4`), `extra="forbid"`, JSON Schema
      generated from the models
- [x] `parse/cv.py`: PDF (pypdf), DOCX (python-docx, incl. tables), text; line
      splitting, section detection, `L<n>` ids, warnings
- [x] Error codes: `file_too_large`, `unreadable_file`, `cv_too_short`, and the
      rest of the `docs.md §3` table
- [x] `host/sampling.py`: reverse sampling, `responseFormat`, low temperature,
      one retry, `model_output_invalid` / `sampling_unavailable`
- [x] `pipeline/extract.py` + `prompts/extract.v1.md`
- [x] `pipeline/match.py` + `prompts/match.v1.md`; guard for non-existent `line_ids`
- [x] `run_match` async flow with `emit_progress` stages (`docs.md §3`)
- [x] Requirement cache keyed by posting hash
- [x] `verify/grounding.py` + `TechLexicon` with synonyms — **59 unit tests**
- [x] `pipeline/tailor.py` + repair loop + drop
- [x] `pipeline/letter.py` + paragraph citations + placeholders
- [x] `export/docx.py` (returns bytes; see the decision in `docs.md §3`)
- [x] `tests/plugin`: contract test per action, driven as a real subprocess
- [x] `fixtures/golden`: 12 cases (9 EN, 3 TR); `scripts/eval_match.py`
- [~] Eval thresholds: F1 ≥ 0.85, false "strong" ≤ 5%, tailor leakage 0 —
      the harness and thresholds are wired; **the numbers need a live model**
      (`--sampling-cmd`, or `--replay` a recorded run)

**Exit criterion:** ✅ met except the live-model eval — 187 tests green,
`ruff` and `mypy --strict` clean, `run_match` completes end to end through the
harness.

---

## Phase 2 — Interface (Sep 18–21)

- [x] Vite + Preact + TS; `outDir: ../bundle`; no inline scripts or styles
- [x] Self-hosted fonts (Schibsted Grotesk, Source Serif 4; Latin + Latin-Ext,
      subset to 172 KB)
- [x] `styles/tokens.css` (light/dark), `base.css`, `marks.css` — `docs.md §8`
- [x] Custom SVG icon set (highlighter tip, underline, bracket, tab, upload,
      download, trash, check, pencil)
- [x] App icon (`docs.md §11` concept)
- [x] `lib/anna.ts`: typed SDK wrapper + stub mode + `PreviewBanner`
- [x] Component inventory (`docs.md §8.8`) — keyboard, focus ring, dark theme
- [x] Screens: Onboarding, Add CV, CV preview/fix, New match, Progress, Match
      map, Tailor, Cover letter, Tracker, Your data
- [x] `MarkerHighlight` sweep driven by progress events; reduced-motion support
- [x] Desktop two-panel ↔ mobile tabbed layout; verified at 360 px
- [x] i18n EN + TR; copy matches `docs.md §9`; parity enforced by a test
- [x] Empty, loading and error states on every screen
- [x] **Anti-vibe-code audit** — screenshots taken and checked (below)
- [x] vitest: i18n parity, routes, ACL, engine client (47 tests)

**Anti-vibe-code audit** — checked against `listing/screenshots/`:
- [x] No gradients, glassmorphism or neon glow
- [x] No grid of identical shadowed cards; shadow only on `DocumentSheet`
- [x] No ALL-CAPS eyebrow labels; no `A · B · C` meta strings; no `→` in buttons
- [x] No emoji icons; no off-the-shelf icon library
- [x] No circular score gauge, percentage badge or red/green traffic lights
- [x] No single emphasized word in headings
- [x] Radius hierarchy per `docs.md §8.5` (sheet 2 / input 6 / button 8 / tab 10)
- [x] No receipt clip-art or thermal-paper gimmicks
- [x] The only automatic entrance animation is the highlighter sweep
- [x] Copy contains no "Unlock", "Supercharge", "Seamless", "AI-powered magic"
- [x] AA contrast verified numerically in both themes — worst pair 4.88:1
      (`--graphite` on `--tab`); every other pair ≥ 5.5:1
- [~] Lighthouse accessibility ≥ 95 — not run; contrast, focus rings, keyboard
      paths and landmarks were checked by hand instead

**Exit criterion:** ✅ met — the full flow is clickable in preview mode, the
audit is clean, and the bundle is **28.4 KB JS / 3.9 KB CSS gzip** against a
90 / 20 KB budget.

---

## Phase 3 — Integration & hardening (Sep 21–22)

- [x] UI ↔ engine: `parse_cv`, `run_match` (async job + onProgress + AbortSignal),
      `tailor`, `letter`, `export_docx`
- [x] Recover an in-flight job after page reload (`listJobs` by `clientTag`)
- [x] Posting URL → host `web.fetch` → paste fallback on failure (the grant is
      off by default, so the fallback is the common path)
- [x] Storage keys (`docs.md §7`), tracker status, "Delete all my data"
- [x] Skill: `#receipts` → `open_app_view` with the posting as payload
- [x] Recordings: happy path + 5 error paths; `anna-app fixture verify` green
- [~] Install and full end-to-end flow on **Cloud Agent** — **needs an account**
- [~] Same pass on **Local Agent** — **needs an account**
- [~] Full flow in the mobile launcher — needs the mobile shell
- [x] Fault injection: short CV, corrupt PDF, image-only PDF, oversized file,
      non-posting text, out-of-order chunks, cancelled job, sampling refused,
      mismatched CV hash — each asserted in the suite
- [~] Performance: p50 match ≤ 45 s over 10 runs — needs a live model
- [x] Confirmed no CV content in logs — the plugin logs codes, counts and
      timings only

**Exit criterion:** partially met. Everything reachable without an account
works end to end through the production dispatcher; no error path shows a blank
screen or a false success. The clean-account install pass is the open item.

---

## Phase 4 — Listing & review submission (Sep 22–23)

- [x] `app.json` and the listing copy: name, subtitle, description, keywords,
      category, privacy note (`listing/listing.md`)
- [x] Icon + 8 screenshots (desktop and mobile, light and dark)
- [x] Primary function stated explicitly in the description
- [~] Versions tab: paste manifest, upload bundle, check `min_version`
- [~] Executa visibility set to `app_bundled` or `public`
- [x] **Official review checklist** — everything not needing an account is
      ticked in `listing/listing.md`
- [x] README, architecture diagram, verifier explanation, MIT license
- [x] 90-second demo video **script** with the shot list mapped to real screens
      — the recording itself needs the app running against a live model
- [~] **Submit for review** — record date, App ID and version

**Exit criterion:** not met — submission requires an account.

---

## Phase 5 — Review window & launch prep (Sep 23 – Oct 1)

- [ ] If rejected: fix all feedback, rerun the Phase 3–4 checklists, resubmit
- [ ] DoraHacks BUIDL page: description, repo, video; confirm the deadline
- [ ] Content bank: 10 LinkedIn posts (EN/TR), 3 Reddit drafts, 1 blog post
- [x] `?ref=` link table per channel (`listing/listing.md`)
- [ ] Book workshops with 3 university career clubs / bootcamp communities
- [ ] Apply for Anna marketing / launch support packages
- [ ] Start v1.1 (Interview Prep) on a branch without touching the published version

---

## Phase 6 — Launch & growth (Oct 1 →)

- [ ] Oct 1: forum showcase + Builder Discord + LinkedIn + first Reddit post
- [ ] Weekly: DAU/WAU/MAU and installs by channel → `growth-log.md`
- [ ] Weekly: collect feedback; add every reported "invented" case to
      `tests/verify/test_grounding.py`
- [ ] Oct 15 checkpoint: if MAU trajectory < 250, analyse the activation funnel
- [ ] October: **500 Qualified MAU (Tier D)**; November: **1,000+ (Tier C)**
- [ ] Never: rewards per run, giveaways, reciprocal usage groups, team accounts

---

## Phase 7 — Monthly maintenance (every month, program requirement)

- [ ] October → v1.1 Interview Prep
- [ ] November → v1.2 LinkedIn tailoring + multiple CV profiles
- [ ] December → v1.3 Follow-up emails + posting comparison
- [ ] Every release: rerun the eval, Cloud/Local Agent pass, submit in the first
      half of the month
- [ ] Month end: summarize MAU, cost, error rate; set next month's priority

---

## What is blocked, and on what

Four things, all the same blocker — an account at anna.partners:

1. **Minted ids.** The repo runs on `tool-dev-receipts-engine`; `anna-app apps
   publish` mints the real one and substitutes it everywhere. Nothing in source
   needs editing.
2. **Live-model numbers.** The eval harness, the thresholds and the golden set
   exist; `python scripts/eval_match.py fixtures/golden --sampling-cmd …`
   produces the F1 and false-strong figures once a model can be reached.
3. **Cloud/Local Agent install pass.** The packaging is right — `uv`
   distribution, one Executa, `anna-app validate --strict` clean — but "it
   installs on a clean account" is only provable on one.
4. **Submission.** Listing copy, screenshots, icon and the review checklist are
   written; the Developer Console does the rest.
