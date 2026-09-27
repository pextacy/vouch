/**
 * The card that leaves the account.
 *
 * Every other artefact this app produces is for the person who made it. This
 * one is built to be posted, so the privacy rule cannot be a matter of the
 * renderer being careful — it has to be structural. `cardFor` reduces a match
 * to counts and enums, `renderCard` can only draw what it is handed, and the
 * first test below is the proof: a match stuffed with distinctive words, and
 * not one of them in the output.
 *
 * The rest hold the two things that would quietly break that. The role title
 * is the only free text that may reach the renderer, so it must be off unless
 * asked for and escaped when it arrives. And the preview has to be the file:
 * one renderer, or the screen starts promising something the download does not
 * deliver.
 */

import { describe, expect, it } from "vitest";

import { CARD_HEIGHT, CARD_WIDTH, cardFor, renderCard, wrap } from "../../ui/src/lib/share";
import type { MatchResult } from "../../ui/src/lib/types";

const STRINGS = {
  headline: "9 of 14 requirements have evidence in my CV. 2 must-haves don't.",
  must: "Must have",
  nice: "Nice to have",
  evidenced: "Evidenced",
  related: "Related",
  missing: "No evidence yet",
  tagline: "Receipts on Anna — tailor every application, invent nothing.",
};

/** Every distinctive word here is something the card must never carry. */
const SECRETS = [
  "Northwind",
  "Ledger",
  "Volta",
  "Kubernetes",
  "reconciliation",
  "Bogazici",
  "https://boards.example.com/posting/9912",
];

function match(overrides: Partial<MatchResult> = {}): MatchResult {
  return {
    version: 1,
    id: "m-1",
    created_at: "2026-09-26T09:00:00Z",
    cv_hash: "cv-1",
    posting: {
      title: "Senior Backend Engineer",
      company: "Northwind Ledger",
      url: "https://boards.example.com/posting/9912",
      hash: "p-1",
      language: "en",
    },
    requirements: [
      {
        id: "R1",
        text: "Production experience with Kubernetes",
        kind: "must",
        category: "skill",
        source_quote: "Production experience with Kubernetes at Volta",
      },
      {
        id: "R2",
        text: "Payment reconciliation",
        kind: "nice",
        category: "domain",
        source_quote: "Payment reconciliation work",
      },
    ],
    evidence: [
      {
        requirement_id: "R1",
        status: "strong",
        line_ids: ["L5"],
        why: "Ran settlement workers at Volta on Kubernetes.",
      },
      {
        requirement_id: "R2",
        status: "missing",
        line_ids: [],
        why: "",
      },
    ],
    summary: {
      total: 14,
      strong: 9,
      partial: 3,
      missing: 2,
      must_missing: 2,
      sentence: "9 of 14 requirements have evidence in your CV. 2 must-haves don't.",
    },
    ...overrides,
  };
}

describe("what the card is allowed to know", () => {
  it("carries nothing but counts, enums and an optional role", () => {
    const card = cardFor(match(), { withRole: false, locale: "en" });

    const text = JSON.stringify(card);
    for (const secret of SECRETS) {
      expect(text, secret).not.toContain(secret);
    }
    expect(card.role).toBeNull();
  });

  it("reduces requirements to their kind and status", () => {
    const card = cardFor(match(), { withRole: false, locale: "en" });

    expect(card.marks).toEqual([
      { kind: "must", status: "strong" },
      { kind: "nice", status: "missing" },
    ]);
  });

  it("calls a requirement with no verdict missing rather than dropping it", () => {
    const card = cardFor(match({ evidence: [] }), { withRole: false, locale: "en" });

    expect(card.marks.map((mark) => mark.status)).toEqual(["missing", "missing"]);
  });
});

describe("the rendered card", () => {
  it("contains nothing from the CV, the employer or the posting's wording", () => {
    const svg = renderCard(cardFor(match(), { withRole: false, locale: "en" }), STRINGS);

    for (const secret of SECRETS) {
      expect(svg, secret).not.toContain(secret);
    }
  });

  it("is an SVG at the ratio every platform crops to", () => {
    const svg = renderCard(cardFor(match(), { withRole: false, locale: "en" }), STRINGS);

    expect(svg.startsWith("<svg")).toBe(true);
    expect(svg).toContain(`width="${CARD_WIDTH}"`);
    expect(svg).toContain(`height="${CARD_HEIGHT}"`);
    expect(svg.trimEnd().endsWith("</svg>")).toBe(true);
  });

  it("ships no inline style, because the bundle's CSP drops one", () => {
    const svg = renderCard(cardFor(match(), { withRole: false, locale: "en" }), STRINGS);

    expect(svg).not.toContain("<style");
    expect(svg).not.toContain("style=");
  });

  it("draws a shape per requirement, so it survives being greyscaled", () => {
    const card = cardFor(match(), { withRole: false, locale: "en" });
    const svg = renderCard(card, STRINGS);

    // One filled mark for the strong, one open bracket for the missing.
    expect(svg).toContain('fill="#F4EA3A"');
    expect(svg).toContain('stroke="#D8DEE8"');
  });

  it("says the sentence the user is posting, wrapped into lines", () => {
    const svg = renderCard(cardFor(match(), { withRole: false, locale: "en" }), STRINGS);

    // SVG has no text flow, so the headline arrives as one <text> per line.
    // Joining them back is what a reader does with their eyes.
    const said = [...svg.matchAll(/<text[^>]*>([^<]*)<\/text>/g)]
      .map((hit) => hit[1])
      .join(" ");
    expect(said).toContain(STRINGS.headline);
  });
});

describe("the role title", () => {
  it("is on the card only when the user asks for it", () => {
    const off = renderCard(cardFor(match(), { withRole: false, locale: "en" }), STRINGS);
    const on = renderCard(cardFor(match(), { withRole: true, locale: "en" }), STRINGS);

    expect(off).not.toContain("Senior Backend Engineer");
    expect(on).toContain("Senior Backend Engineer");
  });

  it("never brings the company with it", () => {
    const on = renderCard(cardFor(match(), { withRole: true, locale: "en" }), STRINGS);

    expect(on).not.toContain("Northwind");
  });

  it("is escaped, because it comes from a posting", () => {
    const hostile = match({
      posting: { ...match().posting, title: '</text><script>alert("x")</script>' },
    });

    const svg = renderCard(cardFor(hostile, { withRole: true, locale: "en" }), STRINGS);

    expect(svg).not.toContain("<script");
    expect(svg).toContain("&lt;/text&gt;");
  });

  it("is absent when the posting never named one", () => {
    const untitled = match({ posting: { ...match().posting, title: null } });

    expect(cardFor(untitled, { withRole: true, locale: "en" }).role).toBeNull();
  });
});

describe("wrap", () => {
  it("breaks on spaces and keeps the words in order", () => {
    expect(wrap("one two three four", 9)).toEqual(["one two", "three", "four"]);
  });

  it("leaves a long word long rather than hyphenating it", () => {
    expect(wrap("antidisestablishmentarianism", 8)).toEqual(["antidisestablishmentarianism"]);
  });

  it("returns nothing for nothing", () => {
    expect(wrap("   ", 10)).toEqual([]);
  });
});
