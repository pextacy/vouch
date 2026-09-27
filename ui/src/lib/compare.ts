/**
 * Choosing which saved applications to line up, and refusing to render a
 * column whose numbers cannot be true.
 *
 * The comparison itself is lexicon work and happens in the engine
 * (`compare_postings`), reading the same replay feed as the recurring view —
 * every requirement with the verdict it got. This file is the half that stays
 * in the UI: which matches are selected, and the guard that keeps a payload
 * from putting "5 of 3 must-haves evidenced" in front of someone.
 *
 * Pure functions — no signals, no storage, no host (`tests/ui/compare.spec.ts`).
 */

import type { CompareColumn } from "./types";

/** Mirrors `compare.MIN_POSTINGS`: one posting is not a comparison. */
export const MIN_POSTINGS = 2;

/**
 * Mirrors `compare.MAX_POSTINGS`.
 *
 * Four rows still read at 360 px. The rule lives in the engine; this copy only
 * decides when a checkbox stops accepting a fifth.
 */
export const MAX_POSTINGS = 4;

/**
 * How many are selected by default when the screen opens.
 *
 * The two most recent, because that is the comparison someone almost always
 * means — and an answer on arrival beats an empty form asking them to build
 * one before the screen says anything at all.
 */
export const DEFAULT_POSTINGS = 2;

/**
 * Add or remove one match from the selection.
 *
 * Order is the order they were picked, and the engine breaks an exact tie by
 * it, so a selection that reorders itself would reorder the answer with it.
 */
export function toggleSelection(selection: string[], id: string): string[] {
  if (selection.includes(id)) return selection.filter((entry) => entry !== id);
  if (selection.length >= MAX_POSTINGS) return selection;
  return [...selection, id];
}

/**
 * Whether a column's numbers can be true of the requirements it came from.
 *
 * The engine computes these and in production they always hold. This exists so
 * that a payload which disagrees — a stub, a stale record, a future caller
 * that batches differently — cannot state something false about someone's job
 * search on the screen they are using to decide where to spend an evening.
 * It is the same guard `recurring.coherent` is, for the same reason.
 */
export function coherent(column: CompareColumn): boolean {
  return (
    column.match.length > 0 &&
    column.asked >= 0 &&
    column.proved >= 0 &&
    column.related >= 0 &&
    column.proved + column.related <= column.asked &&
    column.must_asked <= column.asked &&
    column.must_proved <= column.must_asked
  );
}

/** Columns the screen is willing to state. Order is the engine's ranking. */
export function renderableColumns(columns: CompareColumn[]): CompareColumn[] {
  return columns.filter(coherent);
}
