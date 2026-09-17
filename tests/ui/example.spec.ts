/**
 * The recorded example.
 *
 * It is the first thing a visitor sees ("See an example") and the only screen
 * in the app nobody's CV backs, so it has to hold itself to the rules the
 * engine enforces everywhere else: one evidence entry per requirement, counts
 * that add up, and no citation pointing at a line that does not exist.
 */

import { describe, expect, it } from "vitest";

import {
  EXAMPLE_CV,
  EXAMPLE_LETTER,
  EXAMPLE_MATCH,
  EXAMPLE_TAILOR,
} from "../../ui/src/lib/example";

const LINE_IDS = new Set(EXAMPLE_CV.lines.map((line) => line.id));

describe("example match", () => {
  it("has exactly one evidence entry per requirement", () => {
    const requirements = EXAMPLE_MATCH.requirements.map((item) => item.id);
    const evidence = EXAMPLE_MATCH.evidence.map((item) => item.requirement_id);
    expect([...evidence].sort()).toEqual([...requirements].sort());
  });

  it("counts the summary the way summarize() does", () => {
    const counted = { strong: 0, partial: 0, missing: 0 };
    for (const item of EXAMPLE_MATCH.evidence) counted[item.status] += 1;

    expect(EXAMPLE_MATCH.summary.total).toBe(EXAMPLE_MATCH.requirements.length);
    expect(EXAMPLE_MATCH.summary.strong).toBe(counted.strong);
    expect(EXAMPLE_MATCH.summary.partial).toBe(counted.partial);
    expect(EXAMPLE_MATCH.summary.missing).toBe(counted.missing);
  });

  it("counts must-haves without evidence", () => {
    const kindOf = new Map(EXAMPLE_MATCH.requirements.map((item) => [item.id, item.kind]));
    const mustMissing = EXAMPLE_MATCH.evidence.filter(
      (item) => item.status === "missing" && kindOf.get(item.requirement_id) === "must",
    ).length;
    expect(EXAMPLE_MATCH.summary.must_missing).toBe(mustMissing);
  });

  it("cites only CV lines that exist", () => {
    for (const item of EXAMPLE_MATCH.evidence) {
      for (const line of item.line_ids) expect(LINE_IDS.has(line), line).toBe(true);
    }
  });

  it("never cites a line on a requirement it calls missing", () => {
    for (const item of EXAMPLE_MATCH.evidence) {
      if (item.status === "missing") expect(item.line_ids).toEqual([]);
    }
  });
});

describe("example tailor and letter", () => {
  it("builds every bullet from real CV lines", () => {
    for (const bullet of EXAMPLE_TAILOR.bullets) {
      expect(bullet.source_line_ids.length).toBeGreaterThan(0);
      for (const line of bullet.source_line_ids) expect(LINE_IDS.has(line), line).toBe(true);
    }
  });

  it("shows at least one dropped bullet, which is the product working", () => {
    expect(EXAMPLE_TAILOR.bullets.some((bullet) => !bullet.suggestion)).toBe(true);
  });

  it("cites only CV lines that exist in the letter", () => {
    for (const paragraph of EXAMPLE_LETTER.paragraphs) {
      for (const line of paragraph.line_ids) expect(LINE_IDS.has(line), line).toBe(true);
    }
  });

  it("attaches evidence to at least one paragraph", () => {
    expect(EXAMPLE_LETTER.paragraphs.some((paragraph) => paragraph.line_ids.length > 0)).toBe(true);
  });

  it("ties both results to the example match", () => {
    expect(EXAMPLE_TAILOR.match_id).toBe(EXAMPLE_MATCH.id);
    expect(EXAMPLE_LETTER.match_id).toBe(EXAMPLE_MATCH.id);
  });
});
