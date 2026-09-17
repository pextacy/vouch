/**
 * The engine client, driven against the preview stub.
 *
 * The stub answers in the same shape production does — payload unwrapped on
 * success, `tool_failed` with the code as its message on failure — so these
 * tests cover the translation layer that turns a host rejection into a code
 * the UI has copy for.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { connect, isPreview } from "../../ui/src/lib/anna";
import { EngineFailure, health, letter, parseCvText, runMatch, tailor } from "../../ui/src/lib/engine";
import { engineToolId } from "../../ui/src/lib/ids";
import { EXAMPLE_POSTING } from "../../ui/src/lib/example";

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
});

describe("connection", () => {
  it("falls back to preview mode when there is no host", () => {
    expect(isPreview()).toBe(true);
  });

  it("resolves the dev tool id when no sidecar is present", () => {
    expect(engineToolId()).toBe("tool-dev-receipts-engine");
  });
});

describe("health", () => {
  it("returns the engine's liveness payload", async () => {
    await expect(health()).resolves.toMatchObject({ healthy: true });
  });
});

describe("parse_cv", () => {
  it("returns numbered lines", async () => {
    const doc = await parseCvText(CV_TEXT);
    expect(doc.lines[0]?.id).toBe("L1");
    expect(doc.lines.length).toBeGreaterThan(4);
  });

  it("surfaces a short CV as cv_too_short, not as an unknown failure", async () => {
    await expect(parseCvText("too short")).rejects.toSatisfy(
      (error: unknown) => error instanceof EngineFailure && error.code === "cv_too_short",
    );
  });

  it("marks a short CV as not worth retrying", async () => {
    const failure = await parseCvText("nope").catch((error: unknown) => error as EngineFailure);
    expect(failure.retriable).toBe(false);
  });
});

describe("run_match", () => {
  it("reports every stage in order", async () => {
    const doc = await parseCvText(CV_TEXT);
    const stages: string[] = [];

    const result = await runMatch({
      cv: doc,
      postingText: EXAMPLE_POSTING,
      locale: "en",
      onProgress: (event) => stages.push(event.stage),
    });

    expect(stages).toEqual(["normalize", "extract", "match", "guard", "summarize", "done"]);
    expect(result.requirements.length).toBeGreaterThan(0);
    expect(result.evidence.length).toBe(result.requirements.length);
  });

  it("counts the summary consistently with the evidence", async () => {
    const doc = await parseCvText(CV_TEXT);
    const result = await runMatch({ cv: doc, postingText: EXAMPLE_POSTING, locale: "en" });
    const counted = result.evidence.reduce(
      (acc, item) => ({ ...acc, [item.status]: (acc[item.status] ?? 0) + 1 }),
      {} as Record<string, number>,
    );
    expect(counted.strong ?? 0).toBe(result.summary.strong);
    expect(counted.missing ?? 0).toBe(result.summary.missing);
  });

  it("aborts as `cancelled` rather than as a failure", async () => {
    const doc = await parseCvText(CV_TEXT);
    const controller = new AbortController();
    const pending = runMatch({
      cv: doc,
      postingText: EXAMPLE_POSTING,
      locale: "en",
      signal: controller.signal,
      onProgress: () => controller.abort(),
    });
    await expect(pending).rejects.toSatisfy(
      (error: unknown) => error instanceof EngineFailure && error.code === "cancelled",
    );
  });
});

/**
 * Preview matches are matches.
 *
 * The stub used to hand back the recorded example unchanged, id and all, so
 * every preview run produced a match called "example" — and a tracker row
 * pointing at it reopened the read-only example instead of the user's own
 * match, hiding Accept, Skip, Edit and the tone switch behind a route that
 * looked right. A fresh identity per run is what keeps preview mode a
 * rehearsal rather than a diorama.
 */
describe("preview identity", () => {
  it("gives every run its own match id", async () => {
    const doc = await parseCvText(CV_TEXT);
    const first = await runMatch({ cv: doc, postingText: EXAMPLE_POSTING, locale: "en" });
    const second = await runMatch({ cv: doc, postingText: EXAMPLE_POSTING, locale: "en" });

    expect(first.id).not.toBe("example");
    expect(second.id).not.toBe(first.id);
  });

  it("stamps the tailored bullets and the letter with the match they belong to", async () => {
    const doc = await parseCvText(CV_TEXT);
    const match = await runMatch({ cv: doc, postingText: EXAMPLE_POSTING, locale: "en" });

    const bullets = await tailor(doc, match, "en");
    const written = await letter(doc, match, { tone: "plain", length: "short", locale: "en" });

    expect(bullets.match_id).toBe(match.id);
    expect(written.match_id).toBe(match.id);
  });
});
