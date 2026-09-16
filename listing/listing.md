# Marketplace listing — paste-ready copy

Everything the Listing tab in the Developer Console asks for. The canonical
source is `docs.md §11`; this file is the filled-in version, plus the assets
that go with it.

---

## Name

```
Receipts
```

## Subtitle / tagline

```
Tailor every application. Invent nothing.
```

## Category

`productivity` (career)

## Search keywords

```
CV, resume, job application, cover letter, ATS, job match, career
```

## Short description

```
Paste a job posting. Receipts checks each requirement against your real CV,
shows the evidence, and writes tailored bullets and a cover letter that only
use facts you already have.
```

## Full description

```
Paste a job posting. Receipts checks each requirement against your real CV,
shows you the evidence, and writes tailored bullets and a cover letter that use
only facts you already have.

HOW IT WORKS

1. Add your CV once — PDF, DOCX or pasted text. It is split into numbered lines
   and saved in your Anna storage.
2. Paste a job posting. Receipts pulls out every stated requirement and marks it
   as evidenced, related, or no evidence yet — each one citing the CV lines that
   back it.
3. Ask for tailored bullets or a cover letter. Every sentence is checked by a
   deterministic verifier before you see it; anything that cannot be traced back
   to your CV is dropped, not softened.

WHY IT IS DIFFERENT

Most AI resume tools improve a CV by inventing experience — metrics you never
hit, tools you never used. That surfaces in interviews. Receipts refuses: a
number, tool, employer or job title that is not in your CV never reaches the
page. You see the gaps honestly, and what to prepare for.

WHAT YOU GET

- A match map showing every requirement and the CV line that evidences it.
- Tailored CV bullets, each shown next to the line it was rewritten from.
- A cover letter where every paragraph lists the CV lines it stands on.
- DOCX export, and a tracker for the applications you have out.

YOUR DATA

Your CV lives only in your Anna account storage. Receipts uses no external
services and holds no API keys. Delete everything in one step from Your data.

Interface in English and Turkish. Works on desktop and mobile.
```

## Primary function (stated explicitly for review)

```
Evidence Match — analyzes a job posting against the user's saved CV and returns
each requirement with a status (evidenced / related / no evidence) and the cited
CV lines. A successful match is the app's primary function; it completes in
under 60 seconds and is reachable in two clicks from a saved CV.
```

## Privacy note

```
Your CV is stored only in your Anna account storage. Receipts uses no external
services. Delete everything anytime from Your data.
```

## Permissions the store will display

Derived from `manifest.ui.host_api`, not from the legacy `permissions` list:

| Namespace | Methods | Why |
|---|---|---|
| `tools` | the bundled Receipts engine | parsing, matching, tailoring, export |
| `storage` | get, set, delete, list | your CV and your saved matches |
| `files` | upload_init, upload_finalize, download | the DOCX you download |
| `web` | fetch | optional: read a posting from a link (off until you allow it) |
| `window` | set_title | window title follows the open match |

## Assets

| Asset | File |
|---|---|
| Icon | `../ui/public/icon.svg` — a highlighter stroke across a bracketed line on cool paper |
| Screenshot 1 — match map (desktop) | `screenshots/04-match-map-desktop.png` |
| Screenshot 2 — tailored bullets, including one dropped | `screenshots/05-tailor-desktop.png` |
| Screenshot 3 — cover letter with citations | `screenshots/06-letter-desktop.png` |
| Screenshot 4 — match map (mobile) | `screenshots/04-match-map-mobile.png` |
| Screenshot 5 — match map (dark) | `screenshots/04-match-map-desktop-dark.png` |

Regenerate with `node scripts/screenshots.mjs` (add `--dark`, and `--no-banner`
for store assets — the preview strip is for development, not for the store).

## Demo video — 90 seconds

The shot list from `plan.md §10`, with what is on screen in this build.

| Sec | On screen | Voiceover |
|---|---|---|
| 0–8 | Another tool's invented bullet — "increased revenue by 40%" — struck through | "Most AI resume tools make things up. Recruiters notice." |
| 8–20 | Receipts opens on the tracker, CV already saved; paste a posting into New match | "Receipts starts from what you've actually done." |
| 20–40 | Progress: the ledger steps through, requirements appear, marks sweep in as evidence is found | "Every requirement is checked against a real line in your CV." |
| 40–55 | Match map; tap the L3 chip and the CV sheet scrolls to that line | "You see the evidence — and the honest gaps." |
| 55–72 | Tailor: a suggestion with its source line, then the dropped one | "If your CV can't prove it, it doesn't get written." |
| 72–84 | Cover letter with citations, then Download DOCX | "A cover letter that comes with receipts." |
| 84–90 | Icon, subtitle, store link | "Receipts. Tailor every application. Invent nothing." |

Record against `anna-app dev --llm` so the progress timing is real.

## Review checklist (forum: "App Review Timeline & Process")

- [x] Core functionality works; the experience matches the description
- [x] Logo, screenshots and description are complete and clear
- [x] Users understand what the app does and how to use it — onboarding states
      the promise in one line and offers a no-cost example
- [x] Tools/Executa properly packaged — one Executa, `uv` distribution,
      `anna-app validate --strict` clean
- [ ] Dependencies work on Cloud Agent / Local Agent — **needs an account**
- [x] Permissions and data access are appropriate — five namespaces, each used
- [x] No known bugs or unfinished features — every screen has empty, loading
      and error states
- [x] Mobile checklist — 360 px verified, safe areas honoured, 44 px targets,
      no hover-only actions, no hand-written viewport meta

## Channel links (plan.md §9)

| Channel | Link |
|---|---|
| Reddit | `https://anna.partners/store/@handle/receipts?ref=reddit` |
| LinkedIn | `…?ref=linkedin` |
| Campus workshops | `…?ref=campus-<name>` |
| Communities | `…?ref=community-<name>` |
| Anna ecosystem | `…?ref=anna` |
| Blog / README | `…?ref=blog` |

The tag is read at boot (`router.ts` → `referralTag`), kept in memory, and
never attached to a user.
