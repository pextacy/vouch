/**
 * Where the letter's names come from.
 *
 * The engine stores a paragraph exactly as the verifier approved it, which
 * means `[Company]` and `[Role]` are still in the text: substituting them
 * earlier would mean the paragraph a reader sees is not the paragraph that was
 * checked, and `scripts/eval_match.py` re-checks stored letters against the CV
 * knowing nothing else about the posting. The screen is the point of use, so
 * the names go in here.
 */

import { describe, expect, it } from "vitest";

import {
  namesFromMatch,
  resolvePlaceholders,
  resolvedParagraphs,
} from "../../ui/src/lib/letter";
import { EXAMPLE_LETTER, EXAMPLE_MATCH } from "../../ui/src/lib/example";
import type { LetterResult, MatchResult } from "../../ui/src/lib/types";

const match = {
  ...EXAMPLE_MATCH,
  posting: { ...EXAMPLE_MATCH.posting, company: "Northwind Ledger", title: "Senior Backend Engineer" },
} as MatchResult;

const stored = {
  match_id: match.id,
  tone: "plain",
  paragraphs: [
    { text: "I am writing about the [Role] role at [Company].", line_ids: [] },
    { text: "Dear [Hiring Manager], I built reconciliation services in Go.", line_ids: ["L3"] },
  ],
  placeholders: ["[Hiring Manager]"],
} as LetterResult;

describe("resolvePlaceholders", () => {
  it("fills in the names the posting gave us", () => {
    expect(resolvePlaceholders("the [Role] role at [Company]", namesFromMatch(match))).toBe(
      "the Senior Backend Engineer role at Northwind Ledger",
    );
  });

  it("leaves a placeholder the app cannot resolve alone", () => {
    expect(resolvePlaceholders("Dear [Hiring Manager],", namesFromMatch(match))).toBe(
      "Dear [Hiring Manager],",
    );
  });

  it("leaves everything alone when the posting named nobody", () => {
    const text = "the [Role] role at [Company]";
    expect(resolvePlaceholders(text, { company: null, role: null })).toBe(text);
  });
});

describe("resolvedParagraphs", () => {
  it("resolves every paragraph and keeps the citations", () => {
    const paragraphs = resolvedParagraphs(stored, namesFromMatch(match));
    expect(paragraphs[0]?.text).toBe(
      "I am writing about the Senior Backend Engineer role at Northwind Ledger.",
    );
    expect(paragraphs[1]?.line_ids).toEqual(["L3"]);
  });

  it("does not touch the stored result", () => {
    resolvedParagraphs(stored, namesFromMatch(match));
    expect(stored.paragraphs[0]?.text).toBe("I am writing about the [Role] role at [Company].");
  });

  it("is a no-op on a letter that already reads as finished", () => {
    // The example fixture is the rendered form, so resolving it changes
    // nothing — which is also what makes it an honest example of the output.
    const paragraphs = resolvedParagraphs(EXAMPLE_LETTER, namesFromMatch(EXAMPLE_MATCH));
    expect(paragraphs.map((p) => p.text)).toEqual(EXAMPLE_LETTER.paragraphs.map((p) => p.text));
  });
});
