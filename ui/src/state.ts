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
import { appendLine, editLine, sectionForCategory } from "./lib/cv";
import {
  DEFAULT_POSTINGS,
  MIN_POSTINGS,
  renderableColumns,
  toggleSelection,
} from "./lib/compare";
import {
  DEFAULT_CV_ID,
  MAX_CV_PROFILES,
  cleanName,
  forProfile,
  mintCvId,
  nameFromFilename,
  normalize as normalizeProfiles,
} from "./lib/profiles";
import { renderableResult } from "./lib/ledger";
import { previousRun, renderableDiff } from "./lib/rerun";
import { splitQuestions } from "./lib/questions";
import { RECENT_MATCHES, renderable, replayItems } from "./lib/recurring";
import * as engine from "./lib/engine";
import { EngineFailure } from "./lib/engine";
import {
  EXAMPLE_BRIEF,
  EXAMPLE_CV,
  EXAMPLE_GAPS,
  EXAMPLE_LETTER,
  EXAMPLE_MATCH,
  EXAMPLE_TAILOR,
} from "./lib/example";
import * as store from "./lib/store";
import type {
  AnswerResult,
  ApplicationStatus,
  Assertion,
  CVDoc,
  Category,
  CheckedLine,
  CompareResult,
  CvAudit,
  CvExportMode,
  CvFinding,
  CvProfile,
  DocumentCheck,
  QuestionAnswer,
  EngineError,
  ErrorCode,
  GapResult,
  InterviewBrief,
  LedgerResult,
  LetterResult,
  Length,
  LineId,
  Locale,
  MatchResult,
  Profile,
  ProgressEvent,
  RecurringResult,
  RunDiff,
  FollowupResult,
  ProfileResult,
  SinceResult,
  WorthResult,
  Section,
  StoredCv,
  StoredMatch,
  TailoredBullet,
  TailorResult,
  Theme,
  Tone,
  TrackerEntry,
} from "./lib/types";
import { detectLocale, setLocale, t } from "./i18n";
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

/**
 * The CVs this account keeps, and which one is in use.
 *
 * One entry for an account that never asked for a second, and that entry is
 * the document `cv:v1` has always held (`lib/profiles`). The active CV is a
 * workspace: it decides which document gets tailored and which applications
 * the tracker, the recurring report and the comparison are drawn from.
 */
export const cvProfiles = signal<CvProfile[]>([]);
export const activeCvId = signal<string>(DEFAULT_CV_ID);
/** True while the next parsed CV should become a new one rather than replace one. */
export const addingCv = signal(false);
export const cvUpload = signal<{ sent: number; total: number } | null>(null);

// ─── Match ────────────────────────────────────────────────────────────

export const postingText = signal("");
export const postingUrl = signal("");
export const urlPhase = signal<Phase>("idle");

export const matchPhase = signal<Phase>("idle");
export const currentMatch = signal<MatchResult | null>(null);
export const progress = signal<ProgressEvent | null>(null);
export const arrivedEvidence = signal<Set<string>>(new Set());

/**
 * Where the user said the match got it wrong, for the open application.
 *
 * Separate from `currentMatch` on purpose: the engine's verdict is never
 * edited, so these two signals answer two different questions — what the app
 * found, and what the person said — and every screen that shows one has to
 * decide, visibly, what it does with the other.
 */
export const assertions = signal<Record<string, Assertion>>({});
/** The requirement the user is currently picking CV lines for, if any. */
export const asserting = signal<string | null>(null);

export const tailorPhase = signal<Phase>("idle");
export const tailorResult = signal<TailorResult | null>(null);
export const acceptedBullets = signal<Record<string, string>>({});

export const auditPhase = signal<Phase>("idle");
export const auditResult = signal<CvAudit | null>(null);
/** Findings answered this session, keyed by `findingKey`. */
export const answeredFindings = signal<Set<string>>(new Set());

/**
 * The shareable card.
 *
 * `shareWithRole` is the whole consent model and it deliberately does not
 * persist: every card starts with the role title off, so revealing which job
 * someone is applying for is a decision they make each time rather than a
 * setting they forgot they changed.
 */
export const sharePhase = signal<Phase>("idle");
export const shareWithRole = signal(false);

/**
 * Answering the free-text questions on an application form.
 *
 * `questionDraft` is what the user pasted and `skippedQuestions` is what they
 * struck off the reading of it, so the split the screen shows and the list the
 * engine answers are the same list — including on the re-run after an answer
 * goes into the CV.
 */
export const answersPhase = signal<Phase>("idle");
export const questionDraft = signal("");
export const skippedQuestions = signal<Set<string>>(new Set());
export const answersResult = signal<AnswerResult | null>(null);
/** Questions answered into the CV this session, by their text. */
export const answeredQuestions = signal<Set<string>>(new Set());

/** The pasted block, read as questions, minus the ones the user struck off. */
export const detectedQuestions = computed(() =>
  splitQuestions(questionDraft.value).filter((question) => !skippedQuestions.value.has(question)),
);

/**
 * Checking a document the app did not write.
 *
 * `checkDraft` is the pasted text and it lives here rather than in the screen
 * so a stray navigation does not throw away a CV someone just pasted. It is
 * never written to storage: the document arrives, is read, and is gone.
 */
export const checkPhase = signal<Phase>("idle");
export const checkDraft = signal("");
export const checkResult = signal<DocumentCheck | null>(null);
/** Match the check ran against, so the screen can name what it disregarded. */
export const checkAgainst = signal<string | null>(null);
/** Sentences answered this session, keyed by `checkedKey`. */
export const answeredChecks = signal<Set<string>>(new Set());

export const comparePhase = signal<Phase>("idle");
export const compareResult = signal<CompareResult | null>(null);
/** Match ids being compared, in the order they were picked. */
export const compareSelection = signal<string[]>([]);

export const recurringPhase = signal<Phase>("idle");
export const recurringResult = signal<RecurringResult | null>(null);
/** Recurring gaps answered this session, by group key. */
export const answeredRecurring = signal<Set<string>>(new Set());

/**
 * What every CV line has proved across the applications it was sent with.
 *
 * Not cached anywhere: it is free to compute and it stops being true the
 * moment a line is added or a match is saved, and a stale ledger is advice
 * about a document that no longer exists.
 */
export const ledgerPhase = signal<Phase>("idle");
export const ledgerResult = signal<LedgerResult | null>(null);

/**
 * What one application has missed since it went out.
 *
 * About a single application, unlike the ledger, but read from the same two
 * records: the verdicts that application recorded, and the dates on the lines
 * the user has written into the CV since.
 */
export const sincePhase = signal<Phase>("idle");
export const sinceResult = signal<SinceResult | null>(null);

/**
 * The note after the silence.
 *
 * The only model call in the app that often does not happen: the engine
 * decides from stored records whether there is anything worth sending, and
 * declining costs nothing.
 */
export const followupPhase = signal<Phase>("idle");
export const followupResult = signal<FollowupResult | null>(null);

/**
 * The profile — the one thing this app writes that no posting asked for.
 *
 * Kept per CV rather than per match: it is about the document, so switching
 * CVs or adding a line to one makes it stale in the way a match never does.
 */
export const profilePhase = signal<Phase>("idle");
export const profileResult = signal<ProfileResult | null>(null);

/**
 * What the second run of a posting changed.
 *
 * The one screen in the app that reports back on whether answering a gap
 * question was worth it. Rebuilt on open like the rest of the reading
 * screens, because both runs are stored and the comparison is free.
 */
export const rerunPhase = signal<Phase>("idle");
export const rerunResult = signal<RunDiff | null>(null);

/**
 * Which saved applications the CV has since gained an answer for.
 *
 * The shelf-wide version of "since you applied": nobody with thirty
 * applications opens thirty of them to find out which one last Tuesday's
 * sentence changed.
 */
export const worthPhase = signal<Phase>("idle");
export const worthResult = signal<WorthResult | null>(null);

/**
 * The earlier run of the posting on screen, when there is one.
 *
 * `null` for almost every match — most are run once — and that is what keeps
 * the banner off every other match map in the app.
 */
export const earlierRun = computed(() => {
  const match = currentMatch.value;
  if (!match || showingExample.value) return null;
  return previousRun(tracker.value, match);
});

export const gapsPhase = signal<Phase>("idle");
export const gapsResult = signal<GapResult | null>(null);
/** Requirement ids whose answer is already a line in the CV, this session. */
export const answeredGaps = signal<Set<string>>(new Set());

export const briefPhase = signal<Phase>("idle");
export const briefResult = signal<InterviewBrief | null>(null);

export const letterPhase = signal<Phase>("idle");
export const letterResult = signal<LetterResult | null>(null);
export const letterTone = signal<Tone>("plain");
export const letterLength = signal<Length>("standard");

/** Downloading the CV itself — a different document, and a different state. */
export const cvExportPhase = signal<Phase>("idle");
export const cvExportMode = signal<CvExportMode>("full");
/** Lines the last CV export wrote. */
export const cvExportLines = signal(0);

export const exportPhase = signal<Phase>("idle");
/** Lines in the exported document the CV could not vouch for after an edit. */
export const exportUnverified = signal(0);

// ─── Tracker ──────────────────────────────────────────────────────────

/**
 * The active CV's applications. Every screen reads this one.
 *
 * The stored index holds all of them across every CV; keeping the visible list
 * here rather than filtering in each screen is what makes switching CVs one
 * total change of workspace instead of a rule every screen has to remember.
 */
export const tracker = signal<TrackerEntry[]>([]);

/** The whole index, including the CVs that are not on screen. */
let everyEntry: TrackerEntry[] = [];

function setIndex(entries: TrackerEntry[]): void {
  everyEntry = entries;
  tracker.value = forProfile(entries, activeCvId.value);
}

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

  await loadCvProfiles();
  setIndex(await store.loadIndex());
  ready.value = true;

  applyEntryPayload(connection.entryPayload);
  void adoptRunningMatch();
}

/**
 * A posting handed over by the assistant (`#vouch` + text) should land the
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

// ─── The CVs ──────────────────────────────────────────────────────────

/**
 * Read the CV set, and the active CV's document.
 *
 * An account that never asked for a second CV has no `cvs:v1` key at all, and
 * `normalize` turns that into the one entry it always had — so nothing about
 * an existing user's storage changes until they add a CV themselves.
 */
async function loadCvProfiles(): Promise<void> {
  const stored = await store.loadCvProfiles();
  const { active, list } = normalizeProfiles(stored, untitledCv(1));
  cvProfiles.value = list;
  activeCvId.value = active;
  cv.value = await store.loadCv(active);
}

/**
 * Write the set down.
 *
 * Best effort, like every other preference: the CV documents themselves are
 * already saved under their own keys, so a failure here costs the *name* and
 * which one was open, never a document.
 */
async function persistCvProfiles(): Promise<void> {
  try {
    await store.saveCvProfiles({
      version: 1,
      active: activeCvId.value,
      list: cvProfiles.value,
    });
  } catch {
    // Names and the open CV revert on the next boot; the CVs themselves stay.
  }
}

/** A name for a CV the user has not named. The numeral is theirs to replace. */
function untitledCv(position: number): string {
  return t("cv.profiles.untitled", { n: position });
}

/** Whether there is room for another. */
export const canAddCv = computed(() => cvProfiles.value.length < MAX_CV_PROFILES);

export const activeCvName = computed(
  () =>
    cvProfiles.value.find((profile) => profile.id === activeCvId.value)?.name ??
    untitledCv(1),
);

/**
 * Send the user to add a CV that sits beside the one they have.
 *
 * The flag is what separates this from "Replace my CV": the same screen and
 * the same parse, and then the document is saved under a new id instead of
 * over the old one.
 */
export function startAnotherCv(): void {
  if (!canAddCv.value) return;
  addingCv.value = true;
  navigate("/cv/add");
}

/**
 * Open one of the CVs.
 *
 * A total switch: the document, the applications on screen, and everything
 * read across them. Anything still open that was about the other CV is
 * dropped rather than left to be read against a document it was never made
 * from — the citations would point at lines that do not exist there.
 */
export async function useCv(id: string): Promise<void> {
  if (id === activeCvId.value) return;
  if (!cvProfiles.value.some((profile) => profile.id === id)) return;

  activeCvId.value = id;
  cv.value = await store.loadCv(id);
  setIndex(everyEntry);
  clearMatchWork();
  await persistCvProfiles();
  navigate(cv.value ? "/cv/preview" : "/cv/add");
}

/** Rename one. The name is the user's own word for it and is never generated. */
export async function renameCv(id: string, name: string): Promise<void> {
  const clean = cleanName(name);
  if (!clean) return;
  cvProfiles.value = cvProfiles.value.map((profile) =>
    profile.id === id ? { ...profile, name: clean } : profile,
  );
  await persistCvProfiles();
}

/**
 * Delete one CV and the applications made against it.
 *
 * The matches go with it, and the confirmation says so. A match whose CV is
 * gone would render its citations against whichever document was loaded
 * instead — the quiet wrongness this product exists to prevent — and the last
 * CV cannot be deleted here, because "delete everything" is its own button
 * with its own confirmation.
 */
export async function removeCvProfile(id: string): Promise<void> {
  if (cvProfiles.value.length < 2) return;
  try {
    setIndex(await store.deleteCvProfile(id));
  } catch (failure) {
    report(failure);
    return;
  }
  const kept = cvProfiles.value.filter((profile) => profile.id !== id);
  cvProfiles.value = kept;
  if (activeCvId.value === id) {
    const next = kept[0]?.id ?? DEFAULT_CV_ID;
    activeCvId.value = next;
    cv.value = await store.loadCv(next);
    setIndex(everyEntry);
    clearMatchWork();
  }
  await persistCvProfiles();
}

/** How many applications a CV would take with it. */
export function matchesForCv(id: string): number {
  return forProfile(everyEntry, id).length;
}

/**
 * Drop everything on screen that was about one application.
 *
 * Switching CVs and deleting one both land here: a match map, a tailor sheet
 * or a brief left over from the other workspace is not stale, it is about a
 * different document.
 */
function clearMatchWork(): void {
  currentMatch.value = null;
  matchPhase.value = "idle";
  tailorResult.value = null;
  tailorPhase.value = "idle";
  letterResult.value = null;
  letterPhase.value = "idle";
  gapsResult.value = null;
  gapsPhase.value = "idle";
  answeredGaps.value = new Set();
  briefResult.value = null;
  briefPhase.value = "idle";
  acceptedBullets.value = {};
  assertions.value = {};
  asserting.value = null;
  sharePhase.value = "idle";
  shareWithRole.value = false;
  auditResult.value = null;
  auditPhase.value = "idle";
  answeredFindings.value = new Set();
  clearCheck();
  clearAnswers();
  recurringResult.value = null;
  recurringPhase.value = "idle";
  answeredRecurring.value = new Set();
  ledgerResult.value = null;
  ledgerPhase.value = "idle";
  sinceResult.value = null;
  sincePhase.value = "idle";
  followupResult.value = null;
  followupPhase.value = "idle";
  profileResult.value = null;
  profilePhase.value = "idle";
  rerunResult.value = null;
  rerunPhase.value = "idle";
  worthResult.value = null;
  worthPhase.value = "idle";
  compareResult.value = null;
  comparePhase.value = "idle";
  compareSelection.value = [];
  letterCache.clear();
  showingExample.value = false;
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

/**
 * Parse a CV and save it — over the open one, or as a new one beside it.
 *
 * Which of the two is decided before the parse (`addingCv`), because the
 * difference is not a detail of storage: replacing a CV keeps the
 * applications that were checked against it, and adding one starts an empty
 * workspace.
 */
async function withCv(run: () => Promise<CVDoc>, filename: string | null): Promise<void> {
  cvPhase.value = "running";
  error.value = null;
  const adding = addingCv.value && canAddCv.value;
  try {
    const doc = await run();
    const stored: StoredCv = { doc, filename, updated_at: new Date().toISOString() };
    const id = adding ? mintCvId(cvProfiles.value) : activeCvId.value;
    await store.saveCv(stored, id);
    if (adding) {
      // Named from the file where there is one: "dilek-backend.pdf" is
      // already the user's own word for this CV, and telling two documents
      // apart in a tab is the whole point of naming them.
      const name = nameFromFilename(filename) ?? untitledCv(cvProfiles.value.length + 1);
      cvProfiles.value = [
        ...cvProfiles.value,
        { id, name, created_at: new Date().toISOString() },
      ];
      activeCvId.value = id;
      setIndex(everyEntry);
      clearMatchWork();
      await persistCvProfiles();
    }
    cv.value = stored;
    cvPhase.value = "done";
    addingCv.value = false;
    navigate("/cv/preview");
  } catch (failure) {
    cvPhase.value = "error";
    report(failure);
  }
}

/**
 * Fix a misread line in place.
 *
 * The hash moves with the edit (`lib/cv.markEdited`). It is the only thing
 * tying a saved match to the CV it was made against, so leaving it alone would
 * let a match cite a line whose text has since changed — evidence that no
 * longer says what the match claims it says.
 */
export async function editCvLine(id: LineId, text: string): Promise<void> {
  const current = cv.value;
  if (!current) return;
  const stored: StoredCv = {
    ...current,
    doc: editLine(current.doc, id, text),
    updated_at: new Date().toISOString(),
  };
  await store.saveCv(stored, activeCvId.value);
  cv.value = stored;
}


export async function removeCv(): Promise<void> {
  await store.deleteCv(activeCvId.value);
  cv.value = null;
  cvPhase.value = "idle";
  // "Replace my CV" replaces the open one; an abandoned "add another" must not
  // turn the replacement into a third document.
  addingCv.value = false;
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
  gapsResult.value = null;
  gapsPhase.value = "idle";
  answeredGaps.value = new Set();
  briefResult.value = null;
  briefPhase.value = "idle";
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
    setIndex(await store.saveMatch(result, activeCvId.value));
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
    setIndex(await store.deleteMatch(id).catch(() => everyEntry));
    navigate("/matches");
    return;
  }
  // A match is only readable against the CV it was checked against: its
  // citations are line ids, and those point at different sentences in another
  // document. Opening one from another workspace switches to it rather than
  // rendering the map over the wrong CV.
  const belongsTo = record.cv ?? DEFAULT_CV_ID;
  if (belongsTo !== activeCvId.value && cvProfiles.value.some((p) => p.id === belongsTo)) {
    activeCvId.value = belongsTo;
    cv.value = await store.loadCv(belongsTo);
    setIndex(everyEntry);
    await persistCvProfiles();
  }
  showingExample.value = false;
  currentMatch.value = record.match;
  tailorResult.value = record.tailor ?? null;
  letterResult.value = record.letter ?? null;
  acceptedBullets.value = record.accepted ?? {};
  assertions.value = record.assertions ?? {};
  asserting.value = null;
  // The sheet is about the CV as it stands now, not as it stood when the match
  // was saved, so it is asked for again rather than stored.
  gapsResult.value = null;
  gapsPhase.value = "idle";
  answeredGaps.value = new Set();
  // Same reason as the gap sheet: the brief is about the CV and the accepted
  // bullets as they stand now, so it is rebuilt rather than restored. The
  // same goes for the comparison with this posting's earlier run.
  briefResult.value = null;
  briefPhase.value = "idle";
  rerunResult.value = null;
  rerunPhase.value = "idle";
  matchPhase.value = "done";
  tailorPhase.value = record.tailor ? "done" : "idle";
  letterPhase.value = record.letter ? "done" : "idle";
  navigate(`/match/${id}`);
}

export async function removeMatch(id: string): Promise<void> {
  setIndex(await store.deleteMatch(id));
  forgetLetters(id);
  if (currentMatch.value?.id === id) currentMatch.value = null;
}

function forgetLetters(matchId: string): void {
  for (const key of [...letterCache.keys()]) {
    if (key.startsWith(`${matchId}:`)) letterCache.delete(key);
  }
}

export async function updateMatchStatus(id: string, status: ApplicationStatus): Promise<void> {
  setIndex(await store.setMatchStatus(id, status));
}

/** The recorded example: no model call, and never a qualified run. */
export function showExample(): void {
  showingExample.value = true;
  currentMatch.value = EXAMPLE_MATCH;
  tailorResult.value = EXAMPLE_TAILOR;
  letterResult.value = EXAMPLE_LETTER;
  gapsResult.value = EXAMPLE_GAPS;
  briefResult.value = EXAMPLE_BRIEF;
  briefPhase.value = "done";
  matchPhase.value = "done";
  tailorPhase.value = "done";
  letterPhase.value = "done";
  gapsPhase.value = "done";
  answeredGaps.value = new Set();
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

/**
 * What identifies one suggestion.
 *
 * Not its source line: the engine can return two suggestions for the same CV
 * line and goes out of its way to keep both (`pipeline/tailor.py` groups them
 * into a list precisely because "a plain dict would drop one of them without
 * saying so"). Keying acceptance by the line id put that dict back — accepting
 * one suggestion marked both accepted, editing one rewrote both, and the
 * exported document carried the same sentence twice.
 *
 * The suggestion text is part of the identity, not the index, so the key
 * survives a reload and a re-run that returns the bullets in another order —
 * and a re-run that produces *different* wording correctly drops an acceptance
 * that was made about the old sentence.
 */
export function bulletKey(bullet: TailoredBullet): string {
  return `${bullet.source_line_ids[0] ?? ""}|${bullet.suggestion ?? ""}`;
}

export function acceptBullet(key: string, text: string): void {
  acceptedBullets.value = { ...acceptedBullets.value, [key]: text };
  void persistAccepted();
}

export function skipBullet(key: string): void {
  const next = { ...acceptedBullets.value };
  delete next[key];
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

// ─── Gaps ─────────────────────────────────────────────────────────────

/**
 * Ask about everything this match could not prove.
 *
 * Cheap to re-run and worth re-running: the sheet is about the CV as it stands,
 * and the CV changes as the user answers.
 */
export async function runGaps(): Promise<void> {
  const match = currentMatch.value;
  const doc = cv.value?.doc;
  if (!match || !doc || showingExample.value) return;
  if (reportCvDrift(match.cv_hash, doc.hash)) return;

  gapsPhase.value = "running";
  error.value = null;
  try {
    gapsResult.value = await engine.gaps(doc, match, currentLocale());
    gapsPhase.value = "done";
  } catch (failure) {
    gapsPhase.value = "error";
    report(failure);
  }
}

/**
 * Put the user's answer into their CV, verbatim.
 *
 * This is the whole feature. Every other tool closes a gap by writing the
 * experience in for the candidate; here the sentence is theirs, it is stored
 * exactly as typed, and the next match cites it like any other line — with a
 * number, in the sheet, where a recruiter's question can reach it.
 *
 * Appending moves the CV hash, so the match on screen is now stale and
 * `reportCvDrift` will refuse to tailor from it. That is correct rather than
 * unfortunate: the answer is new evidence, and evidence changes the verdict.
 * The screen sends the user back to run it again.
 */
export async function answerGap(requirementId: string, text: string): Promise<void> {
  const match = currentMatch.value;
  if (!match) return;
  const requirement = match.requirements.find((item) => item.id === requirementId);
  const section = sectionForCategory(requirement?.category ?? ("experience" as Category));
  if (!(await appendAnswer(text, section))) return;
  answeredGaps.value = new Set([...answeredGaps.value, requirementId]);
}

/**
 * The one place a user-written line enters the CV.
 *
 * Both answer paths — a gap question and an audit finding — end here, because
 * both are the same promise: the sentence is the person's, it is stored as
 * typed, and the hash moves so nothing built on the old CV keeps claiming to
 * describe the new one. Returns whether the line was actually saved.
 */
async function appendAnswer(text: string, section: Section): Promise<boolean> {
  const current = cv.value;
  const answer = text.trim();
  if (!current || !answer || showingExample.value) return false;

  const stored: StoredCv = {
    ...current,
    doc: appendLine(current.doc, answer, section),
    updated_at: new Date().toISOString(),
  };
  try {
    await store.saveCv(stored, activeCvId.value);
  } catch (failure) {
    // The answer is only worth anything once it is in the CV, so a failed
    // write must not look like a saved one.
    report(failure);
    return false;
  }
  cv.value = stored;
  // The ledger is a statement about this document: a line added to it changes
  // which lines are idle, and what the added ones have proved. That same line
  // is the entire subject of "since you applied".
  ledgerResult.value = null;
  ledgerPhase.value = "idle";
  sinceResult.value = null;
  sincePhase.value = "idle";
  followupResult.value = null;
  followupPhase.value = "idle";
  profileResult.value = null;
  profilePhase.value = "idle";
  rerunResult.value = null;
  rerunPhase.value = "idle";
  // The new line is exactly what this screen scans for, so its answer is
  // stale the moment it is written.
  worthResult.value = null;
  worthPhase.value = "idle";
  return true;
}

/** Whether answers have made the match on screen out of date. */
export const cvMovedOnFromMatch = computed(() => {
  const match = currentMatch.value;
  const doc = cv.value?.doc;
  if (!match || !doc || showingExample.value) return false;
  return match.cv_hash !== doc.hash;
});

// ─── CV audit ─────────────────────────────────────────────────────────

/**
 * What identifies one finding.
 *
 * The engine returns no id, and it does not need to: a finding is fully
 * described by what it is about. Two runs over the same CV produce the same
 * key, so an answer given before a re-audit is still recognised afterwards.
 */
export function findingKey(finding: CvFinding): string {
  return `${finding.kind}|${finding.subject}`;
}

/**
 * Read the CV against itself.
 *
 * No model and no job — a synchronous invoke that costs nothing, which is why
 * the screen can simply run it on open and re-run it after every answer
 * instead of asking the user to.
 */
export async function runAudit(): Promise<void> {
  const doc = activeCv();
  if (!doc) return;

  auditPhase.value = "running";
  error.value = null;
  try {
    auditResult.value = await engine.auditCv(doc);
    auditPhase.value = "done";
  } catch (failure) {
    auditPhase.value = "error";
    report(failure);
  }
}

/**
 * Answer a finding by adding the evidence it asked for.
 *
 * The same loop the gap questions use: the app says what it could not find,
 * the person says where it actually happened, and their sentence becomes a
 * line the verifier can cite from then on. The audit is re-run afterwards so
 * the finding disappears because it is genuinely resolved, not because the
 * screen hid it.
 */
export async function answerFinding(finding: CvFinding, text: string): Promise<void> {
  if (!(await appendAnswer(text, "experience"))) return;
  answeredFindings.value = new Set([...answeredFindings.value, findingKey(finding)]);
  await runAudit();
}

// ─── A receipt you can show ───────────────────────────────────────────

/**
 * Write the card to a file, through the same path a DOCX takes.
 *
 * The SVG string comes from the screen rather than being rebuilt here, so the
 * bytes saved are the bytes previewed. `TextEncoder` before base64 because the
 * headline can be Turkish and `btoa` only speaks Latin-1.
 */
export async function saveCard(svg: string): Promise<void> {
  const match = currentMatch.value;
  if (!match) return;

  sharePhase.value = "running";
  error.value = null;
  try {
    const bytes = new TextEncoder().encode(svg);
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    await saveFile(`receipts-${match.id.slice(0, 8)}.svg`, btoa(binary), "image/svg+xml");
    sharePhase.value = "done";
  } catch (failure) {
    sharePhase.value = "error";
    report(failure);
  }
}

// ─── When the match got it wrong ──────────────────────────────────────

/**
 * The assertions in the shape the engine takes them.
 *
 * A list rather than the record the UI keeps, because the engine validates
 * `requirement_id` and a map key cannot carry a pattern.
 */
export function assertionList(): { requirement_id: string; line_ids: string[] }[] {
  return Object.entries(assertions.value).map(([requirement_id, item]) => ({
    requirement_id,
    line_ids: item.line_ids,
  }));
}

/** Start picking the CV lines that cover a requirement, or stop. */
export function startAsserting(requirementId: string | null): void {
  asserting.value = requirementId;
}

/**
 * Record that the user says these lines cover a requirement.
 *
 * The match is not touched. What is stored is the disagreement, beside the
 * verdict, so that a month later the record still answers both questions —
 * and so that nothing generated can ever lean on it: `tailor` and `letter`
 * build from `match.evidence`, which has not changed, and the verifier still
 * checks every sentence against the CV line it cites.
 *
 * Empty `lineIds` withdraws an assertion, because changing your mind about
 * your own career is not a different operation from having it.
 */
export async function assertEvidence(requirementId: string, lineIds: string[]): Promise<void> {
  const match = currentMatch.value;
  if (!match || showingExample.value) return;

  const next = { ...assertions.value };
  if (lineIds.length === 0) {
    delete next[requirementId];
  } else {
    next[requirementId] = { line_ids: lineIds as LineId[], at: new Date().toISOString() };
  }
  assertions.value = next;
  asserting.value = null;
  // The brief reads these, so a stale one would tell the user the app agreed
  // with them — the one thing this feature must never imply.
  briefResult.value = null;
  briefPhase.value = "idle";
  try {
    await store.attachAssertions(match.id, next);
  } catch (failure) {
    report(failure);
  }
}

// ─── Answering what the form asked ────────────────────────────────────

/** Throw away a set of answers and the questions they were about. */
export function clearAnswers(): void {
  answersPhase.value = "idle";
  questionDraft.value = "";
  skippedQuestions.value = new Set();
  answersResult.value = null;
  answeredQuestions.value = new Set();
}

/** Strike one question off the reading of what was pasted. */
export function skipQuestion(question: string): void {
  skippedQuestions.value = new Set([...skippedQuestions.value, question]);
}

/**
 * Answer the form's questions from the CV.
 *
 * A model call, so it runs as a job like the letter. The open application goes
 * along when there is one, but it is context and not the subject: these
 * questions can arrive in an email months after the application, and refusing
 * to answer them because no match is open would be refusing the common case.
 * That is also why there is no `reportCvDrift` here — nothing is being built
 * on the match's verdicts.
 */
export async function runAnswers(): Promise<void> {
  const doc = activeCv();
  const questions = detectedQuestions.value;
  if (!doc || questions.length === 0) return;

  answersPhase.value = "running";
  error.value = null;
  try {
    answersResult.value = await engine.answerQuestions({
      cv: doc,
      questions,
      match: currentMatch.value,
      locale: currentLocale(),
    });
    answersPhase.value = "done";
  } catch (failure) {
    answersPhase.value = "error";
    report(failure);
  }
}

/**
 * Answer a question the CV could not, in the user's own words.
 *
 * The same loop as a gap question, an audit finding and a flagged sentence,
 * and the reason this screen can say "no evidence" without it being a dead
 * end: the sentence goes into the CV verbatim and the questions are asked
 * again, so the answer comes back written from a line that now exists.
 */
export async function answerUnanswered(item: QuestionAnswer, text: string): Promise<void> {
  if (!(await appendAnswer(text, "experience"))) return;
  answeredQuestions.value = new Set([...answeredQuestions.value, item.question]);
  await runAnswers();
}

// ─── Checking a document the app did not write ────────────────────────

/**
 * What identifies one flagged sentence.
 *
 * Its position moves the moment the user edits the document and checks again,
 * so the key is the sentence itself — an answer given about a sentence is
 * still recognised after a re-check that reordered everything above it.
 */
export function checkedKey(line: CheckedLine): string {
  return line.text.trim();
}

/** Throw away a check and the document it was about. */
export function clearCheck(): void {
  checkPhase.value = "idle";
  checkDraft.value = "";
  checkResult.value = null;
  checkAgainst.value = null;
  answeredChecks.value = new Set();
}

/**
 * Read a pasted document against the CV.
 *
 * No model and no job, like the audit: a synchronous invoke that costs
 * nothing, which is why the screen can simply run it again after every answer
 * instead of asking the user to.
 *
 * The open application, when there is one, is passed along so the employer
 * being written to is not read as a claim about the candidate. It is not what
 * is being checked — a document has no posting and needs none.
 */
export async function runCheck(): Promise<void> {
  const doc = activeCv();
  const document = checkDraft.value.trim();
  if (!doc || !document) return;

  const against = checkAgainst.value;
  const match = against && currentMatch.value?.id === against ? currentMatch.value : null;

  checkPhase.value = "running";
  error.value = null;
  try {
    checkResult.value = await engine.checkDocument({
      cv: doc,
      document,
      match,
      company: match?.posting.company ?? null,
      role: match?.posting.title ?? null,
    });
    checkPhase.value = "done";
  } catch (failure) {
    checkPhase.value = "error";
    report(failure);
  }
}

/**
 * Answer a flagged sentence by adding the evidence it needs.
 *
 * The same loop the gap questions and the audit findings use, and the only
 * repair this screen can honestly offer: the app cannot edit someone's file,
 * so either the claim is true and the CV should say so, or it is not and the
 * sentence belongs out of the document. The check is re-run afterwards, so the
 * sentence clears because it is backed now, not because the screen hid it.
 */
export async function answerCheckedLine(line: CheckedLine, text: string): Promise<void> {
  if (!(await appendAnswer(text, "experience"))) return;
  answeredChecks.value = new Set([...answeredChecks.value, checkedKey(line)]);
  await runCheck();
}

// ─── What keeps coming up ─────────────────────────────────────────────

/**
 * Read every recent application at once and ask what they have in common.
 *
 * The only view in the app that crosses applications, and the only question a
 * single match cannot answer: not "does this CV fit this job" but "what is
 * standing between me and the jobs I keep applying to". It is honest here in a
 * way it would not be elsewhere, because every number comes from a verdict the
 * verifier already made, one application at a time.
 *
 * Free to run — no model, no tokens — so it re-runs whenever the shelf changes
 * rather than caching a number that has quietly stopped being true.
 */
export async function runRecurring(): Promise<void> {
  recurringPhase.value = "running";
  error.value = null;
  try {
    const records = await store.loadRecentMatches(RECENT_MATCHES, activeCvId.value);
    const items = replayItems(records);
    if (items.length === 0) {
      // No saved requirements at all: a real answer, and asking the engine to
      // group an empty list would spend an invoke to be told so.
      recurringResult.value = { version: 1, matches: 0, groups: [], strengths: [] };
      recurringPhase.value = "done";
      return;
    }
    const report = await engine.recurringGaps(items);
    // Nothing reaches the screen whose numbers cannot be true of the sample
    // they came from, so no payload can make it say "in 3 of 1".
    recurringResult.value = {
      ...report,
      groups: renderable(report.groups, report.matches),
      strengths: renderable(report.strengths, report.matches),
    };
    recurringPhase.value = "done";
  } catch (failure) {
    recurringPhase.value = "error";
    report(failure);
  }
}

/**
 * Answer a recurring gap once, for every application it appeared in.
 *
 * The same loop as the gap questions and the audit findings — the user's own
 * sentence becomes a CV line — except that here one answer changes the verdict
 * on every future match rather than on one. That is the whole argument for
 * showing this screen at all: it tells the user which single sentence is worth
 * the most.
 */
export async function answerRecurring(key: string, text: string): Promise<void> {
  if (!(await appendAnswer(text, "experience"))) return;
  answeredRecurring.value = new Set([...answeredRecurring.value, key]);
}

// ─── Which lines do the work ──────────────────────────────────────────

/**
 * Read the CV back through the applications it has already been sent with.
 *
 * The same replay feed the recurring report uses, asked the other way round:
 * not "what did the postings keep asking for" but "which of these sentences
 * has ever answered one". Only this app can say it, because only this app
 * stored which line was accepted as evidence for which requirement — and it
 * says it without a model, so re-running costs the user nothing.
 *
 * The CV goes with the feed. Half the answer is about lines no posting has
 * ever cited, and a list of citations cannot name a line that is missing from
 * it.
 */
export async function runLedger(): Promise<void> {
  const doc = activeCv();
  if (!doc) return;

  ledgerPhase.value = "running";
  error.value = null;
  try {
    const records = await store.loadRecentMatches(RECENT_MATCHES, activeCvId.value);
    const items = replayItems(records);
    if (items.length === 0) {
      // No saved application at all: a real answer, and asking the engine to
      // count an empty feed would spend an invoke to be told so.
      ledgerResult.value = {
        version: 1,
        applications: 0,
        skipped: 0,
        eligible: doc.lines.filter((line) => line.section !== "header").length,
        cited: 0,
        working: [],
        idle: [],
        added: [],
      };
      ledgerPhase.value = "done";
      return;
    }
    // Nothing reaches the screen that cannot be true of the applications it
    // was counted from, or that names a line this CV does not have.
    ledgerResult.value = renderableResult(await engine.lineLedger(doc, items), doc);
    ledgerPhase.value = "done";
  } catch (failure) {
    ledgerPhase.value = "error";
    report(failure);
  }
}

// ─── Which one to spend the hour on ───────────────────────────────────

/**
 * Add or drop one application from the comparison, and answer again.
 *
 * Re-running is free — no model, no tokens — so changing the selection
 * changes the answer instead of leaving a result on screen that is about a
 * selection the user has already moved on from.
 */
export function toggleCompare(id: string): void {
  const next = toggleSelection(compareSelection.value, id);
  if (next === compareSelection.value) return;
  compareSelection.value = next;
  compareResult.value = null;
  comparePhase.value = "idle";
}

/**
 * Prepare the selection the screen opens with.
 *
 * A match deleted from the tracker leaves its id behind in a selection made
 * before it went, and a comparison quietly drawn from one posting is worse
 * than no comparison: it would keep the old columns on screen with nothing
 * saying why they stopped being about what the user picked. Pruned first, then
 * the two most recent if nothing is left, so the screen answers on arrival
 * instead of asking.
 */
export function startCompare(): void {
  const known = new Set(tracker.value.map((entry) => entry.id));
  const kept = compareSelection.value.filter((id) => known.has(id));
  if (kept.length !== compareSelection.value.length) {
    compareSelection.value = kept;
    compareResult.value = null;
    comparePhase.value = "idle";
  }
  if (compareSelection.value.length > 0) return;
  compareSelection.value = tracker.value.slice(0, DEFAULT_POSTINGS).map((entry) => entry.id);
}

/**
 * Line up the selected applications against the verdicts they already carry.
 *
 * Nothing here is generated and nothing is re-analysed: the numbers come from
 * matches the verifier already made, which is why this screen can rank
 * someone's options out loud when a fit score cannot.
 */
export async function runCompare(): Promise<void> {
  const ids = compareSelection.value;
  if (ids.length < MIN_POSTINGS) return;

  comparePhase.value = "running";
  error.value = null;
  try {
    const records: StoredMatch[] = [];
    for (const id of ids) {
      try {
        const record = await store.loadMatch(id);
        if (record) records.push(record);
      } catch {
        // One unreadable match is not a reason to answer nothing; the columns
        // that do load are still true of the matches they came from.
      }
    }
    const report = await engine.comparePostings(replayItems(records));
    // Nothing reaches the screen whose numbers cannot be true of the
    // requirements they were counted from.
    compareResult.value = {
      ...report,
      columns: renderableColumns(report.columns),
      shared_gaps: renderable(report.shared_gaps, report.postings),
      shared_proved: renderable(report.shared_proved, report.postings),
    };
    comparePhase.value = "done";
  } catch (failure) {
    comparePhase.value = "error";
    report(failure);
  }
}

// ─── Interview brief ──────────────────────────────────────────────────

/**
 * What this application will be asked to back up, out loud.
 *
 * The app was honest right up to the moment the application was sent and then
 * went quiet: a tracker row could be marked *Interview* and nothing followed.
 * This is the follow-through, and it is the only screen that reads the match,
 * the CV and the sentences the user actually sent as one document.
 *
 * Free to run — no model, no tokens — so it is rebuilt on open instead of
 * stored, and it is honest the moment the CV changes underneath it.
 *
 * Only the accepted bullets go: the brief is about the sentences the
 * interviewer is holding, not the ones the app once suggested.
 */
export async function runBrief(): Promise<void> {
  const match = currentMatch.value;
  const doc = activeCv();
  if (!match || !doc) return;

  briefPhase.value = "running";
  error.value = null;
  try {
    briefResult.value = await engine.interviewBrief({
      cv: doc,
      match,
      tailor: acceptedTailor(),
      letter: letterResult.value,
      assertions: assertionList(),
    });
    briefPhase.value = "done";
  } catch (failure) {
    briefPhase.value = "error";
    report(failure);
  }
}

// ─── Worth another look ───────────────────────────────────────────────

/**
 * Ask every saved application whether the CV has since answered it.
 *
 * "Since you applied" answers this one application at a time and answers it
 * well; it is also the wrong shape for someone applying to thirty jobs a
 * month, who will never open thirty saved applications to find out whether
 * last Tuesday's sentence changed any of them. The answer existed and nothing
 * was going to read it.
 *
 * Free to run — no model, no tokens — so it is rebuilt whenever the shelf or
 * the CV moves rather than cached into something quietly untrue.
 */
export async function runWorth(): Promise<void> {
  const doc = activeCv();
  if (!doc) return;

  worthPhase.value = "running";
  error.value = null;
  try {
    const records = await store.loadRecentMatches(RECENT_MATCHES, activeCvId.value);
    const items = replayItems(records);
    if (items.length === 0) {
      // Nothing saved yet: a real answer, and asking the engine to scan an
      // empty shelf would spend an invoke to be told so.
      worthResult.value = {
        version: 1,
        applications: 0,
        written: doc.lines.filter((line) => line.added_at).length,
        items: [],
      };
      worthPhase.value = "done";
      return;
    }
    worthResult.value = await engine.worthRerunning(doc, items);
    worthPhase.value = "done";
  } catch (failure) {
    worthPhase.value = "error";
    report(failure);
  }
}

// ─── What the re-run changed ──────────────────────────────────────────

/**
 * Line this run up against the last one of the same posting.
 *
 * Four screens in this app ask the user to write a sentence into their CV,
 * and the last of them ends in "run this posting again". This is the only
 * place that ever reports back on whether it worked — and the one moment the
 * whole product is built towards: the line they wrote turning a "no evidence
 * yet" into a receipt.
 *
 * Free to run, like every other comparison here: both runs are already
 * stored, so nothing is re-analysed and no model is involved.
 */
export async function runRerun(): Promise<void> {
  const match = currentMatch.value;
  const doc = activeCv();
  const earlier = earlierRun.value;
  if (!match || !doc || !earlier) return;

  rerunPhase.value = "running";
  error.value = null;
  try {
    const record = await store.loadMatch(earlier.id);
    if (!record) {
      // The index named a run that storage no longer has. Saying nothing is
      // right: the comparison would be with a document that is gone.
      rerunResult.value = null;
      rerunPhase.value = "done";
      return;
    }
    // Nothing reaches the screen that cannot be true of the two runs it came
    // from, or that credits a line this CV no longer has.
    rerunResult.value = renderableDiff(
      await engine.compareRuns({ cv: doc, before: record.match, after: match }),
      doc,
    );
    rerunPhase.value = "done";
  } catch (failure) {
    rerunPhase.value = "error";
    report(failure);
  }
}

// ─── The profile ──────────────────────────────────────────────────────

/**
 * Write the headline and the About section, from the CV alone.
 *
 * The only generated screen that needs no application: it is reached from the
 * CV, it reads the CV, and what it writes has to be true of the person on any
 * day — which is why the verifier is stricter here than anywhere else, with
 * no posting to lend a term.
 */
export async function runProfile(): Promise<void> {
  const doc = activeCv();
  if (!doc || showingExample.value) return;

  profilePhase.value = "running";
  error.value = null;
  try {
    profileResult.value = await engine.profile(doc, { locale: currentLocale() });
    profilePhase.value = "done";
  } catch (failure) {
    profilePhase.value = "error";
    report(failure);
  }
}

// ─── The follow-up ────────────────────────────────────────────────────

/**
 * Write the note, or find out there is nothing to write.
 *
 * The screen is reached from a tracker row that has gone quiet, so the app
 * already knows the day it was sent — that date is what the note is counted
 * from, and the engine is handed it rather than guessing.
 */
export async function runFollowup(): Promise<void> {
  const match = currentMatch.value;
  const doc = activeCv();
  if (!match || !doc || showingExample.value) return;

  followupPhase.value = "running";
  error.value = null;
  try {
    const entry = tracker.value.find((row) => row.id === match.id);
    followupResult.value = await engine.followup(doc, match, {
      locale: currentLocale(),
      sentAt: entry?.status_at ?? null,
    });
    followupPhase.value = "done";
  } catch (failure) {
    followupPhase.value = "error";
    report(failure);
  }
}

/** Open a saved application straight at its follow-up. */
export async function openFollowup(id: string): Promise<void> {
  await openMatch(id);
  navigate("/followup");
}

// ─── Since you applied ────────────────────────────────────────────────

/**
 * What this application has missed.
 *
 * The app is honest right up to the moment an application is sent and then
 * goes quiet about it — while three other screens keep growing the CV
 * underneath it. Someone answers a gap question a week later, and nothing
 * anywhere connects that sentence to the five applications it would have
 * changed.
 *
 * Free to run — no model, no tokens — so it is rebuilt on open rather than
 * stored, which also means it cannot go quietly out of date the next time a
 * line is added.
 */
export async function runSince(): Promise<void> {
  const match = currentMatch.value;
  const doc = activeCv();
  if (!match || !doc) return;

  sincePhase.value = "running";
  error.value = null;
  try {
    // The day the user said it went out, when the record has one. Rows
    // written before v1.3 carry no `status_at`, and the engine dates from the
    // match itself rather than inventing a day.
    const entry = tracker.value.find((row) => row.id === match.id);
    sinceResult.value = await engine.sinceApplied({
      cv: doc,
      match,
      sentAt: entry?.status_at ?? null,
    });
    sincePhase.value = "done";
  } catch (failure) {
    sincePhase.value = "error";
    report(failure);
  }
}

/**
 * Take the user back to New match, with what this app kept of the posting.
 *
 * The posting's text is deliberately not stored — keeping an employer's words
 * in someone's account for months is not this product's to do, and the
 * engine's cache holds only a hash. So this hands over the URL when the
 * posting came from one and an empty box when it did not, rather than
 * pretending a re-run is one click.
 */
export function reRunPosting(): void {
  const match = currentMatch.value;
  postingText.value = "";
  postingUrl.value = match?.posting.url ?? "";
  urlPhase.value = "idle";
  navigate("/new");
}

/**
 * Open a saved application straight at what has changed since it went out.
 *
 * From the tracker, like the brief: that is where someone looks at a row they
 * sent two weeks ago and wonders whether it is worth doing anything about.
 */
export async function openSince(id: string): Promise<void> {
  await openMatch(id);
  navigate("/since");
}

/**
 * Open a saved application straight at its brief.
 *
 * The tracker is where someone marks a row *Interview*, so it is also where
 * they come back the night before one. Loading the match first is what gives
 * the brief its accepted bullets and its letter.
 */
export async function openBrief(id: string): Promise<void> {
  await openMatch(id);
  navigate("/brief");
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

/**
 * Hand the user their CV back.
 *
 * Every answer loop in this app writes into the stored CV — a gap question,
 * an audit finding, a recurring gap — and none of those sentences was ever
 * able to reach the document an employer actually reads. The interview brief
 * says so out loud on every requirement that rests on one (`self_added`);
 * this is what turns that warning into something a person can fix.
 *
 * `additions` is for someone who keeps a CV they designed: the new sentences
 * on their own, to paste, rather than a plain replacement for it.
 */
export async function exportCvDocument(mode: CvExportMode): Promise<void> {
  const doc = cv.value?.doc;
  if (!doc) return;

  cvExportPhase.value = "running";
  cvExportMode.value = mode;
  error.value = null;
  try {
    const file = await engine.exportCv(doc, mode, currentLocale());
    await saveFile(file.filename, file.content_b64, file.mime);
    cvExportLines.value = file.lines;
    cvExportPhase.value = "done";
  } catch (failure) {
    cvExportPhase.value = "error";
    report(failure);
  }
}

/** Whether the CV holds anything the user typed here themselves. */
export const cvHasAdditions = computed(() =>
  (cv.value?.doc.lines ?? []).some((line) => line.added_at),
);

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
    .filter((bullet) => accepted[bulletKey(bullet)] !== undefined)
    .map((bullet) => ({ ...bullet, suggestion: accepted[bulletKey(bullet)]! }));
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
  auditResult.value = null;
  auditPhase.value = "idle";
  answeredFindings.value = new Set();
  clearCheck();
  clearAnswers();
  recurringResult.value = null;
  recurringPhase.value = "idle";
  answeredRecurring.value = new Set();
  ledgerResult.value = null;
  ledgerPhase.value = "idle";
  sinceResult.value = null;
  sincePhase.value = "idle";
  followupResult.value = null;
  followupPhase.value = "idle";
  profileResult.value = null;
  profilePhase.value = "idle";
  rerunResult.value = null;
  rerunPhase.value = "idle";
  worthResult.value = null;
  worthPhase.value = "idle";
  compareResult.value = null;
  comparePhase.value = "idle";
  compareSelection.value = [];
  try {
    await store.deleteEverything(cvProfiles.value.map((profile) => profile.id));
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
  cvProfiles.value = [{ id: DEFAULT_CV_ID, name: untitledCv(1), created_at: new Date().toISOString() }];
  activeCvId.value = DEFAULT_CV_ID;
  addingCv.value = false;
  cvExportPhase.value = "idle";
  cvExportLines.value = 0;
  setIndex([]);
  currentMatch.value = null;
  tailorResult.value = null;
  letterResult.value = null;
  gapsResult.value = null;
  gapsPhase.value = "idle";
  answeredGaps.value = new Set();
  briefResult.value = null;
  briefPhase.value = "idle";
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
