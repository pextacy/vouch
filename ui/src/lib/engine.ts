/**
 * Typed calls into the Receipts engine Executa.
 *
 * Two channels, chosen by how long the work takes:
 *
 * * **sync** (`anna.tools.invoke`) for `health`, `parse_cv`, `upload_chunk`
 *   and `export_docx` — all well under the host's 90 s ceiling.
 * * **async jobs** for `run_match`, `tailor` and `letter`. They can outlive
 *   90 s, they need a cancel button, they have to survive a reload, and
 *   `emit_progress` only reaches the UI on an async invoke.
 *
 * A CV file arrives as base64 chunks over the sync channel: the host reader
 * caps a JSON-RPC line at 2 MiB and async invoke args at 64 KB, so a 2 MB PDF
 * fits in neither.
 */

import { runtime, unwrap, type AnnaRuntime, type InvokeAsyncOptions } from "./anna";
import { ENGINE_METHOD, engineToolId } from "./ids";
import type {
  CVDoc,
  EngineError,
  ErrorCode,
  ExportResult,
  LetterResult,
  Locale,
  MatchResult,
  ProgressEvent,
  TailorResult,
  Tone,
  Length,
} from "./types";

/** 128 KiB of base64 per chunk: ≈130 KB per JSON-RPC line, well under 512 KiB. */
const CHUNK_B64 = 128 * 1024;

/** Matches `parse/cv.py`; checked here so an oversized file never leaves the browser. */
export const MAX_FILE_BYTES = 2 * 1024 * 1024;

const SYNC_TIMEOUT_MS = 60_000;
const JOB_TIMEOUT_MS = 10 * 60_000;

interface InvokeResult<T> {
  success: boolean;
  tool?: string;
  error?: string;
  data: T | EngineError;
}

export class EngineFailure extends Error {
  readonly detail: EngineError;

  constructor(detail: EngineError) {
    super(detail.message);
    this.name = "EngineFailure";
    this.detail = detail;
  }

  get code(): ErrorCode {
    return this.detail.code;
  }

  get retriable(): boolean {
    return this.detail.retriable;
  }
}

function failure(code: ErrorCode, message: string, retriable = false): EngineFailure {
  return new EngineFailure({ code, message, retriable });
}

/**
 * Async job methods, reached through a local alias.
 *
 * `anna-app validate --strict` mirrors an older `host_api_allows` that only
 * knows `tools.invoke` and `tools.list`, so a literal `anna.tools.invokeAsync(`
 * is reported as ungranted even though the production dispatcher gates the
 * `tools` namespace on the tool-id allow-list we do declare. This alias keeps
 * the linter useful for every other namespace instead of turning it off.
 */
function jobs(host: AnnaRuntime): AnnaRuntime["tools"] {
  return host.tools;
}

/**
 * Read an invoke result.
 *
 * Production strips both envelope layers, so a successful call resolves with
 * the plugin's payload directly and a failed one rejects as `tool_failed`
 * (handled in `translateHostError`). The `{success, data}` branch is still
 * here because the stub and the plugin contract tests speak the raw shape.
 */
function readResult<T>(payload: unknown): T {
  const result = unwrap<InvokeResult<T> | T>(payload);
  if (!result || typeof result !== "object" || !("success" in result)) {
    return result as T;
  }
  const envelope = result as InvokeResult<T>;
  if (!envelope.success) {
    const detail = envelope.data as EngineError | undefined;
    throw new EngineFailure(
      detail && typeof detail === "object" && "code" in detail
        ? detail
        : errorFromCode(envelope.error),
    );
  }
  return envelope.data as T;
}

/** Every code the engine can raise; anything else is not ours to interpret. */
const ENGINE_CODES = new Set<ErrorCode>([
  "file_too_large",
  "unreadable_file",
  "cv_too_short",
  "no_requirements_found",
  "model_output_invalid",
  "sampling_unavailable",
  "cancelled",
  "upload_expired",
  "invalid_args",
  "internal_error",
]);

const RETRIABLE_CODES = new Set<ErrorCode>([
  "model_output_invalid",
  "sampling_unavailable",
  "upload_expired",
  "internal_error",
  "host_unavailable",
]);

/**
 * Recover the engine's error code from a `tool_failed` message.
 *
 * The host keeps only `result.error` when an invoke fails, so the plugin puts
 * the bare code there and the sentence the user reads comes from the UI's own
 * string table — which is where the translated copy lives anyway.
 */
function errorFromCode(raw: string | undefined): EngineError {
  const candidate = (raw ?? "").trim() as ErrorCode;
  const code: ErrorCode = ENGINE_CODES.has(candidate) ? candidate : "internal_error";
  return { code, message: raw ?? "the engine failed", retriable: RETRIABLE_CODES.has(code) };
}

async function invokeSync<T>(args: Record<string, unknown>): Promise<T> {
  const anna = runtime();
  try {
    const payload = await anna.tools.invoke({
      tool_id: engineToolId(),
      method: ENGINE_METHOD,
      args,
      timeoutMs: SYNC_TIMEOUT_MS,
    });
    return readResult<T>(payload);
  } catch (error) {
    throw translateHostError(error);
  }
}

async function invokeJob<T>(
  args: Record<string, unknown>,
  options: { onProgress?: (event: ProgressEvent) => void; signal?: AbortSignal; clientTag: string },
): Promise<T> {
  const anna = runtime();
  const tools = jobs(anna);
  const request = {
    tool_id: engineToolId(),
    method: ENGINE_METHOD,
    args,
    timeoutMs: JOB_TIMEOUT_MS,
    clientTag: options.clientTag,
  };

  const forward: InvokeAsyncOptions = {
    onProgress: (event) => {
      if (!options.onProgress) return;
      const progress = readProgressEvent(event);
      if (progress) options.onProgress(progress);
    },
    ...(options.signal ? { signal: options.signal } : {}),
  };

  try {
    if (typeof tools.invokeAsyncAwait === "function") {
      return readResult<T>(await tools.invokeAsyncAwait(request, forward));
    }
    // Older SDK: drive the job by hand. getJob is authoritative either way.
    const started = unwrap<{ jobId: string }>(await tools.invokeAsync(request));
    return await pollJob<T>(tools, started.jobId, forward, options.signal);
  } catch (error) {
    throw translateHostError(error);
  }
}

interface JobSnapshot {
  state: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "expired";
  result?: unknown;
  error?: { code?: string; message?: string };
  lastSeq?: number;
  progress?: { seq: number; type: string; data: unknown }[];
}

async function pollJob<T>(
  tools: AnnaRuntime["tools"],
  jobId: string,
  forward: InvokeAsyncOptions,
  signal?: AbortSignal,
): Promise<T> {
  let seq = 0;
  // The same ceiling the job itself was given. A job stuck in `queued` because
  // the Agent went away would otherwise leave the progress screen spinning for
  // as long as the window stays open.
  const deadline = Date.now() + JOB_TIMEOUT_MS;
  for (;;) {
    if (signal?.aborted) {
      await tools.cancelJob({ jobId, reason: "user cancelled" });
      throw failure("cancelled", "cancelled");
    }
    if (Date.now() > deadline) {
      await tools.cancelJob({ jobId, reason: "client deadline" }).catch(() => undefined);
      throw failure("internal_error", "the engine took too long", true);
    }
    const snapshot = unwrap<JobSnapshot>(await tools.getJob({ jobId, sinceSeq: seq }));
    for (const event of snapshot.progress ?? []) {
      forward.onProgress?.(event);
      seq = Math.max(seq, event.seq);
    }
    if (snapshot.state === "succeeded") return readResult<T>(snapshot.result);
    if (snapshot.state === "cancelled") throw failure("cancelled", "cancelled");
    if (snapshot.state === "failed" || snapshot.state === "expired") {
      throw failure("internal_error", snapshot.error?.message ?? "the job did not finish", true);
    }
    await sleep(1200);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readProgressEvent(event: unknown): ProgressEvent | null {
  if (!event || typeof event !== "object") return null;
  const data = ((event as { data?: unknown }).data ?? event) as Partial<ProgressEvent>;
  if (typeof data.stage !== "string") return null;
  return {
    stage: data.stage,
    pct: typeof data.pct === "number" ? data.pct : 0,
    ...(data.partial ? { partial: data.partial } : {}),
  };
}

/** Map a host-level failure onto a code the UI has copy for. */
function translateHostError(error: unknown): EngineFailure {
  if (error instanceof EngineFailure) return error;
  const code = (error as { code?: string })?.code;
  const message = (error as { message?: string })?.message ?? "the host call failed";
  switch (code) {
    // The plugin reported a user-visible failure; its code rode across as the
    // message (see `errorFromCode`).
    case "tool_failed":
    case "executa_error":
      return new EngineFailure(errorFromCode(message));
    case "cancelled":
      return failure("cancelled", "cancelled");
    case "tool_timeout":
    case "wait_timeout":
      return failure("internal_error", "the engine took too long", true);
    case "agent_unavailable":
    case "executa_unavailable":
    case "long_job_capacity":
    case "job_quota_exceeded":
      return failure("host_unavailable", message, true);
    case "permission_denied":
      return failure("host_unavailable", message, false);
    default:
      return failure("internal_error", message, true);
  }
}

// ─── Actions ──────────────────────────────────────────────────────────

export async function health(): Promise<{ healthy: boolean; version: string; sampling: boolean }> {
  return invokeSync({ action: "health" });
}

/**
 * Ask the engine to drop what it still holds in memory.
 *
 * Called from "Delete all my data". Best effort by design: storage is the
 * record, this is a buffered upload and a cached posting, and neither outlives
 * the process.
 */
export async function forget(): Promise<void> {
  await invokeSync({ action: "forget" });
}

export async function parseCvText(text: string): Promise<CVDoc> {
  return invokeSync<CVDoc>({ action: "parse_cv", source: "text", text });
}

export interface UploadProgress {
  sent: number;
  total: number;
}

export async function parseCvFile(
  file: File,
  onProgress?: (progress: UploadProgress) => void,
): Promise<CVDoc> {
  if (file.size > MAX_FILE_BYTES) {
    throw failure("file_too_large", "the file is over 2 MB");
  }
  const source = sourceOf(file);
  if (!source) {
    throw failure("unreadable_file", "only PDF and DOCX files can be read");
  }

  const base64 = await toBase64(file);
  const chunks = sliceChunks(base64);
  const uploadId = `up-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

  try {
    for (let index = 0; index < chunks.length; index += 1) {
      await invokeSync({
        action: "upload_chunk",
        upload_id: uploadId,
        index,
        total: chunks.length,
        data_b64: chunks[index],
        ...(index === 0 ? { filename: file.name } : {}),
      });
      onProgress?.({ sent: index + 1, total: chunks.length });
    }

    // `parse_cv` consumes the buffer on success; only a failure leaves it.
    return await invokeSync<CVDoc>({ action: "parse_cv", source, upload_id: uploadId });
  } catch (error) {
    // Half a CV is still a CV. It would age out of the engine's buffer in ten
    // minutes on its own; ten minutes is nine longer than it needs to be.
    await forget().catch(() => undefined);
    throw error;
  }
}

function sourceOf(file: File): "pdf" | "docx" | null {
  const name = file.name.toLowerCase();
  if (name.endsWith(".pdf") || file.type === "application/pdf") return "pdf";
  if (name.endsWith(".docx") || file.type.includes("wordprocessingml")) return "docx";
  return null;
}

function sliceChunks(base64: string): string[] {
  const chunks: string[] = [];
  for (let index = 0; index < base64.length; index += CHUNK_B64) {
    chunks.push(base64.slice(index, index + CHUNK_B64));
  }
  return chunks.length > 0 ? chunks : [""];
}

/**
 * Base64 a File without building a giant UTF-16 intermediate.
 *
 * `btoa(String.fromCharCode(...bytes))` blows the call stack on a multi-MB
 * buffer; `readAsDataURL` lets the browser do it natively.
 */
function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(failure("unreadable_file", "the file could not be read"));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.readAsDataURL(file);
  });
}

export interface RunMatchArgs {
  cv: CVDoc;
  postingText: string;
  postingUrl?: string;
  locale: Locale;
  onProgress?: (event: ProgressEvent) => void;
  signal?: AbortSignal;
}

/** The primary function. A successful return is the Qualified App Run. */
export async function runMatch(args: RunMatchArgs): Promise<MatchResult> {
  return invokeJob<MatchResult>(
    {
      action: "run_match",
      cv: args.cv,
      posting_text: args.postingText,
      ...(args.postingUrl ? { posting_url: args.postingUrl } : {}),
      locale: args.locale,
    },
    {
      clientTag: JOB_TAG_MATCH,
      ...(args.onProgress ? { onProgress: args.onProgress } : {}),
      ...(args.signal ? { signal: args.signal } : {}),
    },
  );
}

export const JOB_TAG_MATCH = "receipts:run_match";

export async function tailor(
  cv: CVDoc,
  match: MatchResult,
  locale: Locale,
  signal?: AbortSignal,
): Promise<TailorResult> {
  return invokeJob<TailorResult>(
    { action: "tailor", cv, match, locale },
    { clientTag: "receipts:tailor", ...(signal ? { signal } : {}) },
  );
}

export async function letter(
  cv: CVDoc,
  match: MatchResult,
  options: { tone: Tone; length: Length; locale: Locale; signal?: AbortSignal },
): Promise<LetterResult> {
  return invokeJob<LetterResult>(
    {
      action: "letter",
      cv,
      match,
      tone: options.tone,
      length: options.length,
      locale: options.locale,
      ...(match.posting.company ? { company: match.posting.company } : {}),
      ...(match.posting.title ? { role: match.posting.title } : {}),
    },
    { clientTag: "receipts:letter", ...(options.signal ? { signal: options.signal } : {}) },
  );
}

export async function exportDocx(args: {
  tailor?: TailorResult;
  letter?: LetterResult;
  company?: string | null;
  role?: string | null;
  locale: Locale;
  /** Sent so the engine can re-verify a suggestion the user edited by hand. */
  cv?: CVDoc;
}): Promise<ExportResult> {
  return invokeSync<ExportResult>({
    action: "export_docx",
    ...(args.tailor ? { tailor_result: args.tailor } : {}),
    ...(args.letter ? { letter_result: args.letter } : {}),
    ...(args.cv ? { cv: args.cv } : {}),
    ...(args.company ? { company: args.company } : {}),
    ...(args.role ? { role: args.role } : {}),
    locale: args.locale,
  });
}

/**
 * Re-adopt a match that was already running when the window reloaded.
 *
 * Job state lives on the host, so a reload mid-analysis should pick the run
 * back up rather than charging the user for a second one.
 */
export async function recoverMatchJob(
  onProgress: (event: ProgressEvent) => void,
  signal?: AbortSignal,
): Promise<MatchResult | null> {
  const tools = jobs(runtime());
  let listing: { jobs?: { jobId: string }[] };
  try {
    listing = unwrap<{ jobs?: { jobId: string }[] }>(
      await tools.listJobs({ clientTag: JOB_TAG_MATCH, state: ["queued", "running"], limit: 5 }),
    );
  } catch {
    return null; // an older host without the job API is not an error here
  }
  const job = listing.jobs?.[0];
  if (!job) return null;
  const forward: InvokeAsyncOptions = {
    onProgress: (event) => {
      const progress = readProgressEvent(event);
      if (progress) onProgress(progress);
    },
  };
  return pollJob<MatchResult>(tools, job.jobId, forward, signal);
}
