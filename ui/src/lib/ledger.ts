/**
 * Refusing to put a receipt under the wrong sentence.
 *
 * The ledger tells someone which lines of their CV to lead with and which
 * have never been needed. Both halves are advice about the document itself,
 * which raises the cost of being wrong past what the other cross-application
 * screens carry: a bad number in the recurring report sends someone to study
 * the wrong thing for an evening, and a bad number here has them delete a
 * sentence that has carried five applications.
 *
 * So nothing renders unless it can be true. The engine computes these counts
 * and in production they always hold — this is the guard that no payload, no
 * stub and no future caller can put "cited in 5 of 3 applications" on screen,
 * the same rule `recurring.coherent` enforces there.
 *
 * The second guard is about the CV in front of the user. A line id is a
 * position, and a row whose id this document does not have would render as an
 * empty line with a number beside it — the screen quietly claiming a sentence
 * exists. The engine drops those already; this is the belt to that braces.
 *
 * Pure functions — no signals, no storage, no host (`tests/ui/ledger.spec.ts`).
 */

import type { CVDoc, LedgerLine, LedgerResult } from "./types";

/**
 * Applications the ledger needs before it will rank anything.
 *
 * Mirrors `ledger.MIN_MATCHES`, and only to choose which sentence the screen
 * shows — the rule itself is enforced in one place, in the engine. Two
 * applications cannot say which line does the work; they can only say which
 * line the last two postings happened to ask about.
 */
export const MIN_MATCHES = 3;

/** Whether a row's numbers can be true of the applications they came from. */
export function coherent(line: LedgerLine, applications: number): boolean {
  return (
    line.applications >= 0 &&
    line.applications <= applications &&
    // One application can cite the same line for two requirements, so
    // citations run ahead of applications and never behind them.
    line.citations >= line.applications &&
    line.must <= line.citations &&
    line.decisive <= line.must
  );
}

/** Rows the screen is willing to state. Order is the engine's. */
export function renderable(
  lines: LedgerLine[],
  applications: number,
  cv: CVDoc | null,
): LedgerLine[] {
  const known = new Set((cv?.lines ?? []).map((line) => line.id));
  return lines.filter((line) => known.has(line.id) && coherent(line, applications));
}

/**
 * Everything the screen states, checked in one pass.
 *
 * Done here rather than in three call sites so that a list added later cannot
 * quietly skip the guard.
 */
export function renderableResult(result: LedgerResult, cv: CVDoc | null): LedgerResult {
  return {
    ...result,
    working: renderable(result.working, result.applications, cv),
    idle: renderable(result.idle, result.applications, cv),
    added: renderable(result.added, result.applications, cv),
  };
}

/**
 * How many lines the CV has that the ledger could never credit.
 *
 * The header is a name, an email and a city: never evidence, so never idle
 * either. The engine leaves it out of `eligible`, and the screen needs the
 * same number to say "14 of your 23 lines" about the document on screen.
 */
export function eligibleLines(cv: CVDoc | null): number {
  return (cv?.lines ?? []).filter((line) => line.section !== "header").length;
}
