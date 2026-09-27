/**
 * When an application has gone quiet, and when saying so is honest.
 *
 * The app knows one thing about a sent application and does not know the
 * other. It knows the day the user marked it *Applied*; it does not know
 * whether anyone replied, because nothing in this product reads anyone's
 * inbox. So the reminder is written to say only the first: *"Marked applied
 * 14 days ago."* — never "they haven't replied", which would be the app
 * inventing the one fact it cannot see.
 *
 * The threshold is a judgement and it is a deliberate one. Recruiters take
 * one to two weeks on a normal pipeline, so a nudge before that would push
 * people into sending the email that annoys the reader — the exact email
 * `pipeline/followup.py` refuses to write. Ten working days is roughly two
 * weeks of real time and sits after the median, not before it.
 *
 * Pure functions — no signals, no storage, no host (`tests/ui/followup.spec.ts`).
 */

import type { TrackerEntry } from "./types";

/** Days of silence before the tracker says anything at all. */
export const QUIET_DAYS = 10;

/** Statuses where a follow-up is a sensible thing to be offered. */
const OPEN: ReadonlySet<TrackerEntry["status"]> = new Set(["applied", "interview"]);

/**
 * Whole days since the row last moved, or `null` when the app cannot say.
 *
 * A row written before v1.3 carries no `status_at`, and `created_at` is the
 * day the *match* was run rather than the day it was sent — a different fact.
 * Rather than dress one up as the other, this returns null and the tracker
 * stays quiet: the screen that opens from here says which clock it counted
 * on, and a reminder cannot.
 */
export function daysSilent(entry: TrackerEntry, now: number = Date.now()): number | null {
  if (!OPEN.has(entry.status) || !entry.status_at) return null;
  const moment = Date.parse(entry.status_at);
  if (Number.isNaN(moment)) return null;
  return Math.max(0, Math.floor((now - moment) / 86_400_000));
}

/** Whether this row has been quiet long enough to be worth mentioning. */
export function hasGoneQuiet(entry: TrackerEntry, now: number = Date.now()): boolean {
  const days = daysSilent(entry, now);
  return days !== null && days >= QUIET_DAYS;
}
