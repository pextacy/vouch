/**
 * Changing the CV document.
 *
 * Two rules matter more than anything else here, and both are about citations
 * outliving the edit that follows them: a new line must never take an id that
 * something already points at, and any change must move the hash so a match
 * made against the old text stops claiming to be about the new one.
 */

import { describe, expect, it } from "vitest";

import {
  appendLine,
  editLine,
  markEdited,
  nextLineId,
  sectionForCategory,
} from "../../ui/src/lib/cv";
import { EXAMPLE_CV } from "../../ui/src/lib/example";
import type { CVDoc } from "../../ui/src/lib/types";

const DOC: CVDoc = EXAMPLE_CV;

describe("markEdited", () => {
  it("counts, so two different edits never share a hash", () => {
    const once = markEdited("abc");
    const twice = markEdited(once);
    expect(once).toBe("abc~e1");
    expect(twice).toBe("abc~e2");
    expect(new Set([DOC.hash, once, twice]).size).toBe(3);
  });
});

describe("nextLineId", () => {
  it("follows the highest id in use, not the line count", () => {
    expect(nextLineId(DOC)).toBe(`L${DOC.lines.length + 1}`);
  });

  it("never reuses an id when the document has a gap in its numbering", () => {
    // A citation in a saved match is one of these strings, so handing a new
    // line an id that already appears somewhere would silently re-point it.
    const sparse: CVDoc = {
      ...DOC,
      lines: [
        { id: "L1", text: "first", section: "header" },
        { id: "L7", text: "seventh", section: "experience" },
      ],
    };
    expect(nextLineId(sparse)).toBe("L8");
  });
});

describe("appendLine", () => {
  it("stores the answer exactly as typed", () => {
    const answer = "I ran the Kafka consumers for the order feed at a previous job.";
    const next = appendLine(DOC, answer, "experience");
    expect(next.lines.at(-1)?.text).toBe(answer);
  });

  it("trims surrounding whitespace but nothing else", () => {
    const next = appendLine(DOC, "   two sentences.  Second one.   ", "experience");
    expect(next.lines.at(-1)?.text).toBe("two sentences.  Second one.");
  });

  it("marks the line as the user's own", () => {
    const next = appendLine(DOC, "something true", "skills", new Date("2026-10-01T09:00:00Z"));
    expect(next.lines.at(-1)?.added_at).toBe("2026-10-01T09:00:00.000Z");
  });

  it("leaves the parsed lines untouched and unmarked", () => {
    const next = appendLine(DOC, "something true", "skills");
    expect(next.lines.slice(0, DOC.lines.length)).toEqual(DOC.lines);
    expect(next.lines.slice(0, DOC.lines.length).every((line) => !line.added_at)).toBe(true);
  });

  it("moves the hash, so the match made against the old CV goes stale", () => {
    const next = appendLine(DOC, "something true", "skills");
    expect(next.hash).not.toBe(DOC.hash);
  });

  it("does not mutate the document it was given", () => {
    const before = DOC.lines.length;
    appendLine(DOC, "something true", "skills");
    expect(DOC.lines.length).toBe(before);
  });
});

describe("editLine", () => {
  it("rewrites one line and moves the hash", () => {
    const target = DOC.lines[1]!;
    const next = editLine(DOC, target.id, "corrected text");
    expect(next.lines[1]?.text).toBe("corrected text");
    expect(next.lines[1]?.id).toBe(target.id);
    expect(next.hash).not.toBe(DOC.hash);
  });
});

describe("sectionForCategory", () => {
  it("puts every requirement category somewhere sensible", () => {
    expect(sectionForCategory("education")).toBe("education");
    expect(sectionForCategory("skill")).toBe("skills");
    expect(sectionForCategory("experience")).toBe("experience");
    expect(sectionForCategory("domain")).toBe("experience");
    expect(sectionForCategory("soft")).toBe("experience");
    expect(sectionForCategory("logistics")).toBe("other");
  });
});
