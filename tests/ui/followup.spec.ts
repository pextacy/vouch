/**
 * The nudge the app is willing to give, and the note it is willing to write.
 *
 * Both halves of this feature are restraint. The tracker says an application
 * has been quiet and never that nobody replied — the app does not read
 * anyone's inbox, and the difference between those two sentences is the
 * difference between a record and an invention. And the note is only written
 * when the CV has gained something since the application went out; the
 * refusal is the feature, so it is the first thing tested.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { connect } from "../../ui/src/lib/anna";
import { followup } from "../../ui/src/lib/engine";
import { QUIET_DAYS, daysSilent, hasGoneQuiet } from "../../ui/src/lib/followup";
import { EXAMPLE_CV, EXAMPLE_MATCH } from "../../ui/src/lib/example";
import type { CVDoc, MatchResult, TrackerEntry } from "../../ui/src/lib/types";

const NOW = Date.parse("2026-09-27T12:00:00Z");
const SENT = "2026-09-10T09:00:00+00:00";

function entry(overrides: Partial<TrackerEntry> = {}): TrackerEntry {
  return {
    id: "m1",
    company: "Northwind",
    role: "Backend Engineer",
    created_at: SENT,
    strong: 6,
    total: 8,
    status: "applied",
    status_at: "2026-09-12T09:00:00Z",
    ...overrides,
  };
}

/** The CV, plus a sentence written on a given day. */
function cvWritten(at: string | null): CVDoc {
  if (at === null) return EXAMPLE_CV;
  return {
    ...EXAMPLE_CV,
    hash: `${EXAMPLE_CV.hash}~e1`,
    lines: [
      ...EXAMPLE_CV.lines,
      {
        id: "L20",
        text: "Owned the Kafka consumer rewrite at Acme Payments.",
        section: "experience",
        added_at: at,
      },
    ],
  };
}

function match(): MatchResult {
  return { ...EXAMPLE_MATCH, created_at: SENT, cv_hash: EXAMPLE_CV.hash };
}

beforeAll(async () => {
  await connect();
});

describe("when the tracker is willing to say an application has gone quiet", () => {
  it("counts from the day the user marked it sent", () => {
    expect(daysSilent(entry(), NOW)).toBe(15);
    expect(hasGoneQuiet(entry(), NOW)).toBe(true);
  });

  it("stays quiet before the wait is past the median", () => {
    const recent = entry({ status_at: "2026-09-25T09:00:00Z" });

    expect(daysSilent(recent, NOW)).toBe(2);
    expect(hasGoneQuiet(recent, NOW)).toBe(false);
    expect(QUIET_DAYS).toBe(10);
  });

  it("says nothing about a row that never recorded the day it was sent", () => {
    // Every application saved before v1.3. `created_at` is the day the match
    // was run, which is a different fact, and dressing one up as the other is
    // what this returns null to avoid.
    expect(daysSilent(entry({ status_at: undefined }), NOW)).toBeNull();
    expect(hasGoneQuiet(entry({ status_at: undefined }), NOW)).toBe(false);
  });

  it("says nothing about an application that was never sent", () => {
    expect(daysSilent(entry({ status: "drafted" }), NOW)).toBeNull();
    expect(daysSilent(entry({ status: "closed" }), NOW)).toBeNull();
  });

  it("offers the nudge on a row that reached an interview too", () => {
    expect(hasGoneQuiet(entry({ status: "interview" }), NOW)).toBe(true);
  });
});

describe("followup, through the preview stub", () => {
  it("declines when the CV has not moved since the application went out", async () => {
    const result = await followup(cvWritten(null), match(), { locale: "en", sentAt: SENT });

    expect(result.kind).toBe("nothing_new");
    expect(result.paragraphs).toEqual([]);
    expect(result.dated_from).toBe("sent");
  });

  it("declines for a line the application had already read", async () => {
    const result = await followup(cvWritten("2026-09-01T10:00:00Z"), match(), {
      locale: "en",
      sentAt: SENT,
    });

    expect(result.kind).toBe("nothing_new");
  });

  it("writes from the line that arrived after the envelope", async () => {
    const result = await followup(cvWritten("2026-09-20T10:00:00Z"), match(), {
      locale: "en",
      sentAt: SENT,
    });

    expect(result.kind).toBe("new_evidence");
    expect(result.line_ids).toEqual(["L20"]);
    expect(result.terms).toContain("Kafka");
    // Every sentence that claims something cites the line it stands on, and
    // the reader's name is the one nobody can fill in for the user.
    const claims = result.paragraphs.filter((para) => para.line_ids.length > 0);
    expect(claims.length).toBeGreaterThan(0);
    expect(result.placeholders).toContain("[Hiring Manager]");
  });
});
