/**
 * State machine behaviour around a finished run.
 *
 * The run is the expensive half — two model calls the user waited for. What
 * happens *after* it succeeds is therefore worth testing on its own: a storage
 * failure must not turn a completed match into a failed one.
 */

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const saveMatch = vi.fn();

vi.mock("../../ui/src/lib/store", () => ({
  loadProfile: vi.fn(async () => null),
  saveProfile: vi.fn(async () => undefined),
  loadCv: vi.fn(async () => null),
  saveCv: vi.fn(async () => undefined),
  deleteCv: vi.fn(async () => undefined),
  loadIndex: vi.fn(async () => []),
  loadMatch: vi.fn(async () => null),
  saveMatch,
  attachTailor: vi.fn(async () => undefined),
  attachLetter: vi.fn(async () => undefined),
  setMatchStatus: vi.fn(async () => []),
  deleteMatch: vi.fn(async () => []),
  deleteEverything: vi.fn(async () => undefined),
}));

const { connect } = await import("../../ui/src/lib/anna");
const { parseCvText } = await import("../../ui/src/lib/engine");
const { EXAMPLE_POSTING } = await import("../../ui/src/lib/example");
const state = await import("../../ui/src/state");

const CV_TEXT = [
  "Dilek Aydin — Backend Engineer",
  "Experience",
  "Acme Payments — Backend Engineer, 2018-2024",
  "Built payment reconciliation services in Go for 1,200 merchant accounts.",
  "Migrated the reporting pipeline from MySQL to PostgreSQL with zero downtime.",
  "Ran the settlement workers on k8s across two regions.",
  "Led a team of 4 engineers and owned the on-call rotation.",
  "Education",
  "MSc Computer Science, Bogazici University, 2016",
].join("\n");

beforeAll(async () => {
  await connect();
  const doc = await parseCvText(CV_TEXT);
  state.cv.value = { doc, filename: null, updated_at: new Date().toISOString() };
});

beforeEach(() => {
  saveMatch.mockReset();
  state.error.value = null;
  state.currentMatch.value = null;
  state.postingText.value = EXAMPLE_POSTING;
});

describe("startMatch", () => {
  it("keeps the result on screen when storage refuses to save it", async () => {
    saveMatch.mockRejectedValue(new Error("quota exceeded"));

    await state.startMatch();

    expect(state.matchPhase.value).toBe("done");
    expect(state.currentMatch.value?.requirements.length).toBeGreaterThan(0);
    expect(state.error.value?.code).toBe("save_failed");
  });

  it("reports no error when the save succeeds", async () => {
    saveMatch.mockResolvedValue([]);

    await state.startMatch();

    expect(state.matchPhase.value).toBe("done");
    expect(state.error.value).toBeNull();
    expect(saveMatch).toHaveBeenCalledTimes(1);
  });
});

describe("runTailor", () => {
  it("runs on a match made against the CV on screen", async () => {
    saveMatch.mockResolvedValue([]);
    await state.startMatch();

    await state.runTailor();

    expect(state.error.value).toBeNull();
    expect(state.tailorPhase.value).toBe("done");
  });

  it("refuses a match made against an earlier version of the CV", async () => {
    saveMatch.mockResolvedValue([]);
    await state.startMatch();
    const before = state.currentMatch.value;

    // The user fixes a misread line: the stored match no longer describes the
    // CV on screen, and building on it would cite text that has changed.
    const firstLine = state.cv.value?.doc.lines[0];
    if (!firstLine) throw new Error("fixture CV has no lines");
    await state.editCvLine(firstLine.id, "Dilek Aydin — Staff Backend Engineer");

    await state.runTailor();

    expect(state.error.value?.code).toBe("cv_changed");
    expect(state.tailorPhase.value).not.toBe("running");
    expect(state.currentMatch.value).toBe(before);
  });
});
