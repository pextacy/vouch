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
import type {
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
const KEY_CV = "cv:v1";
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

export async function loadCv(): Promise<StoredCv | null> {
  return read<StoredCv>(KEY_CV);
}

export async function saveCv(cv: StoredCv): Promise<void> {
  await write(KEY_CV, cv);
}

export async function deleteCv(): Promise<void> {
  await remove(KEY_CV);
}

// ─── Matches ──────────────────────────────────────────────────────────

export async function loadIndex(): Promise<TrackerEntry[]> {
  return (await read<TrackerEntry[]>(KEY_INDEX)) ?? [];
}

export async function loadMatch(id: string): Promise<StoredMatch | null> {
  return read<StoredMatch>(KEY_MATCH(id));
}

export async function saveMatch(match: MatchResult): Promise<TrackerEntry[]> {
  const record: StoredMatch = { match, status: "drafted" };
  await write(KEY_MATCH(match.id), record);

  const entry: TrackerEntry = {
    id: match.id,
    company: match.posting.company,
    role: match.posting.title,
    created_at: match.created_at,
    strong: match.summary.strong,
    total: match.summary.total,
    status: "drafted",
  };
  const index = [entry, ...(await loadIndex()).filter((row) => row.id !== match.id)];
  const trimmed = index.slice(0, MAX_TRACKER_ENTRIES);
  for (const dropped of index.slice(MAX_TRACKER_ENTRIES)) {
    await remove(KEY_MATCH(dropped.id));
  }
  await write(KEY_INDEX, trimmed);
  return trimmed;
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

export async function setMatchStatus(
  id: string,
  status: ApplicationStatus,
): Promise<TrackerEntry[]> {
  const record = await loadMatch(id);
  if (record) await write(KEY_MATCH(id), { ...record, status });
  const index = (await loadIndex()).map((row) => (row.id === id ? { ...row, status } : row));
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
 * Remove the CV and every match. The profile stays so the app knows the
 * locale and does not re-run onboarding copy at someone who has seen it.
 */
export async function deleteEverything(): Promise<void> {
  const index = await loadIndex();
  for (const entry of index) {
    await remove(KEY_MATCH(entry.id));
  }
  await remove(KEY_INDEX);
  await remove(KEY_CV);
}
