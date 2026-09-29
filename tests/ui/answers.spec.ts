/**
 * Answering the form — and the two ways the app declines to.
 *
 * The splitter gets the most tests here, because it runs before anything is
 * spent and a wrong split is the difference between answering the question and
 * answering half of two. After that: an answer the CV cannot give must reach
 * the screen as a question, not as prose, and the sentence the user types must
 * land in their CV and be there on the re-run.
 */

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const saveCv = vi.fn(async () => undefined);

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
  saveMatch: vi.fn(async () => []),
  attachTailor: vi.fn(async () => undefined),
  attachLetter: vi.fn(async () => undefined),
  setMatchStatus: vi.fn(async () => []),
  deleteMatch: vi.fn(async () => []),
  deleteEverything: vi.fn(async () => undefined),
}));

const { connect } = await import("../../ui/src/lib/anna");
const { parseCvText } = await import("../../ui/src/lib/engine");
const { MAX_QUESTIONS, splitQuestions } = await import("../../ui/src/lib/questions");
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
  state.clearAnswers();
});

describe("the route", () => {
  it("is flat, like every other one", () => {
    expect(parse("/answers")).toEqual({ name: "answers" });
  });
});

describe("splitQuestions", () => {
  it("reads one form box per line", () => {
    expect(
      splitQuestions("Describe your Go experience.\nHave you owned an on-call rotation?"),
    ).toEqual(["Describe your Go experience.", "Have you owned an on-call rotation?"]);
  });

  it("splits a paragraph where the question marks are", () => {
    expect(splitQuestions("Why us? What excites you about this role?")).toEqual([
      "Why us?",
      "What excites you about this role?",
    ]);
  });

  it("does not split a question that runs to two sentences", () => {
    const asked = "Tell us about a time you owned an incident. Include what you changed.";
    expect(splitQuestions(asked)).toEqual([asked]);
  });

  it("drops the form's own numbering, not the question", () => {
    expect(splitQuestions("1. Describe your Go experience.\n2) Have you led a team?")).toEqual([
      "Describe your Go experience.",
      "Have you led a team?",
    ]);
  });

  it("ignores headings and blank lines", () => {
    expect(splitQuestions("Questions\n\nDescribe your Go experience.\n\n")).toEqual([
      "Describe your Go experience.",
    ]);
  });

  it("asks the same question once", () => {
    expect(splitQuestions("Why us?\nWhy us?")).toEqual(["Why us?"]);
  });

  it("stops at a form's worth", () => {
    const many = Array.from({ length: MAX_QUESTIONS + 4 }, (_, n) => `Question number ${n}?`);
    expect(splitQuestions(many.join("\n"))).toHaveLength(MAX_QUESTIONS);
  });
});

describe("what the screen will run", () => {
  it("is the split of what was pasted", () => {
    state.questionDraft.value = "Describe your Go experience.\nHave you led a team?";
    expect(state.detectedQuestions.value).toHaveLength(2);
  });

  it("drops a line the user struck off", () => {
    state.questionDraft.value = "Describe your Go experience.\nOffice location: Amsterdam";
    state.skipQuestion("Office location: Amsterdam");
    expect(state.detectedQuestions.value).toEqual(["Describe your Go experience."]);
  });
});

describe("runAnswers", () => {
  it("does nothing without a question, rather than calling the engine", async () => {
    state.questionDraft.value = "   ";
    await state.runAnswers();
    expect(state.answersPhase.value).toBe("idle");
    expect(state.answersResult.value).toBeNull();
  });

  it("answers from the CV and cites the line it used", async () => {
    state.questionDraft.value = "Describe your reconciliation experience.";
    await state.runAnswers();

    const item = state.answersResult.value?.items[0];
    expect(state.answersPhase.value).toBe("done");
    expect(item?.kind).toBe("answered");
    expect(item?.sentences[0]?.line_ids.length).toBeGreaterThan(0);
  });

  it("writes nothing at all for a question about what the candidate wants", async () => {
    state.questionDraft.value = "Why do you want to work here?";
    await state.runAnswers();

    const item = state.answersResult.value?.items[0];
    expect(item?.kind).toBe("not_about_you");
    expect(item?.sentences).toEqual([]);
  });

  it("hands back the question when the CV cannot answer it", async () => {
    state.questionDraft.value = "Describe your Kubernetes work.";
    await state.runAnswers();

    const item = state.answersResult.value?.items[0];
    expect(item?.kind).toBe("no_evidence");
    expect(item?.sentences).toEqual([]);
  });

  it("forgets the questions when the screen is left", async () => {
    state.questionDraft.value = "Why do you want to work here?";
    await state.runAnswers();

    state.clearAnswers();

    expect(state.questionDraft.value).toBe("");
    expect(state.answersResult.value).toBeNull();
    expect(state.answersPhase.value).toBe("idle");
  });
});

describe("answering a question the CV could not", () => {
  it("puts the sentence in the CV verbatim and asks again", async () => {
    state.questionDraft.value = "Describe your Kubernetes work.";
    await state.runAnswers();
    const item = state.answersResult.value?.items[0];
    if (!item) throw new Error("expected a question back");
    expect(item.kind).toBe("no_evidence");

    const answer = "I ran our Kubernetes cluster at Acme Payments.";
    await state.answerUnanswered(item, answer);

    const lines = state.cv.value?.doc.lines ?? [];
    const added = lines[lines.length - 1];
    expect(added?.text).toBe(answer);
    expect(added?.added_at).toBeTruthy();
    expect(saveCv).toHaveBeenCalled();
    // Asked again against the new line, the question is answerable.
    expect(state.answersResult.value?.items[0]?.kind).toBe("answered");
  });

  it("does not record an answer that storage refused to save", async () => {
    state.questionDraft.value = "Describe your Rust work.";
    await state.runAnswers();
    const item = state.answersResult.value?.items[0];
    if (!item) throw new Error("expected a question back");

    saveCv.mockRejectedValueOnce(new Error("quota exceeded"));
    await state.answerUnanswered(item, "I wrote a Rust parser at Acme Payments.");

    expect(state.answeredQuestions.value.has(item.question)).toBe(false);
    expect(state.error.value).not.toBeNull();
  });
});
