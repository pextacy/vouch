/**
 * The one place that talks to the Anna host.
 *
 * `AnnaAppRuntime.connect()` only resolves inside the host iframe. Opened in a
 * plain browser tab — `pnpm --dir ui dev`, a designer looking at the bundle —
 * it throws, so we fall back to the fixture-backed stub and show
 * `PreviewBanner`. Without that, the whole UI would be undevelopable outside
 * the harness.
 *
 * Every signature here is recorded in docs/api-notes.md §5. Do not add a call
 * without adding the method to `manifest.ui.host_api` — `anna-app validate
 * --strict` greps this file and will fail the build.
 */

import { createStub } from "./stub";
import type { ProgressEvent } from "./types";

/** SDK module served by the host; the CSP allow-lists this origin. */
const SDK_URL = "/static/anna-apps/_sdk/latest/index.js";

export interface JobHandle {
  jobId: string;
}

export interface InvokeAsyncOptions {
  onProgress?: (event: { seq: number; type: string; data: unknown }) => void;
  signal?: AbortSignal;
}

export interface AnnaRuntime {
  readonly windowUuid?: string;
  readonly entryPayload?: unknown;
  readonly runtimeState?: Record<string, unknown>;
  tools: {
    invoke(args: {
      tool_id: string;
      method?: string;
      args?: unknown;
      timeoutMs?: number;
    }): Promise<unknown>;
    invokeAsync(args: {
      tool_id: string;
      method?: string;
      args?: unknown;
      timeoutMs?: number;
      clientTag?: string;
    }): Promise<unknown>;
    invokeAsyncAwait?(args: unknown, opts?: InvokeAsyncOptions): Promise<unknown>;
    getJob(args: { jobId: string; sinceSeq?: number; limit?: number }): Promise<unknown>;
    cancelJob(args: { jobId: string; reason?: string }): Promise<unknown>;
    listJobs(args?: {
      tool_id?: string;
      state?: string | string[];
      clientTag?: string;
      limit?: number;
    }): Promise<unknown>;
  };
  storage: {
    get(args: { key: string }): Promise<unknown>;
    set(args: { key: string; value: unknown }): Promise<unknown>;
    delete(args: { key: string }): Promise<unknown>;
    list(args: { prefix?: string; cursor?: string; limit?: number }): Promise<unknown>;
  };
  files: {
    upload_init(args: {
      path: string;
      content_type: string;
      size: number;
      ttl_seconds?: number;
    }): Promise<unknown>;
    upload_finalize(args: { path: string; etag?: string; size?: number }): Promise<unknown>;
    download(args: { path: string; filename?: string }): Promise<unknown>;
  };
  web: {
    fetch(args: {
      urls: string[];
      format?: string;
      max_chars?: number;
      timeout_ms?: number;
    }): Promise<unknown>;
  };
  window: {
    set_title(args: { title: string }): Promise<unknown>;
  };
  on?(event: string, handler: (payload: unknown) => void): () => void;
}

export interface Connection {
  anna: AnnaRuntime;
  /** True when the host is not there and the stub is standing in. */
  preview: boolean;
  entryPayload: unknown;
}

let connection: Connection | null = null;

export async function connect(): Promise<Connection> {
  if (connection) return connection;

  try {
    const module = (await import(/* @vite-ignore */ SDK_URL)) as {
      AnnaAppRuntime: { connect(): Promise<AnnaRuntime> };
    };
    const anna = await module.AnnaAppRuntime.connect();
    connection = { anna, preview: false, entryPayload: anna.entryPayload };
  } catch {
    // Outside the iframe there is no host to talk to. Everything still works
    // against fixtures, minus the model.
    const anna = createStub();
    connection = { anna, preview: true, entryPayload: anna.entryPayload };
  }
  return connection;
}

export function runtime(): AnnaRuntime {
  if (!connection) throw new Error("connect() has not resolved yet");
  return connection.anna;
}

export function isPreview(): boolean {
  return connection?.preview ?? true;
}

/**
 * Unwrap a host RPC response.
 *
 * Some namespaces resolve `{ok, result}` and some resolve the payload
 * directly; the docs show both shapes. Handling each defensively costs one
 * branch and removes a whole class of "works in dev, throws in production".
 */
export function unwrap<T>(response: unknown): T {
  if (!isEnvelope(response)) return response as T;
  if (!response.ok) throw response.error ?? new Error("host rpc failed");
  return response.result as T;
}

/**
 * An envelope needs more than an `ok` field to be recognised as one.
 *
 * A plugin payload is free to have its own `ok: true`, and treating that as
 * the RPC wrapper silently returns `undefined` — a failure mode that looks
 * like a missing feature rather than a parsing bug.
 */
function isEnvelope(value: unknown): value is { ok: boolean; result?: unknown; error?: unknown } {
  if (!value || typeof value !== "object") return false;
  const candidate = value as { ok?: unknown; result?: unknown; error?: unknown };
  if (typeof candidate.ok !== "boolean") return false;
  return "result" in candidate || "error" in candidate;
}

/** Normalise the many shapes a progress event can arrive in. */
export function readProgress(event: unknown): ProgressEvent | null {
  if (!event || typeof event !== "object") return null;
  const candidate = event as { data?: unknown };
  const data = (candidate.data ?? event) as Partial<ProgressEvent>;
  if (typeof data.stage !== "string") return null;
  return {
    stage: data.stage,
    pct: typeof data.pct === "number" ? data.pct : 0,
    ...(data.partial ? { partial: data.partial } : {}),
  };
}
