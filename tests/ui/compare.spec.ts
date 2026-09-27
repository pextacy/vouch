/**
 * Choosing between applications, and refusing to state a number that cannot be
 * true.
 *
 * This screen ranks someone's options, so a wrong row costs them an evening on
 * the wrong posting. Two things carry that weight: the selection, whose order
 * is the engine's tie-break and so must not reshuffle itself, and the guard
 * that keeps "5 of 3 must-haves evidenced" off the screen whatever the payload
 * says. The preview stub is exercised too, because preview mode is where the
 * screen is reviewed before anyone's real job search reaches it.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { connect } from "../../ui/src/lib/anna";
import { comparePostings } from "../../ui/src/lib/engine";
import {
  MAX_POSTINGS,
  MIN_POSTINGS,
  coherent,
  renderableColumns,
  toggleSelection,
} from "../../ui/src/lib/compare";
import { replayItems } from "../../ui/src/lib/recurring";
import { EXAMPLE_MATCH } from "../../ui/src/lib/example";
import type { CompareColumn, MatchResult, StoredMatch } from "../../ui/src/lib/types";

function stored(id: string, overrides: Partial<MatchResult> = {}): StoredMatch {
  return { match: { ...EXAMPLE_MATCH, id, ...overrides }, status: "drafted" };
}

function column(overrides: Partial<CompareColumn> = {}): CompareColumn {
  return {
    match: "m1",
    asked: 8,
    proved: 5,
    related: 1,
    must_asked: 5,
    must_proved: 3,
    blockers: ["Kafka"],
    edge: ["PostgreSQL"],
    ...overrides,
  };
}

beforeAll(async () => {
  await connect();
});

describe("toggleSelection", () => {
  it("adds one and keeps the order it was picked in", () => {
    expect(toggleSelection(["m1"], "m2")).toEqual(["m1", "m2"]);
  });

  it("removes one that is already picked", () => {
    expect(toggleSelection(["m1", "m2"], "m1")).toEqual(["m2"]);
  });

  it("refuses a fifth rather than dropping the one just picked", () => {
    const full = ["m1", "m2", "m3", "m4"];
    expect(full).toHaveLength(MAX_POSTINGS);
    expect(toggleSelection(full, "m5")).toBe(full);
  });

  it("still lets a picked one be removed when the selection is full", () => {
    expect(toggleSelection(["m1", "m2", "m3", "m4"], "m2")).toEqual(["m1", "m3", "m4"]);
  });
});

describe("coherent", () => {
  it("accepts a column whose counts fit the posting it came from", () => {
    expect(coherent(column())).toBe(true);
  });

  it("refuses more must-haves proved than asked for", () => {
    // The sentence the guard exists to prevent: "5 of 3 must-haves evidenced".
    expect(coherent(column({ must_asked: 3, must_proved: 5 }))).toBe(false);
  });

  it("refuses more verdicts than there were requirements", () => {
    expect(coherent(column({ asked: 4, proved: 4, related: 2 }))).toBe(false);
  });

  it("refuses more must-haves than requirements", () => {
    expect(coherent(column({ asked: 3, proved: 1, related: 0, must_asked: 4, must_proved: 1 }))).toBe(
      false,
    );
  });

  it("refuses a column that names no match, because nothing could open it", () => {
    expect(coherent(column({ match: "" }))).toBe(false);
  });
});

describe("renderableColumns", () => {
  it("keeps the engine's ranking", () => {
    const first = column({ match: "m1" });
    const second = column({ match: "m2" });

    expect(renderableColumns([first, second]).map((row) => row.match)).toEqual(["m1", "m2"]);
  });

  it("drops only what it cannot state", () => {
    const good = column({ match: "m1" });
    const impossible = column({ match: "m2", must_asked: 1, must_proved: 4 });

    expect(renderableColumns([good, impossible]).map((row) => row.match)).toEqual(["m1"]);
  });
});

describe("compare_postings, through the preview stub", () => {
  it("says nothing about a single application", async () => {
    const result = await comparePostings(replayItems([stored("m1")]));

    expect(result.postings).toBe(1);
    expect(result.columns).toEqual([]);
    expect(MIN_POSTINGS).toBe(2);
  });

  it("counts each posting's own verdicts", async () => {
    const result = await comparePostings(replayItems([stored("m1"), stored("m2")]));

    expect(result.postings).toBe(2);
    expect(result.columns).toHaveLength(2);
    for (const row of result.columns) {
      expect(row.asked).toBe(EXAMPLE_MATCH.requirements.length);
      expect(coherent(row)).toBe(true);
    }
  });

  it("names what every one of them asks for and none of them proves", async () => {
    const result = await comparePostings(replayItems([stored("m1"), stored("m2")]));

    // The example leaves Kafka unproven, and both replayed postings ask for it.
    expect(result.shared_gaps.map((group) => group.surface)).toContain(
      "Event streaming with Kafka",
    );
    for (const group of result.shared_gaps) {
      expect(group.asked).toBe(2);
      expect(group.unproven).toBe(2);
    }
  });

  it("puts the posting with fewer unproved must-haves first", async () => {
    const proved = stored("clear", {
      evidence: EXAMPLE_MATCH.evidence.map((item) => ({ ...item, status: "strong" as const })),
    });
    const result = await comparePostings(replayItems([stored("blocked"), proved]));

    expect(result.columns[0]?.match).toBe("clear");
    expect(result.columns[0]?.blockers).toEqual([]);
    expect(result.columns[1]?.blockers.length).toBeGreaterThan(0);
  });
});
