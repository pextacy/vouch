# Receipts — Product Requirements Document

> **One line:** Receipts checks a job posting against your CV line by line, highlights the evidence for every requirement, then writes tailored CV bullets and a cover letter — **using only facts your CV can prove.**
>
> **Marketplace subtitle:** *Tailor every application. Invent nothing.*
> **Slug:** `receipts` (fallback if taken: `receipts-cv`) · **Category:** productivity / career · **Languages:** English (default), Turkish

Status: v1.0.1, built and verified · Date: September 17, 2026 · Owner: (your name)

---

## 1. Why this idea (decision rationale)

The Anna Founding Builder Program is not judged by a panel; grants are paid on **Qualified App MAU**. The official rules create hard constraints, and Receipts is designed around each one:

| Program constraint (official rules) | How Receipts answers it |
|---|---|
| MAU = unique signed-in users who **successfully** complete the primary function in a month. Opening or installing doesn't count. | The primary function ("Evidence Match") needs one input (a job posting) and completes in under 60 seconds. The CV is saved after first use, so repeat use is nearly frictionless. |
| AI-native core required; superficial chatbots are rejected. | All value depends on AI reasoning: requirement extraction, evidence matching, grounded rewriting. There is no chat UI. |
| Clones and near-duplicates are rejected; distinctiveness matters. | Unlike other AI resume tools, every generated sentence cites a source CV line and passes a deterministic verifier — the "Invent nothing" guarantee. |
| Third-party API outages are not remediated. | Zero external APIs. LLM, web fetch, storage and downloads all go through Anna host APIs. |
| One meaningful maintenance update per month. | Roadmap is split into monthly releases (§10). |
| No app splitting, no artificial usage. | One app. Demo mode never calls the LLM and never produces a qualified run. No incentivized usage. |
| Mobile support is coming (`form_factors`). | UI is designed mobile-first. |

**Why the name "Receipts":** "Show me the receipts" means "prove it." The product's entire promise is proof: every requirement shows its evidence, every rewritten bullet shows its source line, and the cover letter comes with citations. It is one memorable word, easy to say in a demo, easy to search in the store, and it stands apart from the crowded "Resume/CV/Job + AI" naming pattern. Names considered and rejected: Shortlist (generic, widely used), Tailor (common verb, weak ownership), Proofline, Evident, Groundwork (less memorable).

**Market logic:** job seekers are a huge audience, every application is a new reason to return, the match map is screenshot-friendly, and career communities (Reddit, LinkedIn, university career clubs, bootcamps) are ready-made organic distribution. 200 → 1,000+ monthly users is realistic for this audience.

**Alternatives evaluated and dropped:** contract/lease risk scanner (legal-advice and review risk), lecture notes → flashcards (Anna already showcases "study-buddy"; clone risk), trip planner and focus timer (Anna's own showcase examples), subscription tracker (weak AI dependency).

---

## 2. Problem

1. Job seekers send the same CV to every posting; ATS filters and recruiters discard CVs that don't mirror the posting within seconds.
2. Existing AI resume tools "improve" CVs by **inventing experience** — fake metrics, tools never used. It surfaces in interviews and burns the candidate.
3. Candidates can't clearly see which requirements they meet and which they genuinely lack, and don't know how to prepare honestly for gaps.

## 3. Target users

| Persona | Context | Success looks like |
|---|---|---|
| **Active job seeker (primary)** — 1–8 years experience, 10–40 applications/month | Tailoring a CV per posting takes too long | Tailoring time per application drops from ~45 min to ~5 min |
| **New graduate / intern** | Little experience, unsure what to emphasize | Sees their proven strengths and their real gaps |
| **Career switcher** | Can't express transferable skills in the posting's language | Honest reframing of partial matches |

Out of scope for v1: recruiter/HR side, bulk candidate screening.

## 4. Product principles

1. **Invent nothing.** Every generated bullet and cover-letter paragraph cites at least one CV line. Content that fails verification is never shown; the user is told plainly.
2. **Evidence is always visible.** The user can always see why something was called a strong match.
3. **A gap is a plan, not a shame.** Missing requirements are presented as things to prepare for, not red alarms.
4. **One screen, one job.**
5. **The data belongs to the user.** The CV lives only in the user's Anna storage and can be deleted in one step.

## 5. Scope — v1.0 (the version submitted for review)

Every new version is re-reviewed, so v1.0 must be launch-ready and complete.

### F1 — Master CV
- Upload PDF / DOCX (≤ 2 MB) or paste text.
- The engine splits the CV into lines with stable ids (`L1…Ln`) and labels sections (Experience, Education, Skills…).
- The user reviews the parsed preview and can fix a misread line.
- Saved to storage; not requested again on later visits. "Delete my CV" is always reachable.

### F2 — Evidence Match (PRIMARY FUNCTION → Qualified App Run)
- Input: posting text (paste) or posting URL (fetched via host `web` API; on failure the user is sent to paste).
- Output:
  - Requirements list: `must` / `nice`, category (skill, experience, education, domain, soft, logistics).
  - Per requirement: **strong** (direct evidence), **partial** (related/transferable evidence), **missing** (no evidence) + cited CV lines + one-sentence rationale.
  - Summary sentence: "9 of 14 requirements have evidence in your CV. 2 must-haves don't."
- Success condition: at least one requirement extracted and a status assigned to every requirement → this moment is the **Qualified App Run**.

### F3 — Tailored Bullets
- Suggestions only for CV lines tied to strong/partial requirements.
- Each suggestion: original line ↔ suggestion, source chip (`L23`), accept / skip / edit.
- Verifier (docs.md §6): any number (with its unit), date, duration, proper noun, tool or job title in the suggestion that isn't in the source → one repair attempt → if it still fails, the suggestion is dropped with the note "We couldn't strengthen this line without adding facts that aren't in your CV."

### F4 — Cover Letter
- Tone: Plain / Warm / Formal. Length: short (~150 words) / standard (~250).
- Every paragraph carries citations; the user can show/hide them. Same verifier.
- If the company name isn't in the posting, a placeholder is used — never invented.

### F5 — Export
- Tailored bullets + cover letter: DOCX download (host `files.download`) and copy to clipboard.

### F6 — Application Tracker
- Every match is saved: company, role, date, coverage, status (Drafted / Applied / Interview / Offer / Closed).
- List view; opening an entry reloads its match map from storage (no LLM call).
- Retention engine: users come back to manage their applications here.

### F7 — Chat integration (Skill)
- Typing `#receipts` in Anna chat with a pasted posting opens the app window with the posting prefilled.

### F8 — Example preview
- "See an example" on onboarding → a static, pre-recorded fixture. **No LLM call, not a qualified run.** Its job is to show the output, not to inflate MAU.

### Deferred (monthly maintenance releases)
Interview Prep, LinkedIn headline/About tailoring, multiple CV profiles, follow-up email drafts, posting comparison.

## 6. User flows

**First use (target ≤ 3 min):**
Open → Add your CV (upload/paste) → confirm preview → Paste a job posting → Run match → progress (requirements appear, evidence gets highlighted as it's found) → Match map → (optional) Tailor → Cover letter → Export.

**Repeat use (target ≤ 60 s):**
Open → New match → paste posting → Run match → result.

**From chat:**
`#receipts` + posting text → window opens with posting prefilled → Run match.

## 7. Success metrics

| Metric | Definition | October target | November target |
|---|---|---|---|
| **Qualified MAU** | Unique users completing ≥1 successful match in the month | **500** (Tier D) | **1,000+** (Tier C) |
| Activation | Share of users who open the app and complete a first match | ≥ 45% | ≥ 55% |
| Match success rate | Started matches that complete without error | ≥ 97% | ≥ 98% |
| Fabrication leak | Suggestions that passed the verifier but were reported as invented | < 1% | < 0.5% |
| Matches per user | Average matches per monthly active user | ≥ 3 | ≥ 4 |
| p50 match time | Start → result | ≤ 45 s | ≤ 35 s |

Stretch: 4,000 MAU in December (Tier B). Source: Developer Console → Analytics (DAU/WAU/MAU).

## 8. Non-functional requirements

- **Reliability:** every error is caught; the user is told what happened and what to do. An empty or failed result is never shown as success.
- **Performance:** long work runs as async tool jobs with real-time progress; never hits the 90 s synchronous limit.
- **Cost:** ≤ 3 LLM calls and ≤ ~15k input tokens per match. CV trimmed to 6k tokens, posting to 3k.
- **Privacy:** CV data only in APS (per-user storage). No CV content in logs. No external services. "Delete all my data" in one step.
- **Accessibility:** WCAG 2.2 AA contrast, full keyboard use, visible focus, `prefers-reduced-motion`; statuses expressed by shape + text, not color alone.
- **Mobile:** fully functional at 360 px width.
- **i18n:** EN + TR interface strings; generated output follows the posting's language.

## 9. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Review rejection (Executa packaging / Cloud Agent failure) | Medium | End-to-end test on Cloud Agent before submitting; review checklist. |
| LLM fabricates content | Medium | Deterministic verifier + repair + drop; citations visible in UI. |
| PDF parsing yields garbled text | Medium | Editable preview; paste-text fallback; multi-column warning. |
| Posting URL can't be fetched (login walls, bot protection) | High | URL is optional; error message routes to paste. |
| Low initial traffic | High | Launch plan (plan.md §9), Anna marketing support programs, `?ref=` channel tracking. |
| September Launch Boost missed | Very high | Accepted: review time makes 200 MAU in September unrealistic. Target is qualifying in October (deadline Nov 30). |
| Uncertain host API signatures | Medium | Verify against `llms.txt` before writing the call; record the verified signature in a comment beside it. |
| Name/slug already taken on Anna | Low | Fallback slug `receipts-cv`; display name stays "Receipts". |

## 10. Monthly maintenance roadmap (program requirement)

| Month | Version | Meaningful improvement |
|---|---|---|
| October | v1.1 | Interview Prep: likely questions for partial/missing requirements + honest answer outlines grounded in the CV |
| November | v1.2 | LinkedIn headline & About tailoring; multiple CV profiles (e.g. "Backend" / "Data") |
| December | v1.3 | Follow-up email drafts + tracker reminders; side-by-side posting comparison |
| January | v1.4 | Verifier improvements from user reports; additional languages |

## 11. Submission package

- Published Anna Marketplace app (required).
- Open-source repo (MIT); `docs/` explains the architecture and the "Invent nothing" verifier.
- 90-second demo video (script in plan.md §10).
- DoraHacks BUIDL page: what it is, who it's for, how AI is used, how it connects to Anna. **Note:** a forum thread mentions a separate DoraHacks deadline of September 30 — confirm the date and requirements on your own BUIDL page.
