/**
 * Replaying a job search, and refusing to state a number that cannot be true.
 *
 * The recurring screen makes claims about the user's whole history rather than
 * about one application, which raises the cost of being wrong: a bad number
 * here sends someone to spend their evening on the wrong gap. Two rules carry
 * that weight and both are tested below — every requirement is replayed, not
 * only the failures, and nothing renders whose counts exceed their own
 * denominator.
 */

import { describe, expect, it } from "vitest";

import { coherent, renderable, replayItems } from "../../ui/src/lib/recurring";
import { EXAMPLE_MATCH } from "../../ui/src/lib/example";
import type { MatchResult, RecurringGroup, StoredMatch } from "../../ui/src/lib/types";

function stored(id: string, overrides: Partial<MatchResult> = {}): StoredMatch {
  return { match: { ...EXAMPLE_MATCH, id, ...overrides }, status: "drafted" };
}

function group(overrides: Partial<RecurringGroup> = {}): RecurringGroup {
  return {
    key: "kafka",
    surface: "Kafka",
    kind: "must",
    asked: 3,
    unproven: 3,
    must: 3,
    ids: ["m1#R1", "m2#R1", "m3#R1"],
    texts: ["Event streaming with Kafka"],
    ...overrides,
  };
}

describe("replayItems", () => {
  /**
   * The denominator is the whole point. A term asked twenty times and proved
   * eighteen still leaves two unproven; sending only the failures would have
   * the engine report that as a recurring gap, telling someone their strongest
   * skill is what they should go and learn.
   */
  it("sends every requirement, proved ones included", () => {
    const items = replayItems([stored("m1")]);

    expect(items).toHaveLength(EXAMPLE_MATCH.requirements.length);
    expect(items.filter((item) => item.status === "strong").length).toBeGreaterThan(0);
  });

  it("carries the verdict each requirement actually got", () => {
    const items = replayItems([stored("m1")]);
    const byId = new Map(items.map((item) => [item.id, item.status]));

    // The example proves six of eight; R6 and R8 came back missing.
    expect(byId.get("m1#R1")).toBe("strong");
    expect(byId.get("m1#R6")).toBe("missing");
    expect(byId.get("m1#R8")).toBe("missing");
  });

  it("treats a requirement with no evidence entry as unproven", () => {
    // Records written by earlier versions can be short an entry, and silence
    // has never been evidence anywhere else in this app.
    const items = replayItems([stored("m1", { evidence: [] })]);

    expect(items.every((item) => item.status === "missing")).toBe(true);
  });

  it("keeps the match id as its own field, not only inside the item id", () => {
    // The engine counts distinct `match` values, so "asked in 7 applications"
    // means seven applications rather than seven bullets in one posting.
    const items = replayItems([stored("m1"), stored("m2")]);

    expect(new Set(items.map((item) => item.match))).toEqual(new Set(["m1", "m2"]));
    expect(items[0]?.id.startsWith(`${items[0]?.match}#`)).toBe(true);
  });

  it("carries each requirement's own wording and kind", () => {
    const kafka = replayItems([stored("m1")]).find((item) => item.id === "m1#R6");

    expect(kafka?.text).toBe("Event streaming with Kafka");
    expect(kafka?.kind).toBe("must");
  });

  it("returns nothing when there is nothing saved", () => {
    expect(replayItems([])).toEqual([]);
  });
});

describe("coherent", () => {
  it("accepts a group whose counts fit its sample", () => {
    expect(coherent(group(), 5)).toBe(true);
  });

  it("refuses a group asked in more applications than were read", () => {
    // This is the sentence the guard exists to prevent: "asked in 3
    // applications" under a report drawn from one.
    expect(coherent(group({ asked: 3 }), 1)).toBe(false);
  });

  it("refuses more unproven than asked", () => {
    expect(coherent(group({ asked: 2, unproven: 3 }), 5)).toBe(false);
  });

  it("refuses more must-haves than asked", () => {
    expect(coherent(group({ asked: 2, unproven: 2, must: 3 }), 5)).toBe(false);
  });

  it("refuses a group that was never asked", () => {
    expect(coherent(group({ asked: 0, unproven: 0, must: 0 }), 5)).toBe(false);
  });

  it("refuses a group with nothing to render", () => {
    // The screen prints `surface` as its heading and has no fallback.
    expect(coherent(group({ surface: "" }), 5)).toBe(false);
  });
});

describe("renderable", () => {
  it("keeps the engine's order", () => {
    const first = group({ key: "kafka" });
    const second = group({ key: "terraform", asked: 2, unproven: 2, must: 0 });

    expect(renderable([first, second], 5).map((item) => item.key)).toEqual([
      "kafka",
      "terraform",
    ]);
  });

  it("drops only what it cannot state", () => {
    const good = group({ key: "kafka" });
    const impossible = group({ key: "redis", asked: 9 });

    expect(renderable([good, impossible], 5).map((item) => item.key)).toEqual(["kafka"]);
  });
});
