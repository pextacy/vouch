/**
 * Finding the earlier run of a posting, and refusing to state a change twice.
 *
 * Four screens ask the user to write a sentence into their CV, and the last
 * of them ends in "run this posting again". This is the bookkeeping behind
 * the screen that finally answers whether that worked: which saved
 * application is the *previous* run of the one on screen.
 *
 * The rule is deliberately narrow. Two runs pair only when the index recorded
 * the same posting hash for both, they belong to the same CV workspace, and
 * the other one is older. Rows written before v1.3 carry no posting hash at
 * all, and those are left alone rather than guessed at by role and company —
 * two applications to "Backend Engineer" at the same company can be two
 * different postings, and pairing them would put one posting's verdicts under
 * another's requirements.
 *
 * Pure functions — no signals, no storage, no host (`tests/ui/rerun.spec.ts`).
 */

import type { CVDoc, MatchResult, RunChange, RunDiff, TrackerEntry } from "./types";

/**
 * The run of this posting that came before the one on screen.
 *
 * `null` is the common answer — most applications are run once — and the
 * screen is built for it: no banner, no empty state, nothing.
 */
export function previousRun(entries: TrackerEntry[], match: MatchResult): TrackerEntry | null {
  const candidates = entries.filter(
    (entry) =>
      entry.id !== match.id &&
      entry.posting !== undefined &&
      entry.posting === match.posting.hash &&
      entry.created_at < match.created_at,
  );
  // The index is newest-first, but a record repaired or re-saved out of order
  // would break that assumption quietly, so the newest is chosen rather than
  // assumed.
  return candidates.reduce<TrackerEntry | null>(
    (newest, entry) => (!newest || entry.created_at > newest.created_at ? entry : newest),
    null,
  );
}

/**
 * Whether a row can be true of the two runs it came from.
 *
 * The engine computes these and in production they hold; this is the guard
 * that no payload — a stub, a stale cache, a future caller — can put "no
 * evidence → no evidence" under a heading that says something improved, or
 * claim the user's sentence caused a change the citation does not show.
 */
export function coherent(change: RunChange): boolean {
  const rank = { missing: 0, partial: 1, strong: 2 } as const;
  const before = change.before ? rank[change.before] : null;
  const after = change.after ? rank[change.after] : null;

  switch (change.direction) {
    case "gained":
      return before !== null && after !== null && after > before;
    case "lost":
      return before !== null && after !== null && after < before;
    case "same":
      return before !== null && after !== null && after === before;
    case "new_ask":
      return before === null && after !== null;
    case "dropped_ask":
      return before !== null && after === null;
    default:
      return false;
  }
}

/**
 * Rows the screen is willing to state.
 *
 * Also drops a citation the CV no longer has: the screen quotes the line
 * under the change, and a number with an empty quotation beneath it is the
 * app claiming a sentence exists.
 */
export function renderable(changes: RunChange[], cv: CVDoc | null): RunChange[] {
  const known = new Set((cv?.lines ?? []).map((line) => line.id));
  return changes
    .filter(coherent)
    .map((change) => ({ ...change, line_ids: change.line_ids.filter((id) => known.has(id)) }))
    // Credit is a claim about a specific line. If that line is gone from the
    // CV, the claim has nothing left to stand on.
    .map((change) => (change.credited && change.line_ids.length === 0
      ? { ...change, credited: false }
      : change));
}

/** Every list on the diff, checked in one pass so a new one cannot skip it. */
export function renderableDiff(diff: RunDiff, cv: CVDoc | null): RunDiff {
  return {
    ...diff,
    gained: renderable(diff.gained, cv),
    lost: renderable(diff.lost, cv),
    still: renderable(diff.still, cv),
    differed: renderable(diff.differed, cv),
  };
}

/** Whether the diff found anything at all worth a screen. */
export function isEmpty(diff: RunDiff): boolean {
  return (
    diff.gained.length === 0 &&
    diff.lost.length === 0 &&
    diff.still.length === 0 &&
    diff.differed.length === 0
  );
}
