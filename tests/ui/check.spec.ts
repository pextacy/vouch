/**
 * Checking a document Vouch did not write.
 *
 * Three things carry the weight here and none of them is the verifier, which
 * has its own suite in Python:
 *
 * * the document is **never stored** — this screen takes the one piece of
 *   text in the app the user did not agree to save, and a stray `saveCv` here
 *   would be a privacy bug wearing a feature's clothes;
 * * an answer goes into the CV verbatim and the check runs again, so a
 *   sentence clears because it is backed, not because the screen hid it;
 * * the key that remembers an answer survives a re-check, whose indices move
 *   the moment anything above the sentence changes.
 */

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const saveCv = vi.fn(async () => undefined);
const saveMatch = vi.fn(async () => []);

vi.mock("../../ui/src/lib/store", () => ({
  loadProfile: vi.fn(async () => null),
  saveProfile: vi.fn(async () => undefined),
  loadCv: vi.fn(async () => null),
  saveCv,
  deleteCv: vi.fn(async () => undefined),
  loadCvProfiles: vi.fn(async () => null),
  saveCvProfiles: vi.fn(async () => undefined),
  deleteCvProfile: vi.fn(async () => []),
  loadIndex: vi.fn(async () => []),
  loadMatch: vi.fn(async () => null),
  loadRecentMatches: vi.fn(async () => []),
  saveMatch,
  attachTailor: vi.fn(async () => undefined),
  attachLetter: vi.fn(async () => undefined),
  setMatchStatus: vi.fn(async () => []),
  deleteMatch: vi.fn(async () => []),
  deleteEverything: vi.fn(async () => undefined),
}));

const { connect } = await import("../../ui/src/lib/anna");
const { checkDocument, parseCvText } = await import("../../ui/src/lib/engine");
const { parse } = await import("../../ui/src/router");
const state = await import("../../ui/src/state");

const CV_TEXT = [
  "Maya Collins — Backend Engineer",
  "Experience",
  "Acme Payments — Backend Engineer, 2018-2024",
  "Built payment reconciliation services in Go for merchant accounts.",
  "Migrated the reporting pipeline from MySQL to PostgreSQL.",
  "Education",
  "MSc Computer Science, University of Edinburgh, 2016",
].join("\n");

beforeAll(async () => {
  await connect();
  const doc = await parseCvText(CV_TEXT);
  state.cv.value = { doc, filename: null, updated_at: new Date().toISOString() };
});

beforeEach(() => {
  saveCv.mockClear();
  saveCv.mockResolvedValue(undefined);
  state.error.value = null;
  state.currentMatch.value = null;
  state.clearCheck();
});

describe("the route", () => {
  it("is flat, like every other one", () => {
    expect(parse("/check")).toEqual({ name: "check" });
  });
});

describe("checkDocument", () => {
  it("flags a sentence claiming something the CV never states", async () => {
    const doc = state.cv.value?.doc;
    if (!doc) throw new Error("fixture CV missing");

    const result = await checkDocument({
      cv: doc,
      document: "Cut checkout latency by 40% at Globex.",
    });

    expect(result.unbacked).toBe(1);
    expect(result.flagged[0]?.text).toBe("Cut checkout latency by 40% at Globex.");
    expect(result.flagged.flatMap((line) => line.claims.map((claim) => claim.surface))).toContain(
      "40%",
    );
  });

  it("leaves a sentence the CV states outright alone", async () => {
    const doc = state.cv.value?.doc;
    if (!doc) throw new Error("fixture CV missing");

    const result = await checkDocument({
      cv: doc,
      document: "Migrated the reporting pipeline from MySQL to PostgreSQL.",
    });

    expect(result.flagged).toEqual([]);
    expect(result.checked).toBe(1);
  });

  it("counts every sentence, not only the flagged ones", async () => {
    const doc = state.cv.value?.doc;
    if (!doc) throw new Error("fixture CV missing");

    const result = await checkDocument({
      cv: doc,
      document: [
        "Migrated the reporting pipeline from MySQL to PostgreSQL.",
        "Ran a department of 40 people.",
      ].join("\n"),
    });

    expect(result.checked).toBe(2);
    expect(result.unbacked).toBe(1);
  });
});

describe("runCheck", () => {
  it("does nothing without a document, rather than calling the engine", async () => {
    state.checkDraft.value = "   ";
    await state.runCheck();
    expect(state.checkPhase.value).toBe("idle");
    expect(state.checkResult.value).toBeNull();
  });

  it("never writes the pasted document to storage", async () => {
    state.checkDraft.value = "Cut checkout latency by 40%.";
    await state.runCheck();

    expect(state.checkPhase.value).toBe("done");
    expect(state.checkResult.value?.unbacked).toBe(1);
    expect(saveCv).not.toHaveBeenCalled();
  });

  it("forgets the document when the screen is left", async () => {
    state.checkDraft.value = "Cut checkout latency by 40%.";
    await state.runCheck();

    state.clearCheck();

    expect(state.checkDraft.value).toBe("");
    expect(state.checkResult.value).toBeNull();
    expect(state.checkPhase.value).toBe("idle");
  });
});

describe("answering a flagged sentence", () => {
  it("puts the answer in the CV verbatim and checks again", async () => {
    state.checkDraft.value = "Ran the settlement workers on Kubernetes.";
    await state.runCheck();
    const flagged = state.checkResult.value?.flagged[0];
    if (!flagged) throw new Error("expected the sentence to be flagged");

    const answer = "I ran our Kubernetes cluster at Acme Payments.";
    await state.answerCheckedLine(flagged, answer);

    const lines = state.cv.value?.doc.lines ?? [];
    const added = lines[lines.length - 1];
    expect(added?.text).toBe(answer);
    expect(added?.added_at).toBeTruthy();
    expect(saveCv).toHaveBeenCalled();
    // Re-run: the sentence is backed now, so it is gone from the list.
    expect(state.checkResult.value?.flagged.map((line) => line.text)).not.toContain(flagged.text);
  });

  it("does not record an answer that storage refused to save", async () => {
    state.checkDraft.value = "Cut checkout latency by 40%.";
    await state.runCheck();
    const flagged = state.checkResult.value?.flagged[0];
    if (!flagged) throw new Error("expected the sentence to be flagged");

    saveCv.mockRejectedValueOnce(new Error("quota exceeded"));
    await state.answerCheckedLine(flagged, "It was a 40% drop, at Acme.");

    expect(state.answeredChecks.value.has(state.checkedKey(flagged))).toBe(false);
    // Whatever the code, the failure has to reach the screen: an answer that
    // never made it into the CV must not look like one that did.
    expect(state.error.value).not.toBeNull();
  });
});

describe("checkedKey", () => {
  it("names the sentence, not where it happens to sit", () => {
    const sentence = "Cut checkout latency by 40%.";
    const first = { index: 2, text: sentence, claims: [] };
    const moved = { index: 9, text: sentence, claims: [] };
    expect(state.checkedKey(first)).toBe(state.checkedKey(moved));
  });

  it("tells two different sentences apart", () => {
    expect(state.checkedKey({ index: 0, text: "One.", claims: [] })).not.toBe(
      state.checkedKey({ index: 0, text: "Two.", claims: [] }),
    );
  });
});
