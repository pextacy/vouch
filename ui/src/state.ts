/**
 * Application state.
 *
 * One module of signals rather than a store per screen: every screen reads the
 * same CV, the same current match and the same tracker index, and keeping
 * three copies in sync was the alternative.
 *
 * Each long action is a small state machine — `idle → running → done | error`
 * — because "loading" and "failed" are states the UI must render, not
 * conditions to hide.
 */

import { computed, signal } from "@preact/signals";

import { connect, isPreview } from "./lib/anna";
import * as engine from "./lib/engine";
import { EngineFailure } from "./lib/engine";
import { EXAMPLE_CV, EXAMPLE_LETTER, EXAMPLE_MATCH, EXAMPLE_TAILOR } from "./lib/example";
import * as store from "./lib/store";
import type {
  ApplicationStatus,
  CVDoc,
  EngineError,
  ErrorCode,
  LetterResult,
  Length,
  LineId,
  Locale,
  MatchResult,
  ProgressEvent,
  Stage,
  StoredCv,
  TailorResult,
  Tone,
  TrackerEntry,
} from "./lib/types";
import { detectLocale, setLocale } from "./i18n";
import { navigate } from "./router";

export type Phase = "idle" | "running" | "done" | "error";
export type Theme = "system" | "light" | "dark";

// ─── Session ──────────────────────────────────────────────────────────

export const ready = signal(false);
export const preview = signal(false);
export const theme = signal<Theme>("system");

// ─── CV ───────────────────────────────────────────────────────────────

export const cv = signal<StoredCv | null>(null);
export const cvPhase = signal<Phase>("idle");
export const cvUpload = signal<{ sent: number; total: number } | null>(null);

// ─── Match ────────────────────────────────────────────────────────────

export const postingText = signal("");
export const postingUrl = signal("");
export const urlPhase = signal<Phase>("idle");

export const matchPhase = signal<Phase>("idle");
export const currentMatch = signal<MatchResult | null>(null);
export const progress = signal<ProgressEvent | null>(null);
export const arrivedEvidence = signal<Set<string>>(new Set());

export const tailorPhase = signal<Phase>("idle");
export const tailorResult = signal<TailorResult | null>(null);
export const acceptedBullets = signal<Record<string, string>>({});

export const letterPhase = signal<Phase>("idle");
export const letterResult = signal<LetterResult | null>(null);
export const letterTone = signal<Tone>("plain");
export const letterLength = signal<Length>("standard");

export const exportPhase = signal<Phase>("idle");

// ─── Tracker ──────────────────────────────────────────────────────────

export const tracker = signal<TrackerEntry[]>([]);

// ─── Errors ───────────────────────────────────────────────────────────

export const error = signal<EngineError | null>(null);

/** True while a recorded example is on screen; nothing here hit the model. */
export const showingExample = signal(false);

export const hasCv = computed(() => cv.value !== null);

let matchController: AbortController | null = null;

// ─── Boot ─────────────────────────────────────────────────────────────

export async function boot(): Promise<void> {
  const connection = await connect();
  preview.value = isPreview();

  const profile = await store.loadProfile();
  const chosen: Locale = profile?.locale ?? detectLocale();
  setLocale(chosen);
  if (!profile) {
    await store.saveProfile({
      locale: chosen,
      onboarding_done: false,
      created_at: new Date().toISOString(),
    });
  }

  cv.value = await store.loadCv();
  tracker.value = await store.loadIndex();
  ready.value = true;

  applyEntryPayload(connection.entryPayload);
  void adoptRunningMatch();
}

/**
 * A posting handed over by the assistant (`#receipts` + text) should land the
 * user on the New match screen with the box already filled, not on a blank
 * onboarding page they have to navigate out of.
 */
function applyEntryPayload(payload: unknown): void {
  if (!payload || typeof payload !== "object") return;
  const text = (payload as { posting_text?: unknown }).posting_text;
  if (typeof text === "string" && text.trim()) {
    postingText.value = text;
    navigate(cv.value ? "/new" : "/cv/add");
  }
}

/** Re-attach to a match that was still running when the window reloaded. */
async function adoptRunningMatch(): Promise<void> {
  if (preview.value) return;
  try {
    const result = await engine.recoverMatchJob((event) => applyProgress(event));
    if (result) {
      await finishMatch(result);
    }
  } catch {
    // Nothing to recover, or the host has no job API. Either is fine.
  }
}

// ─── CV actions ───────────────────────────────────────────────────────

export async function addCvFromText(text: string): Promise<void> {
  await withCv(() => engine.parseCvText(text), null);
}

export async function addCvFromFile(file: File): Promise<void> {
  cvUpload.value = { sent: 0, total: 1 };
  await withCv(
    () => engine.parseCvFile(file, (value) => (cvUpload.value = value)),
    file.name,
  );
  cvUpload.value = null;
}

async function withCv(run: () => Promise<CVDoc>, filename: string | null): Promise<void> {
  cvPhase.value = "running";
  error.value = null;
  try {
    const doc = await run();
    const stored: StoredCv = { doc, filename, updated_at: new Date().toISOString() };
    await store.saveCv(stored);
    cv.value = stored;
    cvPhase.value = "done";
    navigate("/cv/preview");
  } catch (failure) {
    cvPhase.value = "error";
    report(failure);
  }
}

/** Fix a misread line in place. The hash stays: the text the model sees changed. */
export async function editCvLine(id: LineId, text: string): Promise<void> {
  const current = cv.value;
  if (!current) return;
  const lines = current.doc.lines.map((line) => (line.id === id ? { ...line, text } : line));
  const stored: StoredCv = {
    ...current,
    doc: { ...current.doc, lines },
    updated_at: new Date().toISOString(),
  };
  await store.saveCv(stored);
  cv.value = stored;
}

export async function removeCv(): Promise<void> {
  await store.deleteCv();
  cv.value = null;
  cvPhase.value = "idle";
}

// ─── Posting URL ──────────────────────────────────────────────────────

/**
 * Fetch a posting through the host.
 *
 * `web.*` is gated by a per-app grant that is off by default, so the first
 * call commonly fails. That is not an error state worth dwelling on — the
 * paste box is right there, and the copy says so.
 */
export async function fetchPosting(url: string): Promise<void> {
  urlPhase.value = "running";
  error.value = null;
  try {
    const { runtime, unwrap } = await import("./lib/anna");
    const response = unwrap<{ pages?: { ok: boolean; content?: string }[] }>(
      await runtime().web.fetch({ urls: [url], format: "text", max_chars: 20000 }),
    );
    const page = response.pages?.[0];
    if (!page?.ok || !page.content) {
      throw new EngineFailure({
        code: "url_fetch_failed",
        message: "the page could not be read",
        retriable: false,
      });
    }
    postingText.value = page.content;
    postingUrl.value = url;
    urlPhase.value = "done";
  } catch (failure) {
    urlPhase.value = "error";
    error.value =
      failure instanceof EngineFailure && failure.code !== "internal_error"
        ? failure.detail
        : { code: "url_fetch_failed", message: "the page could not be read", retriable: false };
  }
}

// ─── Match ────────────────────────────────────────────────────────────

export async function startMatch(): Promise<void> {
  const current = cv.value;
  if (!current || !postingText.value.trim()) return;

  matchController?.abort();
  matchController = new AbortController();

  matchPhase.value = "running";
  showingExample.value = false;
  error.value = null;
  progress.value = null;
  arrivedEvidence.value = new Set();
  currentMatch.value = null;
  tailorResult.value = null;
  letterResult.value = null;
  acceptedBullets.value = {};
  navigate("/progress");

  try {
    const result = await engine.runMatch({
      cv: current.doc,
      postingText: postingText.value,
      ...(postingUrl.value ? { postingUrl: postingUrl.value } : {}),
      locale: currentLocale(),
      onProgress: applyProgress,
      signal: matchController.signal,
    });
    await finishMatch(result);
  } catch (failure) {
    if (failure instanceof EngineFailure && failure.code === "cancelled") {
      matchPhase.value = "idle";
      navigate("/new");
      return;
    }
    matchPhase.value = "error";
    report(failure);
  }
}

function applyProgress(event: ProgressEvent): void {
  progress.value = event;
  const matched = event.partial?.matched;
  if (!matched) return;
  // Only requirements that actually found evidence get the sweep — the
  // animation has to mean "we found this", or it means nothing.
  const next = new Set(arrivedEvidence.value);
  for (const item of matched) {
    if (item.status !== "missing") next.add(item.id);
  }
  arrivedEvidence.value = next;
}

async function finishMatch(result: MatchResult): Promise<void> {
  currentMatch.value = result;
  matchPhase.value = "done";
  tracker.value = await store.saveMatch(result);
  navigate(`/match/${result.id}`);
}

export function cancelMatch(): void {
  matchController?.abort();
  matchController = null;
}

export async function openMatch(id: string): Promise<void> {
  if (id === "example") {
    showExample();
    return;
  }
  const record = await store.loadMatch(id);
  if (!record) {
    navigate("/matches");
    return;
  }
  showingExample.value = false;
  currentMatch.value = record.match;
  tailorResult.value = record.tailor ?? null;
  letterResult.value = record.letter ?? null;
  acceptedBullets.value = {};
  matchPhase.value = "done";
  tailorPhase.value = record.tailor ? "done" : "idle";
  letterPhase.value = record.letter ? "done" : "idle";
  navigate(`/match/${id}`);
}

export async function removeMatch(id: string): Promise<void> {
  tracker.value = await store.deleteMatch(id);
  if (currentMatch.value?.id === id) currentMatch.value = null;
}

export async function updateMatchStatus(id: string, status: ApplicationStatus): Promise<void> {
  tracker.value = await store.setMatchStatus(id, status);
}

/** The recorded example: no model call, and never a qualified run. */
export function showExample(): void {
  showingExample.value = true;
  currentMatch.value = EXAMPLE_MATCH;
  tailorResult.value = EXAMPLE_TAILOR;
  letterResult.value = EXAMPLE_LETTER;
  matchPhase.value = "done";
  tailorPhase.value = "done";
  letterPhase.value = "done";
  arrivedEvidence.value = new Set(
    EXAMPLE_MATCH.evidence.filter((item) => item.status !== "missing").map((item) => item.requirement_id),
  );
  navigate("/match/example");
}

export function exampleCv(): CVDoc {
  return EXAMPLE_CV;
}

/** The CV the current screen should display — the example has its own. */
export function activeCv(): CVDoc | null {
  if (showingExample.value) return EXAMPLE_CV;
  return cv.value?.doc ?? null;
}

// ─── Tailor ───────────────────────────────────────────────────────────

export async function runTailor(): Promise<void> {
  const match = currentMatch.value;
  const doc = cv.value?.doc;
  if (!match || !doc || showingExample.value) return;

  tailorPhase.value = "running";
  error.value = null;
  try {
    const result = await engine.tailor(doc, match, currentLocale());
    tailorResult.value = result;
    tailorPhase.value = "done";
    await store.attachTailor(match.id, result);
  } catch (failure) {
    tailorPhase.value = "error";
    report(failure);
  }
}

export function acceptBullet(lineId: string, text: string): void {
  acceptedBullets.value = { ...acceptedBullets.value, [lineId]: text };
}

export function skipBullet(lineId: string): void {
  const next = { ...acceptedBullets.value };
  delete next[lineId];
  acceptedBullets.value = next;
}

// ─── Letter ───────────────────────────────────────────────────────────

export async function runLetter(): Promise<void> {
  const match = currentMatch.value;
  const doc = cv.value?.doc;
  if (!match || !doc || showingExample.value) return;

  letterPhase.value = "running";
  error.value = null;
  try {
    const result = await engine.letter(doc, match, {
      tone: letterTone.value,
      length: letterLength.value,
      locale: currentLocale(),
    });
    letterResult.value = result;
    letterPhase.value = "done";
    await store.attachLetter(match.id, result);
  } catch (failure) {
    letterPhase.value = "error";
    report(failure);
  }
}

// ─── Export ───────────────────────────────────────────────────────────

/**
 * Build the DOCX in the engine, put it in the app's own APS storage, then ask
 * the host to save it. The host page clicks the anchor, so the download works
 * regardless of the iframe's sandbox tokens (docs/api-notes.md §6).
 */
export async function exportDocument(): Promise<void> {
  const match = currentMatch.value;
  if (!match) return;
  const accepted = acceptedTailor();
  if (!accepted && !letterResult.value) return;

  exportPhase.value = "running";
  error.value = null;
  try {
    const file = await engine.exportDocx({
      ...(accepted ? { tailor: accepted } : {}),
      ...(letterResult.value ? { letter: letterResult.value } : {}),
      company: match.posting.company,
      role: match.posting.title,
      locale: currentLocale(),
    });
    await saveFile(file.filename, file.content_b64, file.mime);
    exportPhase.value = "done";
  } catch (failure) {
    exportPhase.value = "error";
    report(failure);
  }
}

async function saveFile(filename: string, contentB64: string, mime: string): Promise<void> {
  const { runtime } = await import("./lib/anna");
  const anna = runtime();
  const bytes = base64Length(contentB64);
  const path = `exports/${filename}`;

  interface UploadInit {
    put_url?: string;
    headers?: Record<string, string>;
  }
  const { unwrap } = await import("./lib/anna");
  const put = unwrap<UploadInit>(
    await anna.files.upload_init({
      path,
      content_type: mime,
      size: bytes,
      ttl_seconds: 900,
    }),
  );
  if (!put.put_url) throw new Error("upload_init returned no URL");

  // R2 rejects the presigned PUT unless Content-Type matches the signed value
  // exactly, so the returned headers go on verbatim.
  await fetch(put.put_url, {
    method: "PUT",
    headers: { "Content-Type": mime, ...(put.headers ?? {}) },
    body: new Blob([decodeBase64(contentB64).buffer as ArrayBuffer], { type: mime }),
  });
  await anna.files.upload_finalize({ path, size: bytes });
  await anna.files.download({ path, filename });
}

function base64Length(value: string): number {
  const padding = value.endsWith("==") ? 2 : value.endsWith("=") ? 1 : 0;
  return Math.max(0, (value.length * 3) / 4 - padding);
}

function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

/** Only the bullets the user actually accepted reach the document. */
export function acceptedTailor(): TailorResult | null {
  const result = tailorResult.value;
  if (!result) return null;
  const accepted = acceptedBullets.value;
  const bullets = result.bullets
    .filter((bullet) => bullet.source_line_ids[0] && accepted[bullet.source_line_ids[0]])
    .map((bullet) => ({ ...bullet, suggestion: accepted[bullet.source_line_ids[0]!]! }));
  return bullets.length > 0 ? { ...result, bullets } : null;
}

// ─── Settings ─────────────────────────────────────────────────────────

export async function changeLocale(next: Locale): Promise<void> {
  setLocale(next);
  const profile = await store.loadProfile();
  await store.saveProfile({
    locale: next,
    onboarding_done: profile?.onboarding_done ?? false,
    created_at: profile?.created_at ?? new Date().toISOString(),
  });
}

export function changeTheme(next: Theme): void {
  theme.value = next;
  if (typeof document === "undefined") return;
  if (next === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", next);
  }
}

export async function deleteEverything(): Promise<void> {
  await store.deleteEverything();
  cv.value = null;
  tracker.value = [];
  currentMatch.value = null;
  tailorResult.value = null;
  letterResult.value = null;
  acceptedBullets.value = {};
  matchPhase.value = "idle";
  postingText.value = "";
  postingUrl.value = "";
  navigate("/");
}

// ─── Shared helpers ───────────────────────────────────────────────────

export function dismissError(): void {
  error.value = null;
}

export function currentLocale(): Locale {
  return (document?.documentElement.lang as Locale) === "tr" ? "tr" : "en";
}

export function stageOf(event: ProgressEvent | null): Stage {
  return event?.stage ?? "normalize";
}

function report(failure: unknown): void {
  if (failure instanceof EngineFailure) {
    if (failure.code === "cancelled") return;
    error.value = failure.detail;
    return;
  }
  const code: ErrorCode = "internal_error";
  error.value = {
    code,
    message: failure instanceof Error ? failure.message : String(failure),
    retriable: true,
  };
}
