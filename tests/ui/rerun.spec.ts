/**
 * Pairing two runs of one posting, and the credit the app is allowed to take.
 *
 * This screen is where the product's whole answer loop reports back, which
 * makes both of its failure modes expensive. Pairing the wrong two
 * applications would put one posting's verdicts under another's requirements
 * and announce a gap closed that never was. And crediting the user's own
 * sentence for a gain it did not cause would be the same invention this app
 * refuses everywhere else, wearing a friendlier face.
 *
 * So the pairing is narrow — same recorded posting hash, same workspace,
 * older — and credit survives only while the line it points at still exists.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { connect } from "../../ui/src/lib/anna";
import { compareRuns } from "../../ui/src/lib/engine";
import { coherent, isEmpty, previousRun, renderable, renderableDiff } from "../../ui/src/lib/rerun";
import { EXAMPLE_CV, EXAMPLE_MATCH } from "../../ui/src/lib/example";
import type { CVDoc, MatchResult, RunChange, RunDiff, TrackerEntry } from "../../ui/src/lib/types";

const POSTING = "posting-hash-1";

function entry(id: string, overrides: Partial<TrackerEntry> = {}): TrackerEntry {
  return {
    id,
    company: "Northwind",
    role: "Backend Engineer",
    created_at: "2026-09-10T09:00:00+00:00",
    strong: 6,
    total: 8,
    status: "applied",
    posting: POSTING,
    ...overrides,
  };
}

function match(overrides: Partial<MatchResult> = {}): MatchResult {
  return {
    ...EXAMPLE_MATCH,
    id: "m-now",
    created_at: "2026-09-24T09:00:00+00:00",
    posting: { ...EXAMPLE_MATCH.posting, hash: POSTING },
    ...overrides,
  };
}

function change(overrides: Partial<RunChange> = {}): RunChange {
  return {
    key: "kafka",
    surface: "Kafka",
    kind: "must",
    before: "missing",
    after: "strong",
    direction: "gained",
    line_ids: ["L3"],
    credited: true,
    texts: ["Kafka in production"],
    ...overrides,
  };
}

function diff(overrides: Partial<RunDiff> = {}): RunDiff {
  return {
    version: 1,
    before_id: "m-then",
    after_id: "m-now",
    days_between: 14,
    before_strong: 5,
    before_total: 8,
    after_strong: 6,
    after_total: 8,
    added_between: ["L3"],
    gained: [change()],
    lost: [],
    still: [],
    differed: [],
    ...overrides,
  };
}

beforeAll(async () => {
  await connect();
});

describe("previousRun", () => {
  it("finds the most recent earlier run of the same posting", () => {
    const found = previousRun(
      [
        entry("m-old", { created_at: "2026-09-01T09:00:00+00:00" }),
        entry("m-then", { created_at: "2026-09-10T09:00:00+00:00" }),
      ],
      match(),
    );

    expect(found?.id).toBe("m-then");
  });

  it("ignores a run of a different posting", () => {
    expect(previousRun([entry("m-other", { posting: "another-hash" })], match())).toBeNull();
  });

  it("ignores a row that never recorded which posting it was", () => {
    // Every application saved before v1.3 is this one. Pairing on role and
    // company instead would put two different jobs at one employer together.
    expect(previousRun([entry("m-legacy", { posting: undefined })], match())).toBeNull();
  });

  it("ignores itself and anything newer", () => {
    const now = match();
    const entries = [
      entry(now.id, { created_at: now.created_at }),
      entry("m-later", { created_at: "2026-10-01T09:00:00+00:00" }),
    ];

    expect(previousRun(entries, now)).toBeNull();
  });

  it("answers null for the common case of a posting run once", () => {
    expect(previousRun([], match())).toBeNull();
  });
});

describe("coherent", () => {
  it("accepts a gain that actually improved", () => {
    expect(coherent(change({ before: "missing", after: "partial" }))).toBe(true);
  });

  it("refuses a gain whose verdicts did not move", () => {
    // "No evidence yet → no evidence yet" under a heading that says something
    // improved is the app telling someone their answer worked when it did not.
    expect(coherent(change({ before: "missing", after: "missing" }))).toBe(false);
  });

  it("refuses a loss that went the other way", () => {
    expect(coherent(change({ direction: "lost", before: "missing", after: "strong" }))).toBe(false);
  });

  it("checks the two half-asked shapes", () => {
    expect(coherent(change({ direction: "new_ask", before: null, after: "strong" }))).toBe(true);
    expect(coherent(change({ direction: "new_ask", before: "missing", after: "strong" }))).toBe(false);
    expect(coherent(change({ direction: "dropped_ask", before: "strong", after: null }))).toBe(true);
    expect(coherent(change({ direction: "dropped_ask", before: null, after: null }))).toBe(false);
  });
});

describe("renderable", () => {
  const cv: CVDoc = EXAMPLE_CV;

  it("drops a citation this CV no longer has", () => {
    const [row] = renderable([change({ line_ids: ["L3", "L99"] })], cv);

    expect(row?.line_ids).toEqual(["L3"]);
  });

  it("withdraws the credit when the line it stood on is gone", () => {
    // The claim is about one specific sentence. Without it there is nothing
    // left to credit, and "because of the line you added" would be a
    // congratulation with no receipt underneath.
    const [row] = renderable([change({ line_ids: ["L99"], credited: true })], cv);

    expect(row?.credited).toBe(false);
    expect(row?.line_ids).toEqual([]);
  });

  it("guards every list on the diff", () => {
    const checked = renderableDiff(
      diff({
        gained: [change({ before: "strong", after: "strong" })],
        lost: [change({ direction: "lost", before: "strong", after: "missing" })],
      }),
      cv,
    );

    expect(checked.gained).toEqual([]);
    expect(checked.lost).toHaveLength(1);
  });

  it("knows when a diff has nothing to say", () => {
    expect(isEmpty(diff({ gained: [] }))).toBe(true);
    expect(isEmpty(diff())).toBe(false);
  });
});

describe("compare_runs, through the preview stub", () => {
  const cv: CVDoc = {
    ...EXAMPLE_CV,
    hash: `${EXAMPLE_CV.hash}~e1`,
    lines: [
      ...EXAMPLE_CV.lines,
      {
        id: "L20",
        text: "Owned the Kafka consumer rewrite at Acme Payments.",
        section: "experience",
        added_at: "2026-09-18T10:00:00Z",
      },
    ],
  };

  const asked = (status: "missing" | "strong", lines: string[] = []): Partial<MatchResult> => ({
    requirements: [
      {
        id: "R1",
        text: "Event streaming with Kafka",
        kind: "must",
        category: "skill",
        source_quote: "Kafka",
      },
    ],
    evidence: [{ requirement_id: "R1", status, line_ids: lines, why: "" }],
    summary: { total: 1, strong: status === "strong" ? 1 : 0, partial: 0, missing: 0, must_missing: 0, sentence: "" },
  });

  it("credits the line written between the two runs", async () => {
    const result = await compareRuns({
      cv,
      before: match({ id: "m-then", created_at: "2026-09-10T09:00:00+00:00", ...asked("missing") }),
      after: match({ id: "m-now", ...asked("strong", ["L20"]) }),
    });

    expect(result.gained).toHaveLength(1);
    expect(result.gained[0]?.credited).toBe(true);
    expect(result.added_between).toEqual(["L20"]);
    expect(result.days_between).toBe(14);
  });

  it("takes no credit for a gain that stands on an older line", async () => {
    const result = await compareRuns({
      cv,
      before: match({ id: "m-then", created_at: "2026-09-10T09:00:00+00:00", ...asked("missing") }),
      after: match({ id: "m-now", ...asked("strong", ["L3"]) }),
    });

    expect(result.gained[0]?.credited).toBe(false);
  });

  it("reports a requirement that lost its evidence", async () => {
    const result = await compareRuns({
      cv,
      before: match({ id: "m-then", created_at: "2026-09-10T09:00:00+00:00", ...asked("strong", ["L3"]) }),
      after: match({ id: "m-now", ...asked("missing") }),
    });

    expect(result.lost).toHaveLength(1);
    expect(result.gained).toEqual([]);
  });
});
