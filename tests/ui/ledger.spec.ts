/**
 * The ledger's two ways of being wrong about someone's own document.
 *
 * This screen says which sentences of a CV to lead with and which have never
 * been needed, which makes a bad number more expensive here than anywhere
 * else in the app: a wrong row in the recurring report costs an evening of
 * studying, and a wrong row here has someone delete a line that carried five
 * applications. So nothing renders whose counts cannot be true, and nothing
 * renders that names a line this CV does not have.
 *
 * The replay feed is tested here too, because it is what makes the counting
 * possible at all: the same items the recurring report reads, now carrying
 * the citations and the CV each verdict was made against.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { connect } from "../../ui/src/lib/anna";
import { lineLedger } from "../../ui/src/lib/engine";
import {
  MIN_MATCHES,
  coherent,
  eligibleLines,
  renderable,
  renderableResult,
} from "../../ui/src/lib/ledger";
import { replayItems } from "../../ui/src/lib/recurring";
import { EXAMPLE_CV, EXAMPLE_MATCH } from "../../ui/src/lib/example";
import type { CVDoc, LedgerLine, LedgerResult, MatchResult, StoredMatch } from "../../ui/src/lib/types";

function stored(id: string, overrides: Partial<MatchResult> = {}): StoredMatch {
  return { match: { ...EXAMPLE_MATCH, id, ...overrides }, status: "drafted" };
}

function line(overrides: Partial<LedgerLine> = {}): LedgerLine {
  return {
    id: "L3",
    applications: 3,
    citations: 4,
    must: 3,
    decisive: 2,
    proves: ["Kubernetes"],
    added: false,
    ...overrides,
  };
}

function result(overrides: Partial<LedgerResult> = {}): LedgerResult {
  return {
    version: 1,
    applications: 3,
    skipped: 0,
    eligible: 8,
    cited: 1,
    working: [line()],
    idle: [line({ id: "L4", applications: 0, citations: 0, must: 0, decisive: 0, proves: [] })],
    added: [],
    ...overrides,
  };
}

beforeAll(async () => {
  await connect();
});

describe("the replay feed the ledger reads", () => {
  it("carries the lines each verdict cited", () => {
    const items = replayItems([stored("m1")]);
    const cited = items.filter((item) => item.line_ids.length > 0);

    expect(cited.length).toBeGreaterThan(0);
    // The ids are the whole point: a count of verdicts cannot say which
    // sentence of the CV did the answering.
    expect(cited[0]?.line_ids[0]).toMatch(/^L\d+$/);
  });

  it("records which CV each application was checked against", () => {
    const items = replayItems([stored("m1", { cv_hash: "a-particular-parse" })]);

    expect(items.every((item) => item.cv_hash === "a-particular-parse")).toBe(true);
  });

  it("leaves the citations empty when a requirement has no evidence entry", () => {
    const items = replayItems([stored("m1", { evidence: [] })]);

    expect(items.every((item) => item.line_ids.length === 0)).toBe(true);
  });
});

describe("coherent", () => {
  it("accepts a row whose numbers fit the applications it came from", () => {
    expect(coherent(line(), 3)).toBe(true);
  });

  it("accepts a line nothing has ever cited", () => {
    expect(coherent(line({ applications: 0, citations: 0, must: 0, decisive: 0 }), 3)).toBe(true);
  });

  it("refuses a line cited in more applications than were read", () => {
    // "Evidence in 5 of your 3 applications" is not a rounding problem; it is
    // the app stating something false about someone's job search.
    expect(coherent(line({ applications: 5 }), 3)).toBe(false);
  });

  it("refuses fewer citations than applications", () => {
    // One application can cite a line twice, so citations run ahead of
    // applications and never behind them.
    expect(coherent(line({ applications: 3, citations: 2 }), 3)).toBe(false);
  });

  it("refuses more must-haves than citations, and more decisive than must", () => {
    expect(coherent(line({ must: 9 }), 3)).toBe(false);
    expect(coherent(line({ decisive: 4, must: 3 }), 3)).toBe(false);
  });
});

describe("renderable", () => {
  it("drops a row naming a line this CV does not have", () => {
    // The screen renders the sentence from the CV beside the count. A row for
    // a line that is gone would print a number under an empty quotation.
    const rows = renderable([line({ id: "L3" }), line({ id: "L99" })], 3, EXAMPLE_CV);

    expect(rows.map((row) => row.id)).toEqual(["L3"]);
  });

  it("keeps the engine's order", () => {
    const rows = renderable([line({ id: "L5" }), line({ id: "L3" })], 3, EXAMPLE_CV);

    expect(rows.map((row) => row.id)).toEqual(["L5", "L3"]);
  });

  it("states nothing at all without a CV to check against", () => {
    expect(renderable([line()], 3, null)).toEqual([]);
  });

  it("guards every list on the result, not only the first", () => {
    const checked = renderableResult(
      result({
        working: [line({ applications: 9 })],
        idle: [line({ id: "L99", applications: 0, citations: 0, must: 0, decisive: 0 })],
        added: [line({ id: "L4" })],
      }),
      EXAMPLE_CV,
    );

    expect(checked.working).toEqual([]);
    expect(checked.idle).toEqual([]);
    expect(checked.added.map((row) => row.id)).toEqual(["L4"]);
  });
});

describe("eligibleLines", () => {
  it("counts everything but the header", () => {
    // A name and a city are never evidence, so they are never idle either.
    expect(eligibleLines(EXAMPLE_CV)).toBe(EXAMPLE_CV.lines.length - 1);
  });

  it("answers zero without a CV", () => {
    expect(eligibleLines(null)).toBe(0);
  });
});

describe("line_ledger, through the preview stub", () => {
  const cv: CVDoc = EXAMPLE_CV;
  const feed = (ids: string[]) =>
    ids.flatMap((id) => replayItems([stored(id, { cv_hash: cv.hash })]));

  it("says nothing from two applications", async () => {
    const report = await lineLedger(cv, feed(["m1", "m2"]));

    expect(report.applications).toBe(2);
    expect(report.working).toEqual([]);
    expect(MIN_MATCHES).toBe(3);
  });

  it("counts the applications each line carried", async () => {
    const report = await lineLedger(cv, feed(["m1", "m2", "m3"]));

    expect(report.applications).toBe(3);
    expect(report.working.length).toBeGreaterThan(0);
    expect(report.working[0]?.applications).toBe(3);
    // Every row is true of the sample, which is what the screen will state.
    expect(report.working.every((row) => coherent(row, report.applications))).toBe(true);
  });

  it("leaves out an application checked against another parse of the CV", async () => {
    const report = await lineLedger(cv, [
      ...feed(["m1", "m2", "m3"]),
      ...replayItems([stored("old", { cv_hash: "a-different-parse" })]),
    ]);

    expect(report.applications).toBe(3);
    // Said out loud rather than swallowed: a quietly smaller denominator is
    // the one way this screen could mislead without stating anything false.
    expect(report.skipped).toBe(1);
  });

  it("lists a line no posting ever asked about", async () => {
    const report = await lineLedger(cv, feed(["m1", "m2", "m3"]));
    const cited = new Set(report.working.map((row) => row.id));

    expect(report.idle.length).toBeGreaterThan(0);
    expect(report.idle.every((row) => !cited.has(row.id))).toBe(true);
    expect(report.idle.every((row) => row.applications === 0)).toBe(true);
  });
});
