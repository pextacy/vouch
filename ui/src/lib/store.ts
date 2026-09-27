/**
 * Everything the user owns, in their own Anna storage.
 *
 * Keys are versioned (docs/docs.md §7) so a schema change can migrate rather than
 * silently mis-read. In production `anna.storage.*` is APS-backed at
 * `scope=app`, so values survive window lifetimes and devices; in the local
 * harness they live in the window's 256 KB `runtime_state`, which is why match
 * records are stored one key per match instead of one big blob.
 *
 * Nothing here leaves the user's account, and nothing is logged.
 */

import { runtime, unwrap } from "./anna";
import { DEFAULT_CV_ID, cvKey } from "./profiles";
import type {
  Assertion,
  CvProfiles,
  ApplicationStatus,
  LetterResult,
  MatchResult,
  Profile,
  StoredCv,
  StoredMatch,
  TailorResult,
  TrackerEntry,
} from "./types";

const KEY_PROFILE = "profile:v1";
/**
 * The set of CVs and which one is in use.
 *
 * Absent for a user who only ever had one, which is why `cvKey(DEFAULT_CV_ID)`
 * is still `cv:v1`: nothing about their stored CV changed in v1.2.
 */
const KEY_CVS = "cvs:v1";
const KEY_INDEX = "matches:index:v1";
const KEY_MATCH = (id: string) => `match:v1:${id}`;

/** Tracker cap from docs/docs.md §7 — the oldest entries fall off the end. */
const MAX_TRACKER_ENTRIES = 300;

async function read<T>(key: string): Promise<T | null> {
  const anna = runtime();
  try {
    const response = unwrap<{ value?: unknown; exists?: boolean }>(await anna.storage.get({ key }));
    if (response?.exists === false) return null;
    const value = response?.value;
    return (value ?? null) as T | null;
  } catch {
    // A missing key resolves to null on some hosts and throws on others.
    return null;
  }
}

async function write(key: string, value: unknown): Promise<void> {
  const anna = runtime();
  await anna.storage.set({ key, value });
}

async function remove(key: string): Promise<void> {
  const anna = runtime();
  try {
    await anna.storage.delete({ key });
  } catch {
    // Deleting something that is already gone is the outcome we wanted.
  }
}

// ─── Profile ──────────────────────────────────────────────────────────

export async function loadProfile(): Promise<Profile | null> {
  return read<Profile>(KEY_PROFILE);
}

export async function saveProfile(profile: Profile): Promise<void> {
  await write(KEY_PROFILE, profile);
}

// ─── Master CV ────────────────────────────────────────────────────────

export async function loadCv(id: string = DEFAULT_CV_ID): Promise<StoredCv | null> {
  return read<StoredCv>(cvKey(id));
}

export async function saveCv(cv: StoredCv, id: string = DEFAULT_CV_ID): Promise<void> {
  await write(cvKey(id), cv);
}

export async function deleteCv(id: string = DEFAULT_CV_ID): Promise<void> {
  await remove(cvKey(id));
}

/**
 * The CV set. `null` means the account never needed one — one CV, where it has
 * always been — and the caller turns that into a single default entry.
 */
export async function loadCvProfiles(): Promise<CvProfiles | null> {
  return read<CvProfiles>(KEY_CVS);
}

export async function saveCvProfiles(profiles: CvProfiles): Promise<void> {
  await write(KEY_CVS, profiles);
}

// ─── Matches ──────────────────────────────────────────────────────────

export async function loadIndex(): Promise<TrackerEntry[]> {
  return (await read<TrackerEntry[]>(KEY_INDEX)) ?? [];
}

export async function loadMatch(id: string): Promise<StoredMatch | null> {
  return read<StoredMatch>(KEY_MATCH(id));
}

/**
 * Save a finished match, tagged with the CV it was checked against.
 *
 * The tag is what lets a second CV exist at all: without it the tracker could
 * not tell which applications belong to which document, and a saved match
 * would render its citations against whichever CV happened to be loaded.
 */
export async function saveMatch(
  match: MatchResult,
  cvId: string = DEFAULT_CV_ID,
): Promise<TrackerEntry[]> {
  const record: StoredMatch = { match, status: "drafted", cv: cvId };
  await write(KEY_MATCH(match.id), record);

  const entry: TrackerEntry = {
    id: match.id,
    company: match.posting.company,
    role: match.posting.title,
    created_at: match.created_at,
    // The posting's hash, so a second run of the same posting can find the
    // first one from the index alone. Without it, "what changed since you
    // last ran this" would cost a read of every record the user has.
    posting: match.posting.hash,
    strong: match.summary.strong,
    total: match.summary.total,
    status: "drafted",
    cv: cvId,
  };
  const index = [entry, ...(await loadIndex()).filter((row) => row.id !== match.id)];
  const trimmed = index.slice(0, MAX_TRACKER_ENTRIES);
  for (const dropped of index.slice(MAX_TRACKER_ENTRIES)) {
    await remove(KEY_MATCH(dropped.id));
  }
  await write(KEY_INDEX, trimmed);
  return trimmed;
}

/**
 * Every saved match, newest first, for the cross-application view.
 *
 * One read per match rather than one big blob: that is how matches are stored
 * (`KEY_MATCH`), because the local harness caps `runtime_state` at 256 KB. The
 * limit is what keeps this from becoming 300 sequential reads on a user who
 * has been applying for months — the recurring view is about what keeps coming
 * up lately, and a posting from eight months ago is not that.
 *
 * A record that fails to load is skipped rather than thrown: a partial answer
 * across the matches that did load is still true, and the alternative is one
 * corrupt key taking the whole screen down.
 */
export async function loadRecentMatches(
  limit: number,
  cvId: string = DEFAULT_CV_ID,
): Promise<StoredMatch[]> {
  // Only this CV's applications: a report that mixed two careers would name a
  // gap half of them never asked about (`lib/profiles`).
  const index = (await loadIndex())
    .filter((entry) => (entry.cv ?? DEFAULT_CV_ID) === cvId)
    .slice(0, limit);
  const records: StoredMatch[] = [];
  for (const entry of index) {
    try {
      const record = await loadMatch(entry.id);
      if (record) records.push(record);
    } catch {
      // See above: one unreadable match is not a reason to answer nothing.
    }
  }
  return records;
}

export async function attachTailor(id: string, tailor: TailorResult): Promise<void> {
  const record = await loadMatch(id);
  if (!record) return;
  await write(KEY_MATCH(id), { ...record, tailor });
}

export async function attachLetter(id: string, letter: LetterResult): Promise<void> {
  const record = await loadMatch(id);
  if (!record) return;
  await write(KEY_MATCH(id), { ...record, letter });
}

/**
 * Remember where the user said the match got it wrong.
 *
 * Written to the record beside the match, never into it: `match` is what the
 * engine produced and it stays that way, so reopening an application can
 * still show both verdicts side by side a month later.
 */
export async function attachAssertions(
  id: string,
  assertions: Record<string, Assertion>,
): Promise<void> {
  const record = await loadMatch(id);
  if (!record) return;
  await write(KEY_MATCH(id), { ...record, assertions });
}

/**
 * Remember which suggestions the user accepted, and how they edited them.
 *
 * Reopening a match reloads the suggestions from storage, so losing the
 * acceptance would ask the user to redo a review they already finished — and
 * an edited line they would then have to retype from memory.
 */
export async function attachAccepted(
  id: string,
  accepted: Record<string, string>,
): Promise<void> {
  const record = await loadMatch(id);
  if (!record) return;
  await write(KEY_MATCH(id), { ...record, accepted });
}

/**
 * Move an application along, and remember when.
 *
 * The date is the point. Until v1.3 the tracker knew an application was
 * *Applied* and not when it was sent, so nothing could say "you sent this
 * eleven days ago" — and the screen that tells someone an application is
 * worth another look is mostly a statement about time passing. Records
 * written before this stamp have no `status_at`, and that absence is
 * honoured rather than filled in: `since_applied` dates from the match
 * instead and says which clock it used.
 */
export async function setMatchStatus(
  id: string,
  status: ApplicationStatus,
): Promise<TrackerEntry[]> {
  const status_at = new Date().toISOString();
  const record = await loadMatch(id);
  if (record) await write(KEY_MATCH(id), { ...record, status, status_at });
  const index = (await loadIndex()).map((row) =>
    row.id === id ? { ...row, status, status_at } : row,
  );
  await write(KEY_INDEX, index);
  return index;
}

export async function deleteMatch(id: string): Promise<TrackerEntry[]> {
  await remove(KEY_MATCH(id));
  const index = (await loadIndex()).filter((row) => row.id !== id);
  await write(KEY_INDEX, index);
  return index;
}

/**
 * Delete one CV and the applications that were checked against it.
 *
 * The matches go with it rather than being left behind: a match whose CV is
 * gone would show its citations against a document that never contained those
 * lines, and an application the user cannot open is not a record they kept.
 * Returns what is left of the index.
 */
export async function deleteCvProfile(id: string): Promise<TrackerEntry[]> {
  const index = await loadIndex();
  const theirs = index.filter((entry) => (entry.cv ?? DEFAULT_CV_ID) === id);
  for (const entry of theirs) {
    await remove(KEY_MATCH(entry.id));
  }
  const kept = index.filter((entry) => (entry.cv ?? DEFAULT_CV_ID) !== id);
  await write(KEY_INDEX, kept);
  await deleteCv(id);
  return kept;
}

/**
 * Remove every CV and every match. The profile stays so the app knows the
 * locale and does not re-run onboarding copy at someone who has seen it.
 */
export async function deleteEverything(ids: string[] = [DEFAULT_CV_ID]): Promise<void> {
  const index = await loadIndex();
  for (const entry of index) {
    await remove(KEY_MATCH(entry.id));
  }
  await remove(KEY_INDEX);
  for (const id of ids.length > 0 ? ids : [DEFAULT_CV_ID]) {
    await deleteCv(id);
  }
  await remove(KEY_CVS);
}
