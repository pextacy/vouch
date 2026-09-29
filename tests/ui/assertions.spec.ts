/**
 * When the user says the match got it wrong.
 *
 * The feature is one sentence — *the app's verdict and the candidate's are
 * never the same thing* — and every test here is a way that sentence could
 * quietly stop being true:
 *
 * * the correction must not edit `match.evidence`, or a month later the
 *   record can no longer answer what the app actually found;
 * * it must not move the summary counts, which are what the user screenshots;
 * * it must invalidate the interview brief, because a stale one would tell
 *   somebody the app agreed with them;
 * * and the read-only example must refuse it, like every other write.
 */

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const attachAssertions = vi.fn(async () => undefined);
const loadMatch = vi.fn(async () => null as unknown);

vi.mock("../../ui/src/lib/store", () => ({
  loadProfile: vi.fn(async () => null),
  saveProfile: vi.fn(async () => undefined),
  loadCv: vi.fn(async () => null),
  saveCv: vi.fn(async () => undefined),
  deleteCv: vi.fn(async () => undefined),
  loadCvProfiles: vi.fn(async () => null),
  saveCvProfiles: vi.fn(async () => undefined),
  deleteCvProfile: vi.fn(async () => []),
  loadIndex: vi.fn(async () => []),
  loadMatch,
  loadRecentMatches: vi.fn(async () => []),
  saveMatch: vi.fn(async () => []),
  attachTailor: vi.fn(async () => undefined),
  attachLetter: vi.fn(async () => undefined),
  attachAccepted: vi.fn(async () => undefined),
  attachAssertions,
  setMatchStatus: vi.fn(async () => []),
  deleteMatch: vi.fn(async () => []),
  deleteEverything: vi.fn(async () => undefined),
}));

const { connect } = await import("../../ui/src/lib/anna");
const { parseCvText } = await import("../../ui/src/lib/engine");
const { EXAMPLE_MATCH } = await import("../../ui/src/lib/example");
const state = await import("../../ui/src/state");

const CV_TEXT = [
  "Maya Collins — Backend Engineer",
  "Experience",
  "Acme Payments — Backend Engineer, 2018-2024",
  "Built payment reconciliation services in Go for 1,200 merchant accounts.",
  "Migrated the reporting pipeline from MySQL to PostgreSQL with zero downtime.",
  "Ran the nightly settlement batch on our own scheduler.",
  "Led a team of 4 engineers and owned the on-call rotation.",
  "Education",
  "MSc Computer Science, University of Edinburgh, 2016",
].join("\n");

/** Real ids from the parsed fixture, rather than ones assumed off the page. */
let lineA = "L1";
let lineB = "L2";

beforeAll(async () => {
  await connect();
  const doc = await parseCvText(CV_TEXT);
  state.cv.value = { doc, filename: null, updated_at: new Date().toISOString() };
  const scheduler = doc.lines.find((line) => line.text.includes("scheduler"));
  const team = doc.lines.find((line) => line.text.includes("team of 4"));
  if (!scheduler || !team) throw new Error("fixture CV did not parse as expected");
  lineA = scheduler.id;
  lineB = team.id;
});

beforeEach(() => {
  attachAssertions.mockClear();
  attachAssertions.mockResolvedValue(undefined);
  state.error.value = null;
  state.showingExample.value = false;
  state.assertions.value = {};
  state.asserting.value = null;
  state.briefResult.value = null;
  state.currentMatch.value = { ...EXAMPLE_MATCH, id: "m-local" };
});

const firstRequirement = () => EXAMPLE_MATCH.requirements[0]!.id;

describe("assertEvidence", () => {
  it("records the lines the user picked, with when they said so", async () => {
    await state.assertEvidence(firstRequirement(), [lineA, lineB]);

    const stored = state.assertions.value[firstRequirement()];
    expect(stored?.line_ids).toEqual([lineA, lineB]);
    expect(stored?.at).toBeTruthy();
    expect(attachAssertions).toHaveBeenCalledWith("m-local", state.assertions.value);
  });

  it("never edits the verdict the engine produced", async () => {
    const before = JSON.stringify(state.currentMatch.value);

    await state.assertEvidence(firstRequirement(), [lineA]);

    expect(JSON.stringify(state.currentMatch.value)).toBe(before);
  });

  it("leaves the summary the user screenshots alone", async () => {
    const before = { ...state.currentMatch.value!.summary };

    await state.assertEvidence(firstRequirement(), [lineA]);

    expect(state.currentMatch.value!.summary).toEqual(before);
  });

  it("throws away a brief built before the correction", async () => {
    state.briefResult.value = { version: 1, match_id: "m-local", cv_hash: "x", cv_changed: false, risks: [], proved: [], loose_claims: [] };

    await state.assertEvidence(firstRequirement(), [lineA]);

    expect(state.briefResult.value).toBeNull();
    expect(state.briefPhase.value).toBe("idle");
  });

  it("closes the picker once the lines are recorded", async () => {
    state.asserting.value = firstRequirement();

    await state.assertEvidence(firstRequirement(), [lineA]);

    expect(state.asserting.value).toBeNull();
  });

  it("takes an assertion back when the user picks nothing", async () => {
    await state.assertEvidence(firstRequirement(), [lineA]);
    await state.assertEvidence(firstRequirement(), []);

    expect(state.assertions.value[firstRequirement()]).toBeUndefined();
  });

  it("refuses to write against the read-only example", async () => {
    state.showingExample.value = true;

    await state.assertEvidence(firstRequirement(), [lineA]);

    expect(state.assertions.value).toEqual({});
    expect(attachAssertions).not.toHaveBeenCalled();
  });

  it("reports a storage failure instead of pretending it saved", async () => {
    attachAssertions.mockRejectedValueOnce(new Error("quota exceeded"));

    await state.assertEvidence(firstRequirement(), [lineA]);

    expect(state.error.value).not.toBeNull();
  });
});

describe("assertionList", () => {
  it("is the shape the engine validates, not the map the UI keeps", async () => {
    await state.assertEvidence(firstRequirement(), [lineA, lineB]);

    expect(state.assertionList()).toEqual([
      { requirement_id: firstRequirement(), line_ids: [lineA, lineB] },
    ]);
  });

  it("is empty when nobody has disagreed with anything", () => {
    expect(state.assertionList()).toEqual([]);
  });
});

describe("the interview brief", () => {
  it("is told about the correction and calls it the candidate's own", async () => {
    await state.assertEvidence(firstRequirement(), [lineA]);

    await state.runBrief();

    const item = state.briefResult.value?.risks.find(
      (row) => row.requirement_id === firstRequirement(),
    );
    expect(item?.risk).toBe("self_asserted");
    expect(item?.line_ids).toEqual([lineA]);
    // And it is never a receipt: `proved` is for evidence the app could see.
    expect(state.briefResult.value?.proved.map((row) => row.requirement_id)).not.toContain(
      firstRequirement(),
    );
  });
});
