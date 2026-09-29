# Vouch — Product Requirements Document

> **One line:** Vouch checks a job posting against your CV line by line, highlights the evidence for every requirement, then writes tailored CV bullets and a cover letter — **using only facts your CV can prove.**
>
> **Marketplace subtitle:** *Tailor every application. Invent nothing.*
> **Slug:** `vouch` (fallback if taken: `vouch-cv`) · **Category:** productivity / career · **Languages:** English (default), Turkish

Status: v1.3.0, built and verified · Date: September 27, 2026 · Owner: (your name)

---

## 1. Why this idea (decision rationale)

The Anna Founding Builder Program is not judged by a panel; grants are paid on **Qualified App MAU**. The official rules create hard constraints, and Vouch is designed around each one:

| Program constraint (official rules) | How Vouch answers it |
|---|---|
| MAU = unique signed-in users who **successfully** complete the primary function in a month. Opening or installing doesn't count. | The primary function ("Evidence Match") needs one input (a job posting) and completes in under 60 seconds. The CV is saved after first use, so repeat use is nearly frictionless. |
| AI-native core required; superficial chatbots are rejected. | All value depends on AI reasoning: requirement extraction, evidence matching, grounded rewriting. There is no chat UI. |
| Clones and near-duplicates are rejected; distinctiveness matters. | Unlike other AI resume tools, every generated sentence cites a source CV line and passes a deterministic verifier — the "Invent nothing" guarantee. |
| Third-party API outages are not remediated. | Zero external APIs. LLM, web fetch, storage and downloads all go through Anna host APIs. |
| One meaningful maintenance update per month. | Roadmap is split into monthly releases (§10). |
| No app splitting, no artificial usage. | One app. Demo mode never calls the LLM and never produces a qualified run. No incentivized usage. |
| Mobile support is coming (`form_factors`). | UI is designed mobile-first. |

**Why the name "Vouch":** to vouch for a claim is to stand behind it — and the app only stands behind what the CV can show. Every requirement shows its evidence, every rewritten bullet shows its source line, and the cover letter comes with citations. It is one short word, easy to say in a demo and easy to search in the store, and it stands apart from the crowded "Resume/CV/Job + AI" naming pattern. The product was first built as *Receipts*, from "show me the receipts"; the internal identifiers (`receipts_engine`, `tool-dev-receipts-engine`, the `receipts:*` job tags and the storage keys) keep that name, because renaming them would orphan stored data and minted tool ids for no visible gain.

**Market logic:** job seekers are a huge audience, every application is a new reason to return, the match map is screenshot-friendly, and career communities (Reddit, LinkedIn, university career clubs, bootcamps) are ready-made organic distribution. 200 → 1,000+ monthly users is realistic for this audience.

**Alternatives evaluated and dropped:** contract/lease risk scanner (legal-advice and review risk), lecture notes → flashcards (Anna already showcases "study-buddy"; clone risk), trip planner and focus timer (Anna's own showcase examples), subscription tracker (weak AI dependency).

---

## 2. Problem

1. Job seekers send the same CV to every posting; ATS filters and recruiters discard CVs that don't mirror the posting within seconds.
2. Existing AI resume tools "improve" CVs by **inventing experience** — fake metrics, tools never used. It surfaces in interviews and burns the candidate.
3. Candidates can't clearly see which requirements they meet and which they genuinely lack, and don't know how to prepare honestly for gaps. Worse, much of what they *have* done never reached the CV: side projects, a task owned once, work that was never in a job title.

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
- The model always writes `[Company]`, `[Role]` and `[Hiring Manager]` and is never told their real values, so it cannot guess one. The app substitutes what the posting gave it when the letter is rendered or exported; whatever is left is listed for the user to replace before sending.

### F5 — Export
- Tailored bullets + cover letter: DOCX download (host `files.download`) and copy to clipboard.

### F6 — Application Tracker
- Every match is saved: company, role, date, coverage, status (Drafted / Applied / Interview / Offer / Closed).
- List view; opening an entry reloads its match map from storage (no LLM call).
- Retention engine: users come back to manage their applications here.

### F7 — Chat integration (Skill)
- Typing `#vouch` in Anna chat with a pasted posting opens the app window with the posting prefilled.

### F8 — Example preview
- "See an example" on onboarding → a static, pre-recorded fixture. **No LLM call, not a qualified run.** Its job is to show the output, not to inflate MAU.

### F9 — Gap questions (v1.1)

This is the feature that finally delivers principle 3. Until it existed the app
only *stated* the gap: a requirement came back "No evidence yet" and the screen
ended there, which is a diagnosis, not a plan.

- From the match map, "Prepare for the gaps" — shown only when something is
  unproven. One question per requirement the match marked `missing` or
  `partial`, must-haves first, capped at 6.
- Each question may carry an **angle**: one sentence naming what in the CV
  already sits closest, with its line citations. It is verified like a tailored
  bullet and dropped rather than softened, so most questions have none.
- The user answers in their own words. The answer is appended to the master CV
  **verbatim** as a new line marked `added_at`, shown as "Added by you"
  wherever the CV is rendered.
- Adding a line moves the CV hash, so the open match is out of date and the app
  says so and offers to run it again. That second run is a second Qualified App
  Run, which is also the retention argument: a user with gaps has a reason to
  come back with something new to prove.

Why it is the differentiator rather than one more feature: every other AI
resume tool closes a gap by writing the experience in for the candidate. The
gap *is* the absence of evidence, so anything generated to fill it is a
fabrication by construction. Vouch closes it the only honest way there is —
by asking, and by treating what the person says as the only admissible source.

### F10 — CV audit (v1.1)

Every verifier in this product guards the text the app **writes**. Nothing had
ever looked at the CV the user arrived with — which is where their real
interview risk already lives, usually put there by a previous tool.

- Reached from the CV preview ("Check what it can't back up"). No posting
  needed: this is the only thing the app can do the moment a CV exists.
- **No model, no tokens, no quota** — set arithmetic in the engine, so it is
  instant, free and deterministic. Three findings, capped at 12: a tool in the
  skills list that no job, project or certification shows in use; a seniority
  word at the top that no role below carries; a date range that ends before it
  starts or two roles overlapping by two years or more.
- Each finding offers the same loop as F9 — the user says where it actually
  happened, and their sentence is appended to the CV verbatim. The audit
  re-runs, so a finding clears because it was answered, not because it was
  hidden. A date conflict is the exception: it offers "Fix the line" instead,
  because an explanation nobody reading the CV will ever see is not evidence.
- The engine states no opinion. It returns a `kind` and a bare `subject`; the
  sentence comes from the UI string table, in the user's language.

It is also the answer to the app's coldest start: a new user with a CV and no
posting yet has something worth doing on their first visit.

### F11 — What keeps coming up (v1.1)

The app was honest about one application at a time and learned nothing across
them. Someone applies twenty times, the same requirement comes back unproven in
fifteen of them, and nothing ever says so. That is the question a single match
structurally cannot answer — *which gap is actually costing me jobs?* — and
Vouch is the only app that can, because it already stores a verified
per-requirement verdict for every application the user has made.

- Reached from the tracker once there is more than one match. **No model, no
  tokens**: the grouping is lexicon work in the engine, the counting is
  arithmetic over records already in storage.
- Reads the 40 most recent applications. A gap is named only when it was asked
  in at least two of them and proved in **none**. A skill with a mixed record
  is passed over in silence rather than scored.
- Below three applications the screen says so and asks the user to come back —
  a pattern drawn from two would be a horoscope.
- Every row carries its denominator ("Asked in 5 applications, and proved in
  none of them") and can show the requirement wordings it merged, so the user
  can disagree with the grouping instead of trusting it.
- Closes with "What you keep proving": the terms asked more than once and
  backed every time. A report that is only a list of failures stops being read.
- Same answer loop as F9 and F10 — except that one sentence here changes the
  verdict on every future match rather than on one, which is what makes this
  the screen that tells the user which sentence is worth the most.

This is also the strongest retention argument in the product: it gets better
the more the user applies, and it gives someone a reason to open Vouch on a
day they are not applying to anything new.

### F12 — Interview brief (v1.2)

Everything before this screen is about getting the application sent. Then the
app went quiet: a tracker row could be marked *Interview* and nothing
followed — yet that room is where this product's promise is actually tested,
out loud, by someone whose job is to find the seam between what a CV says and
what happened.

- Reached from a saved match ("Prepare for the interview"), and from the
  tracker row the moment its status becomes *Interview*, which until now
  changed a word and nothing else.
- **No model, no tokens.** Every line on it is a record that already exists:
  the match's verdict per requirement, the CV lines it cited, and the
  sentences the user accepted and sent.
- **"Expect to be pressed here"** ranks what will be hard, must-haves first.
  Four shapes, each read off the evidence rather than judged: nothing in the
  CV shows it; the only evidence is the skills list, which the match accepted
  as proof and an interviewer will not; the only evidence is a line the user
  typed into Vouch *after* sending the document; or the match called it
  related rather than the same thing.
- **"What you can prove"** is the other half, each with the CV's own line
  highlighted underneath. A brief that is only a list of weaknesses stops
  being opened — the same reason the recurring report closes on strengths.
- Under each requirement sits what was actually claimed about it: the accepted
  tailored bullets and the cover-letter paragraphs, quoted exactly, with their
  line numbers. No other tool can show this, because no other tool holds both
  the verdict and the sentence that was sent.
- **It writes nothing.** A generated answer would invent the one thing that
  has to be the candidate's own, at the moment it costs the most — the app
  doing in the interview exactly what it refuses to do on the CV.
- A CV that moved after the application went out is reported rather than
  refused (`tailor` refuses it): the document the interviewer is holding is
  the older one, and that is worth knowing on the way in.

### F13 — Which one you can prove (v1.2)

Between "does this CV fit this posting" and "what keeps costing me jobs" sits
the decision a job seeker actually makes: three postings are open in three
tabs, there is time to tailor one of them properly, and nothing anywhere says
which. Every other tool answers that with a fit score — a number invented by
the same model that wrote the bullets, precise to a percentage point about
something it guessed.

- Reached from the tracker, beside "What keeps coming up", as soon as there
  are two applications to compare. The two most recent are selected on
  arrival, so the screen answers rather than asking the user to fill in a form
  first.
- **No model, no tokens.** Every number is a tally of verdicts the verifier
  already made, one application at a time, so any of them can be checked by
  opening the match it came from. There is no score and no gauge anywhere on
  the screen.
- Per posting: must-haves proved out of must-haves asked, the same for the
  whole posting, and **the must-haves standing in the way** — the reason to
  spend the hour somewhere else.
- Per posting, the thing only a comparison can say: **what this posting asks
  for, your CV proves, and at least one of the others never asks about at
  all.** That is where the evidence already in hand is worth the most, and no
  single match can see it.
- Across the set: what every one of them asks for and none of them proves —
  one answer changes every application on the screen — and what every one of
  them asks for and the CV proves every time.
- Grouping is the lexicon `recurring_gaps` already uses, so "Kubernetes in
  production" and "Experience running services on Kubernetes" are known to be
  the same demand; the wordings it merged are shown beside each row, so the
  user can disagree with the grouping rather than trust it.
- The ordering is by evidence and says so on screen: *"Ordered by what your CV
  can prove. That is not the same as which job you want."* The app has no
  opinion about the second thing and does not pretend to.

It also fills the last gap in the funnel. The app could tell someone what to
fix after applying (F9, F11) and what to expect after being invited (F12); this
is the first screen that helps before the hour is spent.

### F14 — Take your CV back (v1.2)

The app ate a CV and never gave one back. That was tolerable while the stored
CV was only a copy of an uploaded file — and stopped being tolerable the
moment three screens started writing into it. A gap answer, an audit answer
and a recurring answer all become CV lines the next match can cite, and not
one of them could reach the document an employer actually reads. F12 is what
made the hole impossible to ignore: it labels every requirement whose only
evidence is such a line, and says "assume they have not read it."

- "Download your CV" on the CV screen, where someone is already looking at
  their own document, and again under "Your data", because taking the
  document with you is part of leaving (principle 5).
- **No model, no verifier.** Every paragraph is one `CVLine.text`, byte for
  byte. There is nothing to check, because the document *is* the CV — and an
  export that tidied a sentence would be the app editing someone's account of
  their own career.
- Lines come out grouped by section in reading order, not in stored order: an
  answer is appended to the end of the CV, so without grouping a new job would
  print under the skills list.
- **"Just the lines you added"** is the second document, offered only when
  there are any: someone who keeps a CV they designed wants the new sentences
  to paste, not a plain replacement for the layout they spent an evening on.
- The screen says what the file is before the click: plain text, the way an
  ATS reads it, with the original layout gone and nothing rewritten. The full
  CV carries no footer and no Vouch signature — a tool's name at the bottom
  of someone's CV is the tool taking credit for their career.

### F15 — More than one CV (v1.2)

The app held one CV. For the career switcher in §3 that was not only
inconvenient — it was quietly wrong. Someone applying to backend roles with one
document and data roles with another had both careers in one pile, so the
screens that read across applications (F11, F13) counted requirements from jobs
the other CV was never sent to: a recurring gap drawn from both careers names
something half the applications never asked for, and tells the person to go and
learn it.

- **A CV is a workspace.** Switching it switches the document that gets
  tailored *and* the applications on screen — the tracker, the recurring
  report, the comparison. Every match records which CV it was checked against,
  because its citations are line numbers and those point at different sentences
  in another document.
- Reached from the CV screen: tabs once there is more than one, and "Add
  another CV" before that. Nothing appears for someone who has one CV and has
  never asked for a second, which is most people.
- Named by the user, defaulting to the uploaded file's name — "CV 2" only when
  the CV was pasted. Renamed in Your data, where they are also deleted.
- **Deleting a CV takes its applications with it**, and the confirmation says
  how many. A match whose CV is gone would render its citations against
  whichever document was loaded instead.
- Up to five. Past that a CV set is a filing cabinet, and every one of them is
  a document the user is supposed to keep true.
- **Nobody's first CV moves.** It stays under the key v1.0 wrote it to and
  answers to the id `default`; a match saved before this feature existed has no
  CV recorded and belongs to it. There is no migration step to get wrong, which
  matters more here than anywhere else in the app: the CV is the one thing it
  cannot lose.

### F16 — Check a document you didn't write (v1.3)

The verifier is this product. Until now it only ever ran on text Vouch
itself wrote — a tailored bullet, a letter paragraph, a gap question's angle.
That guarantee ends at the export, and the export is where people live: the
bullets get pasted into the CV someone designed in Word, a line gets added at
1 a.m., and the document that reaches the employer was checked by nothing. The
other half of the audience never got as far as an export — they arrive with a
CV another AI "improved" for them last spring, which is precisely the harm §2
names, sitting in a file the app could see and refused to look at.

- Reached from the CV screen ("Check a document you're sending") and from the
  cover letter ("Check the version you're sending"), which opens with the
  letter already in the box — the last honest moment before it is sent.
- Paste a CV or a cover letter. Every sentence is read against the whole CV
  with the **same rule** `tailor` is held to, and every unbacked number, date,
  duration, tool, employer or title is quoted back in the document's own
  spelling, inside the brackets the match map already uses for "no evidence".
- **No model, no tokens, no quota, and nothing stored.** It is the
  deterministic pass that already exists, so it is instant and free, it works
  offline, and the pasted document is read once and dropped. That is also what
  makes it the app's cheapest first visit: someone with a CV and a file they
  are nervous about has something worth doing before any posting exists.
- **The app never edits the user's document.** It offers the one honest repair
  it has — the same loop as F9, F10 and F11: say where it happened, the
  sentence becomes a CV line verbatim, and the check runs again, so the line
  clears because it is backed now. For anything that did not happen the screen
  says the only other true thing: take it out before you send it.
- The envelope is not the letter. Bracket placeholders, the company and role of
  the open application, and salutations and sign-offs are set aside — and the
  screen lists which words it disregarded, because a check that quietly ignores
  things is not a check. Every one of those rules is anchored on a word that
  can only be addressing, so "Hiring Manager, Globex, 2023–2025" on an
  experience line is still checked like anything else.

Why it is the differentiator rather than one more feature: every other tool in
this category *produces* documents and vouches for nothing afterwards. Vouch
is the only one that can read a document it did not write and say — for free,
deterministically, and without a model's opinion in it — which sentences an
interviewer will take apart. Including one a competitor wrote.

### F17 — Which lines do the work (v1.3)

Every screen so far reads the CV as a source: the match cites it, the tailor
rewrites from it, the brief quotes it. None of them ever read it as a
**record**. So the app knew, and never said, which of someone's twenty-odd
sentences has actually carried an application — and which has sat on the page
for two years without a single posting ever needing it.

That is the question a job seeker cannot answer alone. They can see that a CV
is too long; they cannot see which line is load-bearing, because the evidence
for that is spread across forty applications they sent one at a time.

- Reached from the tracker, beside "What keeps coming up" and "Which one you
  can prove", and shown once three applications are saved — the screen needs
  three before it can say anything, so it appears when it has something to
  say rather than leading someone to a dead end.
- **No model, no tokens.** Every number is a citation the verifier already
  made, in an application the user can open and check. There is no score, no
  "strength" rating and nothing a model has an opinion about: a tool that
  calls a bullet weak is describing a CV, and this describes what the CV did.
- **"Doing the work"** ranks the lines by how many applications cited them,
  each quoted with its own mark, its denominator ("Evidence in 6 of your 9
  applications") and what the postings called the things it answered. The one
  warning on the screen is the line that was **the only evidence behind a
  must-have**: that application was resting on one sentence, which is worth
  knowing before an interviewer reads it.
- **"Never asked for"** is the other half, and the copy is the feature: *"No
  posting you applied to needed these. That is a fact about the jobs you
  picked, not about the work."* Every other tool in this category would call
  this a cut list. The app has counted; it has not judged, and it says so.
- **"The sentences you added"** closes it. Three screens ask the user to write
  a sentence into their CV (F9, F10, F11) and not one of them ever reported
  back on whether it was worth writing. This is the receipt for the answer
  loop: what that sentence has proved since, or that nothing has asked for it
  yet.
- Honest about its own denominator. A line id is a position, not a sentence —
  after a re-uploaded CV, `L12` is a different line — so applications checked
  against another parse of the document are left out **and counted on screen**
  rather than quietly dropped. Adding a line never costs a citation, which is
  what lets the third section exist at all.

It is also the first screen that improves the document itself rather than one
application of it: the ordering it produces is the order to put the page in,
and "Download your CV" is one tap away on the CV screen.

### F18 — Since you applied (v1.3)

The app is honest right up to the moment an application is sent, and then it
has nothing further to say about that application — while three of its own
screens keep growing the CV underneath it. Someone applies to a posting that
wanted Kafka, comes back a week later and writes the sentence about the Kafka
consumer they actually rewrote (F9, F10 or F11), and nothing anywhere connects
that sentence to the five applications it would have changed. **The evidence
arrived after the envelope, and the app watched it happen.**

Nobody else can join those two records. This app already stores the
per-requirement verdict for every application and the date on every line the
user has written into their CV.

- Reached from a tracker row once it is marked *Applied* or *Interview* —
  the only rows where the question means anything.
- **No model, no tokens.** Dates, and a lexicon lookup over records that
  already exist.
- It opens with the application's age on the clock it actually has: "You
  marked this sent 11 days ago", or, for a row from before the tracker
  recorded its statuses, "You ran this match today" — plus how to give it the
  better clock. It never implies a day nobody recorded.
- **"Worth running again"** is the substance: what this posting asked for,
  the application could not show, and a line written since **names**. Each
  row carries the verdict it got when it went out, the user's own new
  sentence quoted with its line number, and the terms they share.
- **The word "names" is the feature.** Deciding that a sentence *proves* a
  requirement is the match's job — a model call with the verifier behind it —
  and this is a lexicon hit between two strings. The copy says so out loud:
  *"Naming is not proving — only a new match can say what they are worth."*
  An app that graded its own homework with the one tool it does not trust for
  the job would be doing a small version of what this product exists to
  refuse.
- A requirement the lexicon does not recognise never lights up, and a line
  that was already in the CV when the match ran is not news. Most weeks the
  honest answer is "nothing has changed", and the screen is written for it.
- The posting's text is not stored — keeping an employer's words in someone's
  account for months is not this product's to do — so the action opens New
  match with the posting's link when there was one, and says plainly that the
  text needs pasting when there was not.

It is also the strongest MAU argument in the product after the tracker itself:
every answer a user writes turns some of their old applications into a reason
to run a new match, and a second qualified run is exactly what the program
counts (§1). The prompt is earned rather than invented — the app only nudges
when the record supports it.

### F19 — Answer what the form asked (v1.3)

Vouch checks the bullets it rewrites and the letter it writes. Then the
application form asks four more things in free text — *"Describe your
experience with Kubernetes." "Tell us about a time you owned an incident."
"Why do you want to work here?"* — a human reads every one of them, and the
app had nothing to say about that box. It is the same harm §2 names, one field
lower down the page: the candidate opens another tab, gets a confident
paragraph about experience they do not have, and pastes it under a CV this
product just spent an hour keeping honest.

- Reached from the match map, beside the cover letter, because the letter box
  and the four boxes under it are filled in one sitting. It works without an
  application open too: after the first round these questions arrive by email.
- The paste is split into questions **deterministically**, before anything is
  spent, and the split is shown — "Read as 3 questions" — with "Not a question"
  beside each one. A wrong split is the difference between answering the
  question and answering half of two, so it is the user's to correct.
- Each answer is sentences the verifier passed, with the CV line under every
  one and "Copy this answer" beside it. Anything the cited lines cannot back
  is repaired once and then dropped, and the count of what was dropped is on
  screen rather than swallowed.

What makes it the differentiator is the two ways it declines:

- **No evidence.** The CV cannot answer it, so nothing is written around it.
  The user gets the question back and their own sentence becomes a CV line —
  the F9 loop — and the re-run then answers from a line that exists.
- **Not about you.** The question asks what the candidate *wants*: why this
  company, what excites them, where they see themselves. A CV records what
  someone did and holds no evidence of wanting anything, so the app writes
  nothing and says why. This is the paragraph every competing tool ships, and
  the one place where an invented answer is invented by construction.

Both refusals are enforced rather than requested: prose arriving under
`not_about_you` is discarded unread, and an answer whose every sentence failed
verification is downgraded to "no evidence" instead of being reported as a
thin one. The questions themselves are never a source — they come from an
employer's form, which makes them the one input here an outsider controls, and
letting them license a claim would be the posting-vocabulary leak with a new
front door. `scripts/fabricating_sampler.py` attacks exactly that seam and
`pnpm eval:adversarial` gates it at zero, alongside the bullets and the letter.

### F20 — When the match gets it wrong (v1.3)

The match map is the screen the whole product exists to show, and it was the
only one the user could not answer back. The extraction and the matching are
model calls; `scripts/eval_match.py` measures them and prints the number
(requirement F1 ≈ 0.91), which is another way of saying the app is sometimes
wrong about somebody's career in front of them. Until now the only recourse
was to run it again and hope — and every other tool in this category has the
same shape: a verdict, delivered, with no reply address.

- On any requirement the match did not call `strong`, "The match got this
  wrong" turns the CV sheet itself into a picker. The user taps the lines that
  cover it, in the document they are already looking at; there is no separate
  chooser and nothing new to learn.
- **The verdict is never rewritten.** The correction is stored beside the
  match, not inside it, so the record can always answer both questions: what
  the app found, and what the person said. It is shown the same way — under
  the verdict, behind a rule, in the user's own voice: *"You said these lines
  cover it. Vouch didn't find it — so this one is yours to make."*
- **The counts stay the app's own.** The summary sentence — the one people
  screenshot — does not move. The corrections are reported on their own line:
  *"You marked 2 more as covered. Those are your call, not ours."*
- Nothing generated can lean on it. `tailor` and `letter` build from the
  match's evidence, which has not changed, and the verifier still checks every
  sentence against the CV line it cites. The guarantee holds by construction
  rather than by care.
- The cross-application screens (F11, F13, F17) keep counting the match's own
  verdicts, and that is deliberate: they exist to say what the *market* could
  not see in the CV, and a line only the candidate believes proves something is
  precisely what a recruiter will not find.
- The interview brief is the one screen that reads corrections, where they
  arrive as their own risk, ranked second only to having no evidence at all:
  *"You told Vouch a line covers this and Vouch couldn't see it. Nobody
  but you has agreed with that yet, so be ready to make the case out loud."*

Only the constructive direction is offered — the app missing something the CV
shows. Arguing the other way ("that line does not prove it") would need the app
to agree it was wrong about something it did find, which is a different
feature and a different conversation.

Why it is the differentiator: every other AI resume tool hands down a score you
cannot argue with, produced by the same model that wrote the bullets. Vouch
is the only one where the person whose career it is can correct it — and the
only one that then remembers, all the way into the interview prep, that the
correction was theirs.

### F21 — The verdict, checked (v1.3)

Every generated claim in this app meets a deterministic rule before anyone sees
it — except the one the product is named after. `tailor` and `letter` are
checked sentence by sentence. The **match map** was not: `strong`, `partial`,
`missing` and the CV lines under them were model output, validated for shape
and for whether the cited ids exist, and nothing more. The app's own eval has
been printing the cost of that from the beginning as the false-`strong` rate,
and a wrong `strong` is the worst error this product can make — it is the app
handing someone a receipt for something their CV cannot show, which is exactly
what §2 says every other tool does.

- When a requirement names a **technology** — a term the lexicon knows, so
  "Kubernetes", "PostgreSQL", "k8s", not "stakeholder management" — a `strong`
  verdict now has to cite a line that contains it.
- If another line in the CV does, the **citation is repaired**: the evidence
  was real and the pointer was wrong, and the verdict stands.
- If nothing in the CV shows it, the verdict falls to **related** — which is
  precisely what `partial` means — the model's one-line rationale is cleared,
  because it described a strength that is not there, and the map says why in
  plain words: *"The posting asks for Kubernetes by name, and the line below
  doesn't show it — so this is marked related, not evidenced."*
- **No model, no tokens.** It runs in the `guard` stage the pipeline already
  had, so a match costs exactly what it cost before.

Narrow on purpose, because a false downgrade is worse than the disease: only
`strong` is checked, only technologies are demanded, and a lone ambiguous word
is not a demand. Titles and durations are deliberately excluded — "Lead a
team" against "Led a team of 4 engineers" is the same fact and not the same
word, and demanding it would downgrade correct verdicts wholesale.

Measured with `pnpm eval:adversarial`, whose sampler now plants the exact
failure the rule exists for:

| | false `strong` |
|---|---|
| guard off | **0.235** (8 of 34) |
| guard on | **0.167** (5 of 30) |

The survivors are requirements naming nothing a lexicon can check, which is the
documented edge of the rule. It pairs with F20 by design: the app is stricter
now, and the person whose career it is has a reply address for the times it is
stricter than it should be.

### F22 — A receipt you can show (v1.3)

`plan.md §9` names the growth engine in one line — *anonymised match-map
visuals*, under the hook "Show your receipts" — and §1 calls the match map
screenshot-friendly. Neither was true. The only picture of a match a person
could make was a photograph of their own screen, carrying their employers,
their job titles and the sentences of their CV. That is the one image a job
seeker cannot post, so the mechanic the whole distribution plan rests on had no
product behind it.

- From the match map, "Make a card": a 1200×630 image of the match — the
  summary sentence in the first person, the requirements as shapes in two
  labelled rows, the legend, the tagline.
- **The privacy is structural, not careful.** `cardFor` reduces a match to
  counts and enums; `renderCard` can only draw what it is handed. A CV line, an
  employer or a requirement's wording cannot reach the card *because they never
  reach the renderer*. `tests/ui/share.spec.ts` builds a card from a match
  stuffed with distinctive words and asserts none of them appear in the output.
- **The role title is the one exception, and it is off.** It is the only thing
  on the card that could say which job someone is applying for, so it is opt-in
  each time rather than a setting, and it is escaped on the way in because it
  comes from a posting.
- The preview **is** the file: one renderer draws into the page and writes to
  disk, so nobody has to trust that what they saw is what they saved.
- **No model, no tokens.** Counts the match already holds, drawn.

Why it belongs to this product rather than being a share button: the card shows
the gaps. "6 of 8 requirements have evidence in my CV. 1 must-have doesn't." is
a sentence no career post makes, and it is the product's promise in the one
place other people will read it.

### F23 — What changed (v1.3)

Four screens in this app ask the user to write a sentence into their own CV —
a gap question (F9), an audit finding (F10), a recurring gap (F11) — and the
newest of them (F18) ends by telling them to run the posting again. They run
it again, and the app hands back a fresh match map with no memory of the first
attempt.

So the one moment this entire product is built towards — **the sentence you
wrote turning a "no evidence yet" into a receipt** — was the moment it had
nothing to say. Every screen before this one asks the user for work; this is
the first that reports back on whether the work paid.

- Reached from the match map of a second run of the same posting, as a quiet
  line in the head. It never appears on a first run, which is almost all of
  them.
- **No model, no tokens.** Two stored results, lined up.
- The two runs are paired on the lexicon every cross-application screen uses,
  because requirements are re-extracted on every run — `R3` in one is not
  `R3` in the other. What cannot be paired is shown as "Read differently this
  time" rather than guessed at: a wrong pairing would announce a gap closed
  that never closed.
- It opens on **both totals** — "You now have evidence for 7 of 8. Last time
  it was 6 of 8" — because the posting is read again each run and the
  denominator can move. Hiding that would make a gain of one look like three.
- **"Because of a line you added between the two runs."** This is the only
  claim in the product that the user's own writing caused a result, so it is
  also the narrowest: it appears when the newer run cites a line written after
  the older one, and never otherwise. A gain with any other explanation is
  reported without taking the credit.
- **What went the other way is shown with the same weight.** A posting read
  twice is not read identically, and a screen that only ever reported gains
  would be flattery. The copy says why, and offers both match maps.
- Closes on what is still unproved, with the gap questions one tap away —
  which is where the loop starts again.

It is also the retention argument the other screens set up and none of them
could finish: the product now has a visible payoff for answering a question
honestly, and that payoff is a second qualified run.

### F24 — Worth another look (v1.3)

F18 asks, of one application, whether the CV has gained a line since it went
out that names something it could not show. It answers well, and it is the
wrong shape for the person in §3: someone sending thirty applications a month
is never going to open thirty saved applications to find out whether last
Tuesday's sentence changed any of them. **The answer existed, and nothing was
ever going to read it.**

- Reached from the tracker, beside the other shelf-wide screens, from the
  first saved application — one worth reopening is already worth saying.
- **No model, no tokens.** Dates and a lexicon over records that already
  exist, sharing the naming rule with F18 so the index and the detail can
  never disagree.
- Each row carries its denominator: *"Your CV now names Kafka. That is 1 of
  the 2 things this application could not show"*, plus how many of them were
  must-haves, the posting's own wordings, and the line the user wrote after
  applying.
- Two empty states, because they have different next steps. Nothing found
  says so and waits; **nothing written** sends the user to the gap questions,
  because until they answer one there is nothing for this screen to check
  against.
- Every row ends at F18 for that application, which is where the re-run is
  offered. One screen, one job: this is the index, that is the detail.

It is the strongest reason in the product to open Vouch on a day you are
not applying to anything new — and, unlike a reminder, it is earned: the app
only says an application is worth an hour when the user's own writing has made
it so. Each row that gets acted on is a second Qualified App Run (§1).

### F25 — The follow-up, and the refusal to send one (v1.3)

An application goes out and nothing comes back. This is the last silence in
the product: the tracker records the day it was sent and then the app has
nothing further to offer until an interview appears.

Every other tool in this category fills that silence on demand — a warm
paragraph saying the candidate remains very interested, which hands a
recruiter nothing they did not already have. That email is not free. It
spends the one piece of attention a candidate gets, and it is read by someone
who can tell there is nothing in it.

**Vouch already knows whether there is anything to say.** F18 reports what
the CV has gained *after* an application went out. So:

- **The tracker says when a row has gone quiet** — 10 days past the day it was
  marked sent, which sits after the median recruiter reply rather than before
  it. The sentence is "Quiet for 15 days", never "they have not replied": the
  app does not read anyone's inbox and will not imply that it does.
- **With nothing new, the app refuses to write.** No model call is made to
  reach that refusal; the screen says what would change it — a gap answered in
  the user's own words — and stops. This is the feature. It is also the
  moment the product's promise is easiest to break and every competitor breaks
  it.
- **With something new, the note is built from that and nothing else.** The
  lines written since the application went out are the only material the model
  sees; every paragraph cites the line it stands on and is verified like a
  cover-letter paragraph, with one repair attempt before it is dropped.
- **The note never writes a date.** The model is not told how long it has
  been — the screen says that, from the tracker's own record, and says which
  clock it counted on.
- Gated like the other three generated surfaces: `followup leakage ≤ 0` in
  `pnpm eval:adversarial`, against a sampler that invents a number and an
  employer in every note.

It completes the loop the product has been building all release: answer a gap
→ the CV gains a line → the app names the applications that line would change
→ and now, for the one that has gone quiet, it writes the only honest reason
to email a stranger again.

### F26 — Your profile, from your CV (v1.3)

Everything else this app writes is written *at* an employer. A professional
profile is the opposite shape: nobody commissions it, it has to be true of the
person on any day to any reader, and it is the text a recruiter searches
**before** a candidate has applied to anything.

Which is exactly why the category fills it with invention. "Passionate
engineer with a proven track record of driving impact" is written by a model
that was handed a job title and nothing else — the harm §2 names, moved from
the CV to the paragraph above it, where it sits on a public profile for years.

- Reached from the CV screen, beside the audit. **No posting is involved**,
  which also means there is no posting wording to lend the text a concept —
  the one licence the tailored bullets and the cover letter have. Every term
  has to come from a cited CV line, and the screen shows which.
- Two parts, in the order they are pasted: a headline under 120 characters,
  and a two-or-three paragraph About.
- **The headline comes back empty rather than invented**, and the screen says
  so. It is the shortest, most-read and most-fabricated line in this category;
  a profile carrying an unbacked one is worse than a profile with none. The
  About paragraphs that did survive are still shown — one half failing is not
  a reason to throw away the other.
- Gated like the other generated surfaces: `profile leakage ≤ 0` against a
  sampler that puts an award, an employer and a percentage into every headline
  it writes.

It is also the first thing in the product that is useful before the user has a
posting at all — the CV audit's neighbour, and the answer to "what do I put on
my profile" that does not require trusting a stranger's model with your career.

### Deferred (monthly maintenance releases)
LinkedIn headline/About tailoring, follow-up email drafts.

## 6. User flows

**First use (target ≤ 3 min):**
Open → Add your CV (upload/paste) → confirm preview → Paste a job posting → Run match → progress (requirements appear, evidence gets highlighted as it's found) → Match map → (optional) Tailor → Cover letter → Export.

**Repeat use (target ≤ 60 s):**
Open → New match → paste posting → Run match → result.

**From chat:**
`#vouch` + posting text → window opens with posting prefilled → Run match.

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
- **Cost:** ≤ 3 LLM calls and ≤ ~15k input tokens per **match** (`run_match`: extract + match, plus at most one retry). `tailor`, `letter`, `gaps` and `answer_question` are separate user actions, each a separate invoke with its own budget — `gaps` costs exactly one call, and none at all when the CV already proves everything; `answer_question` costs one call for up to five questions, and a second only when the verifier refused something. CV trimmed to 6k tokens, posting to 3k.
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
| Name/slug already taken on Anna | Low | Fallback slug `receipts-cv`; display name stays "Vouch". |

## 10. Monthly maintenance roadmap (program requirement)

| Month | Version | Meaningful improvement |
|---|---|---|
| October | v1.1 | **Shipped:** Gap questions (F9) — one question per unproven requirement, answered in the user's own words and appended to the CV as citable evidence — the CV audit (F10), which checks the CV the user arrived with before any posting, and the recurring report (F11), which is the first thing in the app that learns across applications |
| November | v1.2 | **Shipped:** the interview brief (F12) — what this application will be asked to back up, built from records that already exist; the comparison screen (F13), which answers which of several saved applications the CV can prove most of, before the evening is spent on one; the CV export (F14); and more than one CV (F15), which is what makes the cross-application screens honest for a career switcher. The profile tailoring planned here shipped in v1.3 as F26, written from the CV with no posting involved at all. |
| December | v1.3 | **Shipped, and every one of them modelless unless it writes:** the document check (F16), which turns the verifier on a CV or letter the app did not write; the line ledger (F17), which says what each CV line has actually carried; "Since you applied" (F18) and "Worth another look" (F24), which find the applications a later sentence would change — one at a time and across the shelf; the form answers (F19), which take the verifier to the last place in an application a human reads; the correction (F20), which lets a candidate answer the verdict back; the guard on the verdict itself (F21), which finally points the verifier at the primary function; the shareable card (F22), the first artefact built to leave the account; "What changed" (F23), which credits the sentence the user wrote for the gap it closed; and the follow-up (F25) with the tracker reminder that leads to it — the note after the silence, and the refusal to write one when nothing has changed; and the profile (F26), a headline and an About the CV can back — the November row's last promise, kept without a posting to borrow words from. |
| January | v1.4 | Verifier improvements from user reports; additional languages |

## 11. Submission package

- Published Anna Marketplace app (required).
- Open-source repo (MIT); `docs/` explains the architecture and the "Invent nothing" verifier.
- 90-second demo video (script in plan.md §10).
- DoraHacks BUIDL page: what it is, who it's for, how AI is used, how it connects to Anna. **Note:** a forum thread mentions a separate DoraHacks deadline of September 30 — confirm the date and requirements on your own BUIDL page.
