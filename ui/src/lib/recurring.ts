/**
 * Replaying every past application so the engine can say what they had in
 * common.
 *
 * Every other screen in this app is about one application. The recurring view
 * is the only one that reads across them, and it can only be honest because
 * each saved match already carries a verified per-requirement verdict.
 *
 * The work splits in two. Deciding that "Experience running services on
 * Kubernetes" and "Kubernetes in production" are the same thing is lexicon
 * work and happens in the engine (`recurring_gaps`). This file is the other
 * half: getting the whole history out of storage in the shape the engine
 * needs, and refusing to render a group whose numbers cannot be true.
 *
 * **Every requirement is sent, not only the unproven ones.** Without the
 * denominator a count says nothing: a term asked in twenty applications and
 * proved in eighteen still leaves two unproven, and reporting that as a
 * recurring gap would tell someone their strongest skill is what they should
 * go and learn. The engine needs to see the proved ones to know better.
 *
 * Pure functions — no signals, no storage, no host (`tests/ui/recurring.spec.ts`).
 */

import type { Kind, LineId, RecurringGroup, Status, StoredMatch } from "./types";

/**
 * How many matches the view reads.
 *
 * The recurring view is about what keeps coming up *lately*. Reading all 300 a
 * user may have saved would be 300 sequential storage reads for an answer a
 * posting from eight months ago only makes less true.
 */
export const RECENT_MATCHES = 40;

/**
 * Below this the engine returns no groups at all.
 *
 * Mirrors `recurring.MIN_MATCHES`, and only to choose which sentence the
 * screen shows — the rule itself is enforced in one place, in the engine.
 */
export const MIN_MATCHES = 3;

/** One requirement from one past application, as the engine wants it. */
export interface ReplayItem {
  /** `"<match_id>#<req_id>"` — opaque to the engine. */
  id: string;
  /** Opaque grouping key; the engine only counts distinct values. */
  match: string;
  text: string;
  kind: Kind;
  status: Status;
  /**
   * The CV lines this requirement was matched to.
   *
   * Read by `line_ledger` alone — the recurring report and the comparison
   * count verdicts and never look at them. One feed rather than three: a
   * second builder projecting the same stored matches is a second thing that
   * can drift, and all three screens have to agree about what was asked.
   */
  line_ids: LineId[];
  /**
   * When this application was run.
   *
   * Read by `worth_rerunning` alone, which needs to know which of the user's
   * own lines each application could not possibly have seen.
   */
  created_at: string;
  /**
   * The CV this application was checked against.
   *
   * Also the ledger's alone, and it is what keeps that screen honest: a line
   * id is a position, so `L12` in a re-parsed CV is a different sentence and
   * its receipts are not this document's.
   */
  cv_hash: string;
}

/**
 * Every requirement from every match read, with the verdict it got.
 *
 * All of them, deliberately: see the note at the top of this file. A
 * requirement with no evidence entry counts as `missing`, which is what
 * "nothing was proven" means everywhere else in the app.
 */
export function replayItems(records: StoredMatch[]): ReplayItem[] {
  const items: ReplayItem[] = [];
  for (const record of records) {
    const evidence = new Map(
      record.match.evidence.map((item) => [item.requirement_id, item]),
    );
    for (const requirement of record.match.requirements) {
      const found = evidence.get(requirement.id);
      items.push({
        id: `${record.match.id}#${requirement.id}`,
        match: record.match.id,
        text: requirement.text,
        kind: requirement.kind,
        status: found?.status ?? "missing",
        line_ids: found?.line_ids ?? [],
        created_at: record.match.created_at,
        cv_hash: record.match.cv_hash,
      });
    }
  }
  return items;
}

/**
 * Whether a group's numbers can be true of the sample it came from.
 *
 * The engine computes these and in production they always hold. This exists so
 * that a payload which disagrees — a stub, a stale cache, a future caller that
 * batches differently — cannot put "unproven in 3 of 1 applications" on screen.
 * A count larger than its own denominator is not a rounding problem; it is the
 * app stating something false about someone's job search.
 */
export function coherent(group: RecurringGroup, matches: number): boolean {
  return (
    group.asked > 0 &&
    group.asked <= matches &&
    group.unproven <= group.asked &&
    group.must <= group.asked &&
    group.surface.length > 0
  );
}

/** Groups the screen is willing to state. Order is the engine's. */
export function renderable(groups: RecurringGroup[], matches: number): RecurringGroup[] {
  return groups.filter((group) => coherent(group, matches));
}
