/**
 * The stand-in host for when there is no host.
 *
 * `AnnaAppRuntime.connect()` only resolves inside the Anna iframe, so opening
 * the bundle in a plain browser tab would otherwise be a blank screen. The
 * stub answers the same RPCs from `localStorage` and the recorded example, so
 * the entire flow is clickable during design work — with `PreviewBanner`
 * making it obvious that nothing here reached a model.
 *
 * It is not a mock of convenience: it enforces the same argument checks the
 * engine does (chunk order, file size, the cv/match hash pairing), so a bug
 * found here is a real bug.
 */

import {
  EXAMPLE_CV,
  EXAMPLE_LETTER,
  EXAMPLE_MATCH,
  EXAMPLE_TAILOR,
} from "./example";
import type { AnnaRuntime } from "./anna";
import type { EngineError } from "./types";

const STORAGE_PREFIX = "receipts.preview.";

interface EngineArgs {
  action?: string;
  [key: string]: unknown;
}

/**
 * The stub mirrors production, not the plugin: the host strips the
 * `{success, data}` envelope before the payload reaches the iframe, and turns
 * a failed invoke into a `tool_failed` rejection whose message is the code.
 * Matching that here is what makes preview mode a real rehearsal.
 */
function ok(data: unknown): unknown {
  return data;
}

function fail(code: EngineError["code"], message: string): never {
  throw { code: "tool_failed", message: code, details: { message } };
}

function readLocal<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key);
    return raw === null ? null : (JSON.parse(raw) as T);
  } catch {
    return null; // private windows and blocked site data both land here
  }
}

function writeLocal(key: string, value: unknown): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
  } catch {
    // Nothing to do: preview state is a convenience, not a guarantee.
  }
}

export function createStub(): AnnaRuntime {
  const uploads = new Map<string, { chunks: string[]; total: number }>();

  function engine(args: EngineArgs): unknown {
    switch (args.action) {
      case "health":
        return ok({ healthy: true, version: "preview", sampling: false, tool_id: "stub" });

      case "upload_chunk": {
        const id = String(args.upload_id ?? "");
        const index = Number(args.index ?? 0);
        const total = Number(args.total ?? 1);
        const existing = uploads.get(id);
        if (index === 0) {
          uploads.set(id, { chunks: [String(args.data_b64 ?? "")], total });
        } else if (!existing) {
          return fail("upload_expired", "upload expired");
        } else if (existing.chunks.length !== index) {
          return fail("invalid_args", "chunks must arrive in order");
        } else {
          existing.chunks.push(String(args.data_b64 ?? ""));
        }
        const upload = uploads.get(id)!;
        return ok({
          received: upload.chunks.length,
          total: upload.total,
          bytes: upload.chunks.join("").length,
          complete: upload.chunks.length === upload.total,
        });
      }

      case "parse_cv": {
        if (args.source === "text") {
          const text = String(args.text ?? "");
          if (text.trim().length < 200) return fail("cv_too_short", "too short");
          return ok(parseTextLocally(text));
        }
        const id = String(args.upload_id ?? "");
        if (!uploads.delete(id)) return fail("upload_expired", "upload expired");
        // A stub cannot read PDF or DOCX bytes — it hands back the example so
        // the rest of the flow stays explorable.
        return ok(EXAMPLE_CV);
      }

      case "run_match":
        return ok(EXAMPLE_MATCH);

      case "tailor":
        return ok(EXAMPLE_TAILOR);

      case "letter":
        return ok({ ...EXAMPLE_LETTER, tone: args.tone ?? "plain" });

      case "export_docx":
        if (!args.tailor_result && !args.letter_result) {
          return fail("invalid_args", "nothing to export");
        }
        return ok({
          filename: "receipts-preview.docx",
          content_b64: "",
          mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        });

      default:
        return fail("invalid_args", `unknown action ${String(args.action)}`);
    }
  }

  /** A deliberately simple split — enough to show real lines from real text. */
  function parseTextLocally(text: string) {
    const lines = text
      .split("\n")
      .map((line) => line.replace(/^\s*[-•*·]\s+/, "").trim())
      .filter(Boolean)
      .slice(0, 80);
    return {
      version: 1,
      hash: `preview-${lines.length}-${text.length}`,
      detected_language: /[ğışçöü]/i.test(text) ? "tr" : "en",
      warnings: [],
      lines: lines.map((line, index) => ({
        id: `L${index + 1}`,
        text: line,
        section: index < 3 ? "header" : "experience",
      })),
    };
  }

  async function settle<T>(value: T, delayMs = 120): Promise<T> {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return value;
  }

  const stagedProgress = [
    { stage: "normalize", pct: 5 },
    { stage: "extract", pct: 30, partial: { requirements: EXAMPLE_MATCH.requirements } },
    {
      stage: "match",
      pct: 70,
      partial: {
        matched: EXAMPLE_MATCH.evidence.map((item) => ({
          id: item.requirement_id,
          status: item.status,
          line_ids: item.line_ids,
        })),
      },
    },
    { stage: "guard", pct: 85 },
    { stage: "summarize", pct: 95 },
    { stage: "done", pct: 100, partial: { summary: EXAMPLE_MATCH.summary } },
  ];

  return {
    entryPayload: undefined,
    runtimeState: {},

    tools: {
      async invoke({ args }) {
        return settle(engine((args ?? {}) as EngineArgs));
      },
      async invokeAsync() {
        return { jobId: "tjob_preview", state: "queued", deadlineMs: 0 };
      },
      async invokeAsyncAwait(request, opts) {
        const { args } = (request ?? {}) as { args?: EngineArgs };
        if (args?.action === "run_match" && opts?.onProgress) {
          for (const [index, event] of stagedProgress.entries()) {
            if (opts.signal?.aborted) throw { code: "cancelled", message: "cancelled" };
            await settle(null, 260);
            opts.onProgress({ seq: index + 1, type: "tool_update", data: event });
          }
        }
        return settle(engine((args ?? {}) as EngineArgs), 80);
      },
      async getJob() {
        return { state: "succeeded", result: EXAMPLE_MATCH, progress: [], lastSeq: 0 };
      },
      async cancelJob() {
        return { cancelled: true };
      },
      async listJobs() {
        return { jobs: [], truncated: false };
      },
    },

    storage: {
      async get({ key }) {
        const value = readLocal<unknown>(key);
        return { value, exists: value !== null };
      },
      async set({ key, value }) {
        writeLocal(key, value);
        return { ok: true };
      },
      async delete({ key }) {
        try {
          localStorage.removeItem(STORAGE_PREFIX + key);
        } catch {
          // see readLocal
        }
        return { ok: true };
      },
      async list() {
        return { items: [], next_cursor: null };
      },
    },

    files: {
      async upload_init() {
        return { upload_id: "preview", put_url: "", headers: {}, expires_at: "" };
      },
      async upload_finalize() {
        return { path: "preview", etag: "preview", generation: 1, size_bytes: 0 };
      },
      async download() {
        throw { code: "not_implemented", message: "downloads need the Anna host" };
      },
    },

    web: {
      async fetch() {
        throw { code: "not_implemented", message: "page fetch needs the Anna host" };
      },
    },

    window: {
      async set_title() {
        return {};
      },
    },

    on() {
      return () => undefined;
    },
  };
}
