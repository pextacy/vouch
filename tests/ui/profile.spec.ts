/**
 * The profile, and the headline it is willing to leave empty.
 *
 * This is the one generated surface with no posting behind it, so it is the
 * one with no borrowed vocabulary: a term survives only if a CV line has it.
 * The screen is built for the case where the headline does not survive —
 * saying so out loud, because the line a recruiter reads first is the worst
 * place in the product to let a model invent.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { connect } from "../../ui/src/lib/anna";
import { profile } from "../../ui/src/lib/engine";
import { EXAMPLE_CV } from "../../ui/src/lib/example";
import type { CVDoc } from "../../ui/src/lib/types";

beforeAll(async () => {
  await connect();
});

describe("profile, through the preview stub", () => {
  it("writes an About that cites the lines it stands on", async () => {
    const result = await profile(EXAMPLE_CV, { locale: "en" });

    expect(result.about.length).toBeGreaterThan(0);
    for (const paragraph of result.about) {
      expect(paragraph.line_ids.length).toBeGreaterThan(0);
      for (const id of paragraph.line_ids) {
        expect(EXAMPLE_CV.lines.some((line) => line.id === id)).toBe(true);
      }
    }
  });

  it("stamps the CV it was written from", async () => {
    const result = await profile(EXAMPLE_CV, { locale: "en" });

    expect(result.cv_hash).toBe(EXAMPLE_CV.hash);
  });

  it("leaves the headline empty rather than inventing one", async () => {
    // Preview mode has no model, so it declines the half that cannot be
    // assembled honestly — which is the state the screen is written for.
    const result = await profile(EXAMPLE_CV, { locale: "en" });

    expect(result.headline).toBe("");
    expect(result.headline_line_ids).toEqual([]);
  });

  it("never writes from the header", async () => {
    const result = await profile(EXAMPLE_CV, { locale: "en" });
    const header = EXAMPLE_CV.lines.filter((line) => line.section === "header").map((l) => l.id);

    const cited = result.about.flatMap((paragraph) => paragraph.line_ids);
    expect(cited.some((id) => header.includes(id))).toBe(false);
  });

  it("says nothing at all about a CV with no experience in it", async () => {
    const bare: CVDoc = {
      ...EXAMPLE_CV,
      lines: EXAMPLE_CV.lines.filter((line) => line.section === "header"),
    };

    const result = await profile(bare, { locale: "en" });

    expect(result.about).toEqual([]);
  });
});
