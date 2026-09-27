/**
 * The engine client, driven against the preview stub.
 *
 * The stub answers in the same shape production does — payload unwrapped on
 * success, `tool_failed` with the code as its message on failure — so these
 * tests cover the translation layer that turns a host rejection into a code
 * the UI has copy for.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { connect, isPreview, runtime } from "../../ui/src/lib/anna";
import {
  EngineFailure,
  health,
  letter,
  parseCvFile,
  parseCvText,
  runMatch,
  tailor,
} from "../../ui/src/lib/engine";
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

/**
 * `parseCvFile` reads bytes with `FileReader`, which is a DOM API that Node
 * does not have — without this shim the upload path throws before it makes a
 * single call, and a test asserting "we never call forget" passes because it
 * never called anything at all.
 */
class NodeFileReader {
  result: string | null = null;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  readAsDataURL(blob: Blob): void {
    void blob
      .arrayBuffer()
      .then((bytes) => {
        this.result = `data:application/octet-stream;base64,${Buffer.from(bytes).toString("base64")}`;
        this.onload?.();
      })
      .catch(() => this.onerror?.());
  }
}

/**
 * Record the engine args of every sync invoke made while `body` runs, and
 * optionally fail one action the way the host reports an engine failure.
 */
async function recordInvokes(
  body: () => Promise<void>,
  failOn?: string,
): Promise<Record<string, unknown>[]> {
  const calls: Record<string, unknown>[] = [];
  const anna = runtime();
  const original = anna.tools.invoke.bind(anna.tools);
  const previousReader = (globalThis as Record<string, unknown>).FileReader;
  (globalThis as Record<string, unknown>).FileReader = NodeFileReader;
  anna.tools.invoke = async (request: Parameters<typeof original>[0]) => {
    const args = (request.args ?? {}) as Record<string, unknown>;
    calls.push(args);
    if (args.action === failOn) {
      throw { code: "tool_failed", message: "unreadable_file" };
    }
    return original(request);
  };
  try {
    await body();
  } finally {
    anna.tools.invoke = original;
    (globalThis as Record<string, unknown>).FileReader = previousReader;
  }
  return calls;
}

describe("uploads", () => {
  it("cleans up only the upload that failed, not every buffer", async () => {
    // The failure path used to call `forget`, which drops every pending upload
    // and the whole requirement cache. A second window mid-upload would have
    // lost its file to someone else's failed one.
    const calls = await recordInvokes(async () => {
      const file = new File(["not a real pdf"], "cv.pdf", { type: "application/pdf" });
      await parseCvFile(file).catch(() => undefined);
    }, "parse_cv");

    const actions = calls.map((args) => args.action);
    expect(actions).toContain("upload_chunk");
    expect(actions).toContain("discard_upload");
    expect(actions).not.toContain("forget");
  });

  it("names an upload with an unguessable id", async () => {
    const calls = await recordInvokes(async () => {
      const file = new File(["not a real pdf"], "cv.pdf", { type: "application/pdf" });
      await parseCvFile(file).catch(() => undefined);
    });
    const ids = calls
      .map((args) => args.upload_id)
      .filter((id): id is string => typeof id === "string");

    // The id is the only thing that entitles a caller to those bytes, so it
    // carries a UUID's randomness rather than a timestamp and Math.random.
    expect(ids[0]).toMatch(
      /^up-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
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
