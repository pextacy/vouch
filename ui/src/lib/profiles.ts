/**
 * More than one CV, and which applications belong to which.
 *
 * A career switcher sends two different documents to two different kinds of
 * role. Until v1.2 the app held one CV, which was inconvenient for tailoring
 * and quietly wrong for everything that reads across applications: a recurring
 * report drawn from both careers names a gap that half the applications never
 * asked about, and tells someone to go and learn it.
 *
 * So a CV here is a workspace. Switching it switches the applications on
 * screen, and every match records the CV it was checked against — otherwise a
 * saved match would render its citations against whichever document happened
 * to be loaded, which is the quiet wrongness this product exists to prevent.
 *
 * Two rules keep the migration free of risk:
 *
 * * **The first CV never moves.** It stays under `cv:v1`, exactly where v1.0
 *   wrote it, and answers to the id `default`. Nothing has to be rewritten for
 *   an existing user, and a failed migration cannot lose the one document the
 *   whole app is about.
 * * **A missing id means the first CV.** Matches saved before v1.2 carry no
 *   `cv` field, and there was only one CV to make them against.
 *
 * Pure functions — no signals, no storage, no host (`tests/ui/profiles.spec.ts`).
 */

import type { CvProfile, TrackerEntry } from "./types";

/** The CV every account already has, and the key it has always lived under. */
export const DEFAULT_CV_ID = "default";

/**
 * How many CVs the app will keep.
 *
 * "Backend", "Data", "Management" is the real case; past that a CV set is a
 * filing cabinet, and every one of them is a document the user is supposed to
 * keep true.
 */
export const MAX_CV_PROFILES = 5;

/** Longer than this is a label nothing can render in a tab. */
export const MAX_CV_NAME = 40;

/** Where one profile's document lives. The first one never moved. */
export function cvKey(id: string): string {
  return id === DEFAULT_CV_ID ? "cv:v1" : `cv:v1:${id}`;
}

/**
 * A new id, unguessable enough never to collide with a stored one.
 *
 * `crypto.randomUUID` where it exists, because the id becomes a storage key
 * and a counter would reuse one after a delete — handing a new CV the matches
 * of the one it replaced.
 */
export function mintCvId(existing: CvProfile[]): string {
  const taken = new Set(existing.map((profile) => profile.id));
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const id =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? `cv-${crypto.randomUUID().slice(0, 8)}`
        : `cv-${Date.now().toString(36)}-${attempt}`;
    if (!taken.has(id)) return id;
  }
  return `cv-${Date.now().toString(36)}`;
}

/**
 * A name from the file the user uploaded.
 *
 * "dilek-aydin-backend.pdf" is already the user's own word for this CV, and it
 * beats "CV 2" by the only measure that matters here — whether they can tell
 * their two documents apart in a tab. Returns null when there is nothing to
 * read, and the caller supplies a numbered fallback from the string table.
 */
export function nameFromFilename(filename: string | null): string | null {
  if (!filename) return null;
  const stem = filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  return stem ? stem.slice(0, MAX_CV_NAME) : null;
}

/** Trim a name the user typed, or refuse it. */
export function cleanName(name: string): string | null {
  const clean = name.trim().replace(/\s+/g, " ").slice(0, MAX_CV_NAME);
  return clean || null;
}

/**
 * Read the stored set, repairing anything that cannot be rendered.
 *
 * Storage is the user's and it outlives every version of this code: an empty
 * list, an active id naming a CV that is gone, a duplicate — none of them are
 * worth a broken screen, and all of them resolve to "the CV they have".
 */
export function normalize(
  stored: { active?: string; list?: CvProfile[] } | null,
  fallbackName: string,
): { active: string; list: CvProfile[] } {
  const seen = new Set<string>();
  const list: CvProfile[] = [];
  for (const profile of stored?.list ?? []) {
    if (!profile?.id || seen.has(profile.id)) continue;
    seen.add(profile.id);
    list.push({
      id: profile.id,
      name: cleanName(profile.name ?? "") ?? fallbackName,
      created_at: profile.created_at ?? new Date(0).toISOString(),
    });
  }
  if (!list.some((profile) => profile.id === DEFAULT_CV_ID)) {
    list.unshift({
      id: DEFAULT_CV_ID,
      name: fallbackName,
      created_at: new Date(0).toISOString(),
    });
  }
  const active = stored?.active && seen.has(stored.active) ? stored.active : DEFAULT_CV_ID;
  return { active, list: list.slice(0, MAX_CV_PROFILES) };
}

/** The applications belonging to one CV. An entry with no id belongs to the first. */
export function forProfile(entries: TrackerEntry[], id: string): TrackerEntry[] {
  return entries.filter((entry) => (entry.cv ?? DEFAULT_CV_ID) === id);
}

/** What to call one, for a screen that has only the id. */
export function nameOf(list: CvProfile[], id: string, fallback: string): string {
  return list.find((profile) => profile.id === id)?.name ?? fallback;
}
