/**
 * "Since you applied" — the date it counts from, and the line it counts.
 *
 * This screen exists to tell someone an application is worth running again,
 * which costs a model call and a few minutes of their evening. Two things
 * keep that honest and both are tested here.
 *
 * The clock: until v1.3 the tracker knew an application was *Applied* and not
 * when, so the screen has to say which day it is counting from rather than
 * implying one it does not have. `setMatchStatus` is what starts recording
 * it, and a row written before that still has to work.
 *
 * The line: only a sentence written *after* the application went out is news.
 * A line the match already read and ruled on is not a reason to run it again.
 */

import { beforeAll, beforeEach, describe, expect, it } from "vitest";

import { connect } from "../../ui/src/lib/anna";
import { sinceApplied } from "../../ui/src/lib/engine";
import * as store from "../../ui/src/lib/store";
import { EXAMPLE_CV, EXAMPLE_MATCH } from "../../ui/src/lib/example";
import type { CVDoc, CvLine, MatchResult } from "../../ui/src/lib/types";

const SENT = "2026-09-12T09:00:00Z";

/** The CV, plus a sentence the user wrote into Vouch on a given day. */
function cvWith(line: Partial<CvLine> & { added_at: string }): CVDoc {
  return {
    ...EXAMPLE_CV,
    hash: `${EXAMPLE_CV.hash}~e1`,
    lines: [
      ...EXAMPLE_CV.lines,
      {
        id: "L20",
        text: "Owned the Kafka consumer rewrite at Northwind.",
        section: "experience",
        ...line,
      },
    ],
  };
}

/** An application that went out without proving what `text` asks for. */
function unproved(text: string, created_at = "2026-09-10T09:00:00+00:00"): MatchResult {
  return {
    ...EXAMPLE_MATCH,
    created_at,
    cv_hash: EXAMPLE_CV.hash,
    requirements: [
      { id: "R1", text, kind: "must", category: "skill", source_quote: text.slice(0, 40) },
    ],
    evidence: [{ requirement_id: "R1", status: "missing", line_ids: [], why: "" }],
  };
}

/**
 * The preview runtime keeps storage in `localStorage`, which a node test run
 * does not have. A Map behind the same three methods is enough to exercise
 * the real `store` module rather than a mock of it — and the date this suite
 * is about is written by `store`, so mocking it would test nothing.
 */
function installLocalStorage(): void {
  const cells = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => cells.get(key) ?? null,
      setItem: (key: string, value: string) => void cells.set(key, value),
      removeItem: (key: string) => void cells.delete(key),
      clear: () => cells.clear(),
      key: (index: number) => [...cells.keys()][index] ?? null,
      get length() {
        return cells.size;
      },
    },
  });
}

beforeAll(async () => {
  installLocalStorage();
  await connect();
});

describe("the tracker's clock", () => {
  beforeEach(async () => {
    await store.saveMatch({ ...EXAMPLE_MATCH, id: "m-since" });
  });

  it("records when a status was set, so an application can be dated", async () => {
    const before = Date.now();

    const index = await store.setMatchStatus("m-since", "applied");

    const row = index.find((entry) => entry.id === "m-since");
    expect(row?.status).toBe("applied");
    expect(Date.parse(row?.status_at ?? "")).toBeGreaterThanOrEqual(before);
    // On the record too: the screen reads the index, the engine call reads
    // whichever the caller has, and a date in only one of them is a date that
    // disagrees with itself.
    const record = await store.loadMatch("m-since");
    expect(record?.status_at).toBe(row?.status_at);
  });

  it("moves the date when the status moves again", async () => {
    const first = (await store.setMatchStatus("m-since", "applied")).find(
      (entry) => entry.id === "m-since",
    )?.status_at;
    const second = (await store.setMatchStatus("m-since", "interview")).find(
      (entry) => entry.id === "m-since",
    )?.status_at;

    expect(Date.parse(second ?? "")).toBeGreaterThanOrEqual(Date.parse(first ?? ""));
  });
});

describe("since_applied, through the preview stub", () => {
  it("reports a line written after it went out, against what it could not show", async () => {
    const result = await sinceApplied({
      cv: cvWith({ added_at: "2026-09-20T10:00:00Z" }),
      match: unproved("Production experience with Kafka"),
      sentAt: SENT,
    });

    expect(result.added).toEqual(["L20"]);
    expect(result.answers.map((answer) => answer.requirement_id)).toEqual(["R1"]);
    expect(result.answers[0]?.line_ids).toEqual(["L20"]);
    expect(result.answers[0]?.terms).toContain("Kafka");
    // The verdict it got is what has *not* changed, and the screen says so.
    expect(result.answers[0]?.status).toBe("missing");
  });

  it("says nothing about a line the match had already read", async () => {
    const result = await sinceApplied({
      cv: cvWith({ added_at: "2026-09-01T10:00:00Z" }),
      match: unproved("Production experience with Kafka"),
      sentAt: SENT,
    });

    expect(result.added).toEqual([]);
    expect(result.answers).toEqual([]);
  });

  it("leaves a requirement the application already proved alone", async () => {
    const match = unproved("Production experience with Kafka");
    match.evidence = [{ requirement_id: "R1", status: "strong", line_ids: ["L3"], why: "" }];

    const result = await sinceApplied({
      cv: cvWith({ added_at: "2026-09-20T10:00:00Z" }),
      match,
      sentAt: SENT,
    });

    expect(result.answers).toEqual([]);
    expect(result.added).toEqual(["L20"], "still a new line — it just changes nothing here");
  });

  it("counts from the day it was sent, and says which clock that was", async () => {
    const result = await sinceApplied({
      cv: EXAMPLE_CV,
      match: unproved("Production experience with Kafka"),
      sentAt: SENT,
    });

    expect(result.dated_from).toBe("sent");
    expect(result.days).toBeGreaterThan(0);
  });

  it("falls back to the day the match was run for a row that never recorded one", async () => {
    // Every application saved before v1.3 is this one, and being told "you
    // sent this 9 days ago" about a day nobody recorded would be a small lie
    // in the screen's opening sentence.
    const result = await sinceApplied({
      cv: EXAMPLE_CV,
      match: unproved("Production experience with Kafka"),
    });

    expect(result.dated_from).toBe("checked");
  });

  it("reports the CV moving on its own", async () => {
    const moved = await sinceApplied({
      cv: cvWith({ added_at: "2026-09-20T10:00:00Z" }),
      match: unproved("Production experience with Kafka"),
      sentAt: SENT,
    });
    const same = await sinceApplied({
      cv: EXAMPLE_CV,
      match: unproved("Production experience with Kafka"),
      sentAt: SENT,
    });

    expect(moved.cv_changed).toBe(true);
    expect(same.cv_changed).toBe(false);
  });
});
