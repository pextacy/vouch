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

describe("accepting suggestions", () => {
  /**
   * Two rewrites of the same CV line.
   *
   * The engine can return these — `pipeline/tailor.py` groups bullets into a
   * list per source line rather than a dict, with a comment saying a dict
   * "would drop one of them without saying so". Keying acceptance by the line
   * id put that dict back in the UI.
   */
  const twoFromOneLine = {
    match_id: "m1",
    bullets: [
      {
        original: "Built payment reconciliation services in Go.",
        suggestion: "Built payment reconciliation services in Go for 1,200 merchants.",
        source_line_ids: ["L4"],
        targets: ["R1"],
      },
      {
        original: "Built payment reconciliation services in Go.",
        suggestion: "Owned reconciliation services written in Go.",
        source_line_ids: ["L4"],
        targets: ["R2"],
      },
    ],
  };

  beforeEach(() => {
    state.acceptedBullets.value = {};
    state.tailorResult.value = twoFromOneLine as never;
    state.currentMatch.value = { id: "m1" } as never;
    state.showingExample.value = false;
  });

  it("keeps two suggestions from the same CV line independent", () => {
    const [first, second] = twoFromOneLine.bullets;
    if (!first || !second) throw new Error("fixture needs two bullets");

    state.acceptBullet(state.bulletKey(first as never), first.suggestion);

    expect(state.acceptedBullets.value[state.bulletKey(first as never)]).toBe(first.suggestion);
    expect(state.acceptedBullets.value[state.bulletKey(second as never)]).toBeUndefined();
  });

  it("exports each accepted suggestion once, with its own text", () => {
    const [first, second] = twoFromOneLine.bullets;
    if (!first || !second) throw new Error("fixture needs two bullets");

    state.acceptBullet(state.bulletKey(first as never), "Edited first suggestion.");
    state.acceptBullet(state.bulletKey(second as never), second.suggestion);

    const exported = state.acceptedTailor();
    expect(exported?.bullets.map((bullet) => bullet.suggestion)).toEqual([
      "Edited first suggestion.",
      second.suggestion,
    ]);
  });

  it("skips only the suggestion it was asked to skip", () => {
    const [first, second] = twoFromOneLine.bullets;
    if (!first || !second) throw new Error("fixture needs two bullets");

    state.acceptBullet(state.bulletKey(first as never), first.suggestion);
    state.acceptBullet(state.bulletKey(second as never), second.suggestion);
    state.skipBullet(state.bulletKey(first as never));

    expect(state.acceptedTailor()?.bullets).toHaveLength(1);
  });
});

describe("answering a gap", () => {
  /**
   * The loop the feature exists for: the app asks, the user answers, and the
   * answer becomes a CV line the next match can cite. Nothing generated ever
   * becomes evidence — only what the person typed.
   */
  beforeEach(async () => {
    saveMatch.mockResolvedValue([]);
    await state.startMatch();
    state.answeredGaps.value = new Set();
  });

  it("asks about the requirements the match could not prove", async () => {
    await state.runGaps();

    expect(state.gapsPhase.value).toBe("done");
    expect(state.gapsResult.value?.items.length).toBeGreaterThan(0);
  });

  it("puts the answer in the CV exactly as typed, marked as the user's own", async () => {
    const answer = "I ran the Kafka consumers behind the order feed at Acme for two years.";
    const before = state.cv.value?.doc.lines.length ?? 0;

    await state.answerGap("R6", answer);

    const lines = state.cv.value?.doc.lines ?? [];
    expect(lines).toHaveLength(before + 1);
    expect(lines.at(-1)?.text).toBe(answer);
    expect(lines.at(-1)?.added_at).toBeTruthy();
    expect(state.answeredGaps.value.has("R6")).toBe(true);
  });

  it("ignores an empty answer rather than adding a blank line", async () => {
    const before = state.cv.value?.doc.lines.length ?? 0;

    await state.answerGap("R6", "   ");

    expect(state.cv.value?.doc.lines).toHaveLength(before);
    expect(state.answeredGaps.value.has("R6")).toBe(false);
  });

  it("makes the match on screen stale, because the evidence has changed", async () => {
    expect(state.cvMovedOnFromMatch.value).toBe(false);

    await state.answerGap("R6", "I ran the consumers behind the order feed.");

    expect(state.cvMovedOnFromMatch.value).toBe(true);
    // And the existing guard does the rest: building a letter on the old match
    // would cite a CV that has since grown a line.
    await state.runLetter();
    expect(state.error.value?.code).toBe("cv_changed");
  });
});

describe("the CV audit", () => {
  /**
   * The only screen that turns the app's suspicion on the document the user
   * arrived with. Answering a finding runs the same loop the gap questions do,
   * so the two must not drift apart.
   */
  beforeEach(() => {
    state.auditResult.value = null;
    state.auditPhase.value = "idle";
    state.answeredFindings.value = new Set();
  });

  it("reads the CV without a posting", async () => {
    state.currentMatch.value = null;

    await state.runAudit();

    expect(state.auditPhase.value).toBe("done");
    expect(state.auditResult.value?.findings.length).toBeGreaterThan(0);
  });

  it("gives every finding a spelling the screen can render", async () => {
    // The card renders `surface` unconditionally, and it is the CV's own
    // spelling rather than the canonical term the engine compared with.
    await state.runAudit();

    for (const finding of state.auditResult.value?.findings ?? []) {
      expect(finding.surface, finding.subject).toBeTruthy();
    }
  });

  it("identifies a finding by what it is about, so a re-audit recognises it", () => {
    const finding = { kind: "skill_unevidenced", subject: "docker", line_ids: ["L9"] } as const;
    const same = { kind: "skill_unevidenced", subject: "docker", line_ids: [] } as const;
    const other = { kind: "skill_unevidenced", subject: "redis", line_ids: ["L9"] } as const;

    expect(state.findingKey(finding as never)).toBe(state.findingKey(same as never));
    expect(state.findingKey(finding as never)).not.toBe(state.findingKey(other as never));
  });

  it("puts the answer in the CV and re-runs the audit", async () => {
    const finding = { kind: "skill_unevidenced", subject: "docker", line_ids: ["L9"] } as const;
    const before = state.cv.value?.doc.lines.length ?? 0;

    await state.answerFinding(finding as never, "I packaged the settlement workers with Docker.");

    const lines = state.cv.value?.doc.lines ?? [];
    expect(lines).toHaveLength(before + 1);
    expect(lines.at(-1)?.text).toBe("I packaged the settlement workers with Docker.");
    expect(lines.at(-1)?.added_at).toBeTruthy();
    expect(state.answeredFindings.value.has(state.findingKey(finding as never))).toBe(true);
    // Re-run, so a finding clears because it was answered rather than hidden.
    expect(state.auditPhase.value).toBe("done");
  });

  it("ignores an empty answer", async () => {
    const finding = { kind: "skill_unevidenced", subject: "redis", line_ids: ["L9"] } as const;
    const before = state.cv.value?.doc.lines.length ?? 0;

    await state.answerFinding(finding as never, "  ");

    expect(state.cv.value?.doc.lines).toHaveLength(before);
    expect(state.answeredFindings.value.size).toBe(0);
  });
});

describe("what keeps coming up", () => {
  /**
   * The only view that reads across applications. The preview stub groups by
   * exact wording rather than by lexicon term, so these assert the plumbing
   * and the guards rather than the grouping, which is the engine's own test.
   */
  beforeEach(() => {
    state.recurringResult.value = null;
    state.recurringPhase.value = "idle";
    state.answeredRecurring.value = new Set();
  });

  it("reports the number of applications it actually read", async () => {
    saveMatch.mockResolvedValue([]);

    await state.runRecurring();

    expect(state.recurringPhase.value).toBe("done");
    expect(state.recurringResult.value?.matches).toBeGreaterThanOrEqual(0);
  });

  it("never renders a group claiming more applications than it read", async () => {
    await state.runRecurring();
    const report = state.recurringResult.value;

    for (const group of [...(report?.groups ?? []), ...(report?.strengths ?? [])]) {
      expect(group.asked, group.key).toBeLessThanOrEqual(report?.matches ?? 0);
      expect(group.unproven, group.key).toBeLessThanOrEqual(group.asked);
    }
  });

  it("puts a recurring answer in the CV like any other", async () => {
    const before = state.cv.value?.doc.lines.length ?? 0;

    await state.answerRecurring("kafka", "I ran the Kafka consumers for the order feed.");

    const lines = state.cv.value?.doc.lines ?? [];
    expect(lines).toHaveLength(before + 1);
    expect(lines.at(-1)?.text).toBe("I ran the Kafka consumers for the order feed.");
    expect(lines.at(-1)?.added_at).toBeTruthy();
    expect(state.answeredRecurring.value.has("kafka")).toBe(true);
  });

  it("ignores an empty answer", async () => {
    const before = state.cv.value?.doc.lines.length ?? 0;

    await state.answerRecurring("redis", "   ");

    expect(state.cv.value?.doc.lines).toHaveLength(before);
    expect(state.answeredRecurring.value.size).toBe(0);
  });
});

describe("the interview brief", () => {
  beforeEach(async () => {
    saveMatch.mockResolvedValue([]);
    await state.startMatch();
    state.briefPhase.value = "idle";
    state.briefResult.value = null;
  });

  it("is built from the match, the CV and what was sent", async () => {
    await state.runBrief();

    expect(state.briefPhase.value).toBe("done");
    expect(state.error.value).toBeNull();
    expect(state.briefResult.value?.match_id).toBe(state.currentMatch.value?.id);
  });

  /**
   * The rule that separates this from `tailor` and `letter`.
   *
   * Answering a gap question moves the CV hash, so a brief that refused a
   * moved CV would lock out exactly the people who prepared hardest. It
   * reports the drift instead — the interviewer is holding the older CV,
   * which is worth saying out loud rather than refusing over.
   */
  it("still runs after the CV has moved, and says the sent version is older", async () => {
    const firstLine = state.cv.value?.doc.lines[0];
    if (!firstLine) throw new Error("fixture CV has no lines");
    await state.editCvLine(firstLine.id, "Dilek Aydin — Staff Backend Engineer");

    await state.runBrief();

    expect(state.error.value).toBeNull();
    expect(state.briefPhase.value).toBe("done");
    expect(state.briefResult.value?.cv_changed).toBe(true);
  });

  it("is dropped when another application is opened, not carried over", async () => {
    await state.runBrief();
    expect(state.briefResult.value).not.toBeNull();

    await state.startMatch();

    expect(state.briefResult.value).toBeNull();
    expect(state.briefPhase.value).toBe("idle");
  });
});

/**
 * The selection the comparison opens with.
 *
 * It outlives the screen — someone picks three postings, opens one of them,
 * comes back — so it can outlive one of the matches in it. A comparison
 * quietly drawn from one posting is worse than none: the columns would stay on
 * screen with nothing saying they had stopped being about what was picked.
 */
describe("choosing what to compare", () => {
  const entry = (id: string) => ({
    id,
    company: "Northwind",
    role: "Backend Engineer",
    created_at: "2026-09-19T10:00:00+00:00",
    strong: 6,
    total: 8,
    status: "drafted" as const,
  });

  beforeEach(() => {
    state.compareSelection.value = [];
    state.compareResult.value = null;
    state.comparePhase.value = "idle";
  });

  it("starts on the two most recent applications", () => {
    state.tracker.value = [entry("m1"), entry("m2"), entry("m3")];

    state.startCompare();

    expect(state.compareSelection.value).toEqual(["m1", "m2"]);
  });

  it("keeps a selection the user made themselves", () => {
    state.tracker.value = [entry("m1"), entry("m2"), entry("m3")];
    state.compareSelection.value = ["m3"];

    state.startCompare();

    expect(state.compareSelection.value).toEqual(["m3"]);
  });

  it("drops a match that is no longer in the tracker", () => {
    state.tracker.value = [entry("m1"), entry("m2")];
    state.compareSelection.value = ["m1", "gone"];

    state.startCompare();

    expect(state.compareSelection.value).toEqual(["m1"]);
    // And the answer that was about the deleted one goes with it.
    expect(state.compareResult.value).toBeNull();
  });

  it("falls back to the recent ones when nothing selected is left", () => {
    state.tracker.value = [entry("m1"), entry("m2")];
    state.compareSelection.value = ["gone"];

    state.startCompare();

    expect(state.compareSelection.value).toEqual(["m1", "m2"]);
  });
});

/**
 * The way out for everything the answer loops write in.
 *
 * The download itself needs a host — the stub has no `files.download` — so
 * what is worth asserting here is the thing the screen keys off: whether this
 * CV holds anything the person typed themselves, which is what decides
 * between "download your CV" alone and "just the lines you added" beside it.
 */
describe("taking the CV back", () => {
  it("offers the additions sheet only once there is something added", async () => {
    // A CV as it arrives from the parser. The suite shares one `cv` signal
    // and the gap tests above have already written into it.
    const doc = await parseCvText(CV_TEXT);
    state.cv.value = { doc, filename: null, updated_at: new Date().toISOString() };
    expect(state.cvHasAdditions.value).toBe(false);

    saveMatch.mockResolvedValue([]);
    await state.startMatch();
    await state.answerGap("R6", "I ran the Kafka consumers behind the order feed at Acme.");

    expect(state.cvHasAdditions.value).toBe(true);
    expect(state.cv.value?.doc.lines.filter((line) => line.added_at)).toHaveLength(1);
  });
});
