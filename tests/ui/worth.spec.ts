/**
 * The shelf-wide scan, and the line it is allowed to count.
 *
 * Every row here sends someone to spend a model call on an application they
 * had already finished with, so the rule that decides a row is the rule worth
 * testing: only a sentence written *after* an application went out can make
 * it worth reopening. A line the match had already read cannot move anything,
 * and saying otherwise wastes the user's credits and their evening.
 *
 * The feed is tested too, because it is what carries the dates: the same
 * replay items the recurring report and the ledger read, now with the day
 * each application was run.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { connect } from "../../ui/src/lib/anna";
import { worthRerunning } from "../../ui/src/lib/engine";
import { replayItems } from "../../ui/src/lib/recurring";
import { EXAMPLE_CV, EXAMPLE_MATCH } from "../../ui/src/lib/example";
import type { CVDoc, MatchResult, StoredMatch } from "../../ui/src/lib/types";

const SENT_EARLY = "2026-09-10T09:00:00+00:00";
const SENT_LATE = "2026-09-22T09:00:00+00:00";

function stored(id: string, created_at: string, overrides: Partial<MatchResult> = {}): StoredMatch {
  return { match: { ...EXAMPLE_MATCH, id, created_at, ...overrides }, status: "applied" };
}

/** The CV, plus a sentence the user wrote on a given day. */
function cvWritten(at: string | null): CVDoc {
  if (at === null) return EXAMPLE_CV;
  return {
    ...EXAMPLE_CV,
    hash: `${EXAMPLE_CV.hash}~e1`,
    lines: [
      ...EXAMPLE_CV.lines,
      {
        id: "L20",
        text: "Owned the Kafka consumer rewrite at Acme Payments.",
        section: "experience",
        added_at: at,
      },
    ],
  };
}

beforeAll(async () => {
  await connect();
});

describe("the replay feed the scan reads", () => {
  it("carries the day each application was run", () => {
    const items = replayItems([stored("m1", SENT_EARLY)]);

    expect(items.every((item) => item.created_at === SENT_EARLY)).toBe(true);
  });
});

describe("worth_rerunning, through the preview stub", () => {
  it("names an application the CV has since gained an answer for", async () => {
    const result = await worthRerunning(
      cvWritten("2026-09-20T10:00:00Z"),
      replayItems([stored("m1", SENT_EARLY)]),
    );

    expect(result.applications).toBe(1);
    expect(result.written).toBe(1);
    expect(result.items.map((item) => item.match)).toEqual(["m1"]);
    const row = result.items[0];
    expect(row?.terms).toContain("Kafka");
    expect(row?.line_ids).toEqual(["L20"]);
    // The denominator travels with the claim.
    expect(row?.unproved).toBeGreaterThanOrEqual(row?.requirements ?? 0);
  });

  it("leaves alone an application sent after the line was written", async () => {
    // That match had the sentence in front of it and said what it said.
    const result = await worthRerunning(
      cvWritten("2026-09-20T10:00:00Z"),
      replayItems([stored("m2", SENT_LATE)]),
    );

    expect(result.items).toEqual([]);
    expect(result.applications).toBe(1);
  });

  it("says nothing at all until something has been written", async () => {
    const result = await worthRerunning(cvWritten(null), replayItems([stored("m1", SENT_EARLY)]));

    expect(result.written).toBe(0);
    expect(result.items).toEqual([]);
  });

  it("keeps one row per application, whatever it names", async () => {
    const result = await worthRerunning(
      cvWritten("2026-09-20T10:00:00Z"),
      replayItems([stored("m1", SENT_EARLY), stored("m2", SENT_EARLY)]),
    );

    expect(result.items).toHaveLength(2);
    expect(new Set(result.items.map((item) => item.match)).size).toBe(2);
  });

  it("counts every application it read, not only the ones it names", async () => {
    const result = await worthRerunning(
      cvWritten("2026-09-20T10:00:00Z"),
      replayItems([stored("m1", SENT_EARLY), stored("m2", SENT_LATE)]),
    );

    expect(result.applications).toBe(2);
    expect(result.items.map((item) => item.match)).toEqual(["m1"]);
  });
});
