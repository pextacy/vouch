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
  EXAMPLE_BRIEF,
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

/**
 * The recorded interview brief.
 *
 * It is the engine's own output for the fixtures above, pasted in — so the
 * thing worth testing is that it still describes them. A brief quoting a
 * sentence the example letter no longer contains would be the demo showing
 * the user something the app did not produce.
 */
describe("example interview brief", () => {
  const REQUIREMENT_IDS = new Set(EXAMPLE_MATCH.requirements.map((item) => item.id));
  const items = [...EXAMPLE_BRIEF.risks, ...EXAMPLE_BRIEF.proved];

  it("belongs to the example match and its CV", () => {
    expect(EXAMPLE_BRIEF.match_id).toBe(EXAMPLE_MATCH.id);
    expect(EXAMPLE_BRIEF.cv_hash).toBe(EXAMPLE_CV.hash);
    expect(EXAMPLE_BRIEF.cv_changed).toBe(false);
  });

  it("names only requirements the match states", () => {
    for (const item of items) {
      expect(REQUIREMENT_IDS.has(item.requirement_id), item.requirement_id).toBe(true);
    }
  });

  it("names each requirement once, on one side or the other", () => {
    const named = items.map((item) => item.requirement_id);
    expect(new Set(named).size).toBe(named.length);
  });

  it("calls proved exactly what the risks do not", () => {
    for (const item of EXAMPLE_BRIEF.proved) expect(item.risk).toBe("proved");
    for (const item of EXAMPLE_BRIEF.risks) expect(item.risk).not.toBe("proved");
  });

  it("cites only CV lines that exist", () => {
    for (const item of items) {
      for (const line of item.line_ids) expect(LINE_IDS.has(line), line).toBe(true);
      for (const claim of item.claims) {
        for (const line of claim.line_ids) expect(LINE_IDS.has(line), line).toBe(true);
      }
    }
  });

  it("cites no line for a requirement it says has no evidence", () => {
    for (const item of items) {
      if (item.risk === "no_evidence") expect(item.line_ids).toEqual([]);
    }
  });

  it("quotes only sentences the user actually sent", () => {
    const sent = new Set<string>([
      ...EXAMPLE_TAILOR.bullets.map((bullet) => bullet.suggestion ?? ""),
      ...EXAMPLE_LETTER.paragraphs.map((paragraph) => paragraph.text),
    ]);
    const claims = [...items.flatMap((item) => item.claims), ...EXAMPLE_BRIEF.loose_claims];
    expect(claims.length).toBeGreaterThan(0);
    for (const claim of claims) expect(sent.has(claim.text), claim.text).toBe(true);
  });

  it("never quotes a suggestion the verifier dropped", () => {
    const dropped = EXAMPLE_TAILOR.bullets.filter((bullet) => !bullet.suggestion);
    expect(dropped.length).toBeGreaterThan(0);
    const originals = new Set(dropped.map((bullet) => bullet.original));
    const claims = [...items.flatMap((item) => item.claims), ...EXAMPLE_BRIEF.loose_claims];
    for (const claim of claims) expect(originals.has(claim.text)).toBe(false);
  });
});
