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

import { connect, isPreview, runtime, unwrap } from "./lib/anna";
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
  Profile,
  ProgressEvent,
  StoredCv,
  TailorResult,
  Theme,
  Tone,
  TrackerEntry,
} from "./lib/types";
import { detectLocale, setLocale } from "./i18n";
import { navigate } from "./router";

export type Phase = "idle" | "running" | "done" | "error";
export type { Theme };

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
/** Lines in the exported document the CV could not vouch for after an edit. */
export const exportUnverified = signal(0);

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
  changeTheme(profile?.theme ?? "system");
  if (!profile) {
    // A profile that cannot be written is a preference lost, not a reason to
    // refuse to start: everything below works from the defaults just chosen.
    try {
      await store.saveProfile({
        locale: chosen,
        onboarding_done: false,
        created_at: new Date().toISOString(),
        theme: "system",
      });
    } catch {
      // Falls back to the detected locale on every open until storage works.
    }
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

/**
 * Fix a misread line in place.
 *
 * The hash moves with the edit. It is the only thing tying a saved match to
 * the CV it was made against, so leaving it alone would let a match cite a
 * line whose text has since changed — evidence that no longer says what the
 * match claims it says.
 */
export async function editCvLine(id: LineId, text: string): Promise<void> {
  const current = cv.value;
  if (!current) return;
  const lines = current.doc.lines.map((line) => (line.id === id ? { ...line, text } : line));
  const stored: StoredCv = {
    ...current,
    doc: { ...current.doc, lines, hash: editedHash(current.doc.hash) },
    updated_at: new Date().toISOString(),
  };
  await store.saveCv(stored);
  cv.value = stored;
}

/**
 * Mark a hash as edited.
 *
 * The engine's hash covers the parsed text and cannot be recomputed here
 * without re-parsing (which would renumber the lines every citation points
 * at). A counted suffix keeps the one property that matters: two different CV
 * contents never share a hash.
 */
function editedHash(hash: string): string {
  const match = /^(.*)~e(\d+)$/.exec(hash);
  if (!match?.[1]) return `${hash}~e1`;
  return `${match[1]}~e${Number(match[2]) + 1}`;
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
    if (!isFetchableUrl(url)) {
      throw new EngineFailure({
        code: "url_fetch_failed",
        message: "only http and https links can be fetched",
        retriable: false,
      });
    }
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

/**
 * Whether a link is worth handing to the host.
 *
 * `web.fetch` only speaks http(s); anything else — a `javascript:` paste, a
 * `file:` path, a typo with no scheme — comes back as an opaque host error
 * after a round trip, when the honest answer was available here.
 */
function isFetchableUrl(value: string): boolean {
  try {
    return ["http:", "https:"].includes(new URL(value).protocol);
  } catch {
    return false;
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

/**
 * Show the finished match, then persist it.
 *
 * The run is the expensive part and it already succeeded: a storage failure
 * must not throw the result away and report the whole run as failed. The map
 * goes on screen either way, with a notice that this one was not saved.
 */
async function finishMatch(result: MatchResult): Promise<void> {
  currentMatch.value = result;
  matchPhase.value = "done";
  navigate(`/match/${result.id}`);
  try {
    tracker.value = await store.saveMatch(result);
  } catch {
    error.value = {
      code: "save_failed",
      message: "the match could not be saved",
      retriable: false,
    };
  }
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
    // The index says the match exists and storage says it does not. Leaving
    // the row there means the next tap does the same nothing, so drop it.
    tracker.value = await store.deleteMatch(id).catch(() => tracker.value);
    navigate("/matches");
    return;
  }
  showingExample.value = false;
  currentMatch.value = record.match;
  tailorResult.value = record.tailor ?? null;
  letterResult.value = record.letter ?? null;
  acceptedBullets.value = record.accepted ?? {};
  matchPhase.value = "done";
  tailorPhase.value = record.tailor ? "done" : "idle";
  letterPhase.value = record.letter ? "done" : "idle";
  navigate(`/match/${id}`);
}

export async function removeMatch(id: string): Promise<void> {
  tracker.value = await store.deleteMatch(id);
  forgetLetters(id);
  if (currentMatch.value?.id === id) currentMatch.value = null;
}

function forgetLetters(matchId: string): void {
  for (const key of [...letterCache.keys()]) {
    if (key.startsWith(`${matchId}:`)) letterCache.delete(key);
  }
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
  if (reportCvDrift(match.cv_hash, doc.hash)) return;

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

/**
 * Refuse to build on a match made against a different CV.
 *
 * The engine refuses this too (`_assert_same_cv`), but it refuses after the
 * user has waited for an invoke. Saying it here costs nothing and names the
 * actual cause: the CV changed, so the citations may no longer hold.
 */
function reportCvDrift(matchHash: string, cvHash: string): boolean {
  if (matchHash === cvHash) return false;
  error.value = {
    code: "cv_changed",
    message: "this match was made against an earlier version of the CV",
    retriable: false,
  };
  return true;
}

export function acceptBullet(lineId: string, text: string): void {
  acceptedBullets.value = { ...acceptedBullets.value, [lineId]: text };
  void persistAccepted();
}

export function skipBullet(lineId: string): void {
  const next = { ...acceptedBullets.value };
  delete next[lineId];
  acceptedBullets.value = next;
  void persistAccepted();
}

/**
 * Acceptance is part of the record, not of this window's session.
 *
 * Writes are chained rather than fired in parallel: each one reads the stored
 * record before rewriting it, so two clicks in flight at once could save the
 * older of the two states.
 */
let acceptedWrite: Promise<void> = Promise.resolve();

function persistAccepted(): Promise<void> {
  const match = currentMatch.value;
  if (!match || showingExample.value) return Promise.resolve();
  const snapshot = acceptedBullets.value;
  acceptedWrite = acceptedWrite
    .catch(() => undefined)
    .then(() => store.attachAccepted(match.id, snapshot))
    .catch(() => {
      // The choice stays on screen; only the memory of it is lost.
    });
  return acceptedWrite;
}

// ─── Letter ───────────────────────────────────────────────────────────

/**
 * Letters already written in this session, by tone and length.
 *
 * Comparing two tones is the point of the switch, and going back to the first
 * one should not cost a second analysis — or produce a different letter than
 * the one the user just decided they preferred.
 */
const letterCache = new Map<string, LetterResult>();

function letterKey(matchId: string, tone: Tone, length: Length): string {
  return `${matchId}:${tone}:${length}:${currentLocale()}`;
}

export async function runLetter(): Promise<void> {
  const match = currentMatch.value;
  const doc = cv.value?.doc;
  if (!match || !doc || showingExample.value) return;
  if (reportCvDrift(match.cv_hash, doc.hash)) return;

  const key = letterKey(match.id, letterTone.value, letterLength.value);
  const cached = letterCache.get(key);
  if (cached) {
    letterResult.value = cached;
    letterPhase.value = "done";
    error.value = null;
    void store.attachLetter(match.id, cached).catch(() => undefined);
    return;
  }

  letterPhase.value = "running";
  error.value = null;
  try {
    const result = await engine.letter(doc, match, {
      tone: letterTone.value,
      length: letterLength.value,
      locale: currentLocale(),
    });
    letterCache.set(key, result);
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
 * regardless of the iframe's sandbox tokens.
 */
export async function exportDocument(): Promise<void> {
  const match = currentMatch.value;
  if (!match) return;
  const accepted = acceptedTailor();
  if (!accepted && !letterResult.value) {
    // The button was enabled and pressing it did nothing, which reads as a
    // broken app rather than as "there is nothing in the document yet".
    error.value = {
      code: "export_empty",
      message: "nothing has been accepted to export",
      retriable: false,
    };
    return;
  }

  exportPhase.value = "running";
  error.value = null;
  exportUnverified.value = 0;
  try {
    const file = await engine.exportDocx({
      ...(accepted ? { tailor: accepted } : {}),
      ...(letterResult.value ? { letter: letterResult.value } : {}),
      ...(cv.value ? { cv: cv.value.doc } : {}),
      company: match.posting.company,
      role: match.posting.title,
      locale: currentLocale(),
    });
    await saveFile(file.filename, file.content_b64, file.mime);
    exportUnverified.value = file.unverified ?? 0;
    exportPhase.value = "done";
  } catch (failure) {
    exportPhase.value = "error";
    report(failure);
  }
}

async function saveFile(filename: string, contentB64: string, mime: string): Promise<void> {
  const anna = runtime();
  const bytes = base64Length(contentB64);
  const path = `exports/${filename}`;

  interface UploadInit {
    put_url?: string;
    headers?: Record<string, string>;
  }
  const put = unwrap<UploadInit>(
    await anna.files.upload_init({
      path,
      content_type: mime,
      size: bytes,
      ttl_seconds: 900,
    }),
  );
  if (!put.put_url) {
    throw new EngineFailure({
      code: "export_failed",
      message: "upload_init returned no URL",
      retriable: true,
    });
  }

  // R2 rejects the presigned PUT unless Content-Type matches the signed value
  // exactly, so the returned headers go on verbatim.
  const upload = await fetch(put.put_url, {
    method: "PUT",
    headers: { "Content-Type": mime, ...(put.headers ?? {}) },
    body: new Blob([decodeBase64(contentB64).buffer as ArrayBuffer], { type: mime }),
  });
  // `fetch` only rejects on a network failure: a refused PUT resolves with a
  // 4xx, and finalising it would hand the user a download that is not there.
  if (!upload.ok) {
    throw new EngineFailure({
      code: "export_failed",
      message: `the upload was refused with ${upload.status}`,
      retriable: true,
    });
  }
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
  await saveProfileWith({ locale: next });
}

/** Apply a theme now; persisting it is what makes the choice survive a reload. */
export function changeTheme(next: Theme): void {
  theme.value = next;
  if (typeof document !== "undefined") {
    if (next === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", next);
    }
  }
}

export async function chooseTheme(next: Theme): Promise<void> {
  changeTheme(next);
  await saveProfileWith({ theme: next });
}

/**
 * Rewrite the profile, keeping the fields this call did not set.
 *
 * A preference that cannot be stored is worth a lost setting, never a crash:
 * the change is already applied on screen by the time this runs.
 */
async function saveProfileWith(changes: Partial<Profile>): Promise<void> {
  try {
    const profile = await store.loadProfile();
    await store.saveProfile({
      locale: profile?.locale ?? currentLocale(),
      onboarding_done: profile?.onboarding_done ?? false,
      created_at: profile?.created_at ?? new Date().toISOString(),
      theme: profile?.theme ?? theme.value,
      ...changes,
    });
  } catch {
    // Reverts to the detected locale and the system theme on the next open.
  }
}

export async function deleteEverything(): Promise<void> {
  letterCache.clear();
  try {
    await store.deleteEverything();
    // Storage is the record, but the engine may still hold an abandoned
    // upload; "deleted" should not mean "deleted in ten minutes".
    await engine.forget().catch(() => undefined);
  } catch (failure) {
    // Leave the screen showing what is still there. Reporting "deleted" over a
    // failed delete is the one lie this screen must never tell.
    report(failure);
    return;
  }
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
  // `document?.` does not guard an undeclared global — only `typeof` does, and
  // this module is imported by tests that run without a DOM.
  if (typeof document === "undefined") return "en";
  return (document.documentElement.lang as Locale) === "tr" ? "tr" : "en";
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
