/**
 * TypeScript twins of the Pydantic models in `receipts_engine/schemas.py`.
 *
 * These two files are the contract (docs/docs.md §4). When one changes the other
 * has to change in the same commit — a drift here is a runtime error the
 * compiler cannot see, because the payload crosses a JSON boundary.
 */

export type LineId = `L${number}`;
export type RequirementId = `R${number}`;

export type Section =
  | "header"
  | "summary"
  | "experience"
  | "education"
  | "skills"
  | "projects"
  | "certifications"
  | "other";

export type Status = "strong" | "partial" | "missing";
export type Kind = "must" | "nice";
export type Category = "skill" | "experience" | "education" | "domain" | "soft" | "logistics";
export type Language = "en" | "tr" | "other";
export type Locale = "en" | "tr";
export type Tone = "plain" | "warm" | "formal";
export type Length = "short" | "standard";
export type CvWarning = "multi_column_suspected" | "tables_flattened" | "truncated";

export interface CvLine {
  id: LineId;
  text: string;
  section: Section;
  /**
   * ISO timestamp, set only on a line the user typed themselves answering a
   * gap question. A parsed line never carries one, so the CV sheet can say
   * which lines came out of the document and which the person added after.
   */
  added_at?: string;
}

export interface CVDoc {
  version: 1;
  hash: string;
  lines: CvLine[];
  detected_language: Language;
  warnings: CvWarning[];
}

export interface Requirement {
  id: RequirementId;
  text: string;
  kind: Kind;
  category: Category;
  source_quote: string;
}

export interface Evidence {
  requirement_id: RequirementId;
  status: Status;
  line_ids: LineId[];
  why: string;
  /**
   * Technologies the requirement named that the cited lines do not show.
   *
   * Present only on a verdict the guard cut back from `strong` to `partial`
   * (`pipeline/match.py`), written the way the **posting** spells them.
   * Absent on records written before v1.3. No sentence: the screen says what
   * it means, in the user's language.
   */
  unshown?: string[];
}

export interface MatchSummary {
  total: number;
  strong: number;
  partial: number;
  missing: number;
  must_missing: number;
  sentence: string;
}

export interface PostingMeta {
  title: string | null;
  company: string | null;
  url: string | null;
  hash: string;
  language: Language;
}

export interface MatchResult {
  version: 1;
  id: string;
  created_at: string;
  posting: PostingMeta;
  requirements: Requirement[];
  evidence: Evidence[];
  summary: MatchSummary;
  cv_hash: string;
}

export interface TailoredBullet {
  source_line_ids: LineId[];
  original: string;
  suggestion: string | null;
  targets: RequirementId[];
  dropped_reason?: "unsupported_claims";
  unsupported_tokens?: string[];
}

export interface TailorResult {
  version: 1;
  match_id: string;
  bullets: TailoredBullet[];
}

/**
 * Something in the user's own CV that an interviewer is likely to press on.
 *
 * The engine names the kind and the subject and stops there; the sentence the
 * user reads is built here, from the string table, in their language. An
 * engine that phrased the accusation would be shipping untranslated copy.
 */
export type CvFindingKind = "skill_unevidenced" | "title_unevidenced" | "date_conflict";

export interface CvFinding {
  kind: CvFindingKind;
  /** The canonical term, for comparison and grouping: `grpc`, `senior`. */
  subject: string;
  /**
   * The same thing as the CV writes it — `gRPC`, `Senior`, `k8s`.
   *
   * Always what the screen renders. Showing the canonical form back to someone
   * tells them their skills list says "grpc" when it says "gRPC", which reads
   * as the app not having looked properly.
   */
  surface: string;
  line_ids: LineId[];
}

export interface CvAudit {
  version: 1;
  cv_hash: string;
  findings: CvFinding[];
}

/**
 * A class of fact the verifier checks. The same vocabulary `verify/grounding.py`
 * uses, because a checked claim *is* one of its claims.
 */
export type ClaimKind = "number" | "date" | "duration" | "tech" | "proper_noun" | "title";

/**
 * One fact in a pasted document that the CV cannot back.
 *
 * `surface` is how **that document** writes it, never the lexicon's canonical
 * form — the same split as `CvFinding`, for the same reason: quoting someone
 * words they did not type is how they stop reading the rest of the list.
 */
export interface CheckedClaim {
  kind: ClaimKind;
  surface: string;
}

/** One sentence of a checked document, and what it claims without evidence. */
export interface CheckedLine {
  /** Position among the sentences read, so the list follows the document. */
  index: number;
  text: string;
  claims: CheckedClaim[];
}

/**
 * The verifier's verdict on a document Receipts did not write.
 *
 * Nothing about it is stored. The document arrives, is read, and is gone; what
 * survives is whatever the user chose to add to their CV afterwards, in their
 * own words.
 */
export interface DocumentCheck {
  version: 1;
  cv_hash: string;
  /** Sentences read — the denominator for the flagged list. */
  checked: number;
  /** Sentences with at least one unbacked claim, before the cap on `flagged`. */
  unbacked: number;
  flagged: CheckedLine[];
  truncated: boolean;
  /** Company and role of the open application: the envelope, not a claim. */
  masked: string[];
}

/**
 * One thing the market kept asking this person for.
 *
 * `key` is canonical (the lexicon term, or a normalised text key) and exists
 * for grouping; `surface` is how the postings write it and is what the screen
 * renders — the same split, for the same reason, as `CvFinding`.
 *
 * `asked` is the denominator and the reason this screen can be trusted: a term
 * asked twenty times and proved eighteen of them is not a recurring gap, and
 * without `asked` there is no way to know that. `texts` carries the wordings
 * that were merged, so the grouping is something the user can disagree with
 * rather than something they have to take on trust.
 */
export interface RecurringGroup {
  key: string;
  surface: string;
  kind: Kind;
  /** Distinct applications that asked for it. */
  asked: number;
  /** Of those, how many the CV could not prove. */
  unproven: number;
  /** Of those, how many asked for it as a must-have. */
  must: number;
  /** `"<match_id>#<req_id>"` for every member. */
  ids: string[];
  texts: string[];
}

export interface RecurringResult {
  version: 1;
  /** Distinct applications the report is drawn from. */
  matches: number;
  /** Asked more than once and never proved. */
  groups: RecurringGroup[];
  /** Asked more than once and always proved. */
  strengths: RecurringGroup[];
}

/**
 * One saved application, as a comparison with the others reads it.
 *
 * Counts rather than a score. Every number is a tally of verdicts a match
 * already recorded, so the user can open that match and check it — which is
 * the one thing a fit percentage can never offer, and the reason this screen
 * draws no gauge.
 */
export interface CompareColumn {
  /** The match id, so the UI can put its own role and company back on it. */
  match: string;
  asked: number;
  proved: number;
  related: number;
  must_asked: number;
  must_proved: number;
  /** Must-haves this posting asks for and the CV cannot prove. */
  blockers: string[];
  /** Proved here, and at least one of the others never asks for it. */
  edge: string[];
}

export interface CompareResult {
  version: 1;
  /** Distinct applications compared. Below two there are no columns. */
  postings: number;
  /** Ranked by the engine: fewest unproved must-haves first. */
  columns: CompareColumn[];
  /** Asked by every one of them and proved in none. */
  shared_gaps: RecurringGroup[];
  /** Asked by every one of them and proved every time. */
  shared_proved: RecurringGroup[];
}

/**
 * One CV line, and what it has actually carried.
 *
 * No text and no section: the screen is rendering the CV next to this, and a
 * second copy of the sentence could disagree with the document the user is
 * reading — the same rule `BriefItem` follows.
 *
 * `applications` is a numerator and means nothing without `LedgerResult.
 * applications` beside it: cited in four is a strong line out of five
 * applications and a coincidence out of forty.
 */
export interface LedgerLine {
  id: LineId;
  /** Distinct applications that cited it. */
  applications: number;
  /** Requirements it was accepted as evidence for, across those. */
  citations: number;
  /** Of those, how many were must-haves. */
  must: number;
  /** Must-haves where this was the only line cited — the application rested on it. */
  decisive: number;
  /** What the postings called the things it answered, most-asked first. */
  proves: string[];
  /** The user wrote this line here, answering a gap. */
  added: boolean;
}

/**
 * One saved application the CV has since gained an answer for.
 *
 * `match` is the id the UI sent; the role and the company stay here, where
 * the tracker's own wording lives. `unproved` is the denominator — "2 of the
 * 5 it could not show" is a different sentence from "2 of the 2".
 */
export interface WorthItem {
  match: string;
  unproved: number;
  requirements: number;
  must: number;
  /** The terms, spelled as the CV writes them. */
  terms: string[];
  /** The lines that named them, all written after this application went out. */
  line_ids: LineId[];
  /** The postings' own wordings, so a row can be checked rather than trusted. */
  texts: string[];
}

export interface WorthResult {
  version: 1;
  /** Applications read — the denominator for "3 of your 18". */
  applications: number;
  /** Lines the user has written into this CV at all. Zero means the screen
   *  has a different thing to say: there is nothing new to check against. */
  written: number;
  items: WorthItem[];
}

/**
 * How one demand moved between two runs of the same posting.
 *
 * Read off two verdicts, never judged. The two `*_ask` values are about the
 * postings being read differently, not about the candidate, and the screen
 * keeps them apart from the gains and the losses for that reason.
 */
export type RunDirection = "gained" | "lost" | "same" | "new_ask" | "dropped_ask";

export interface RunChange {
  /** The lexicon term, or a normalised text key — the grouping that lines two
   *  runs up, since `R3` in one is not `R3` in the other. */
  key: string;
  surface: string;
  kind: Kind;
  /** What the older run said; null when it never asked. */
  before: Status | null;
  /** What the newer run said; null when it no longer asks. */
  after: Status | null;
  direction: RunDirection;
  /** What the newer run cited. */
  line_ids: LineId[];
  /** The newer run stands on a line written after the older run — the only
   *  case where the app claims the user's own sentence did it. */
  credited: boolean;
  /** The wordings that were grouped, so the pairing can be argued with. */
  texts: string[];
}

export interface RunDiff {
  version: 1;
  before_id: string;
  after_id: string;
  days_between: number | null;
  /** Each run's own summary, quoted rather than recomputed: the totals can
   *  differ, because the posting is read again on every run. */
  before_strong: number;
  before_total: number;
  after_strong: number;
  after_total: number;
  /** Lines written between the two runs. */
  added_between: LineId[];
  gained: RunChange[];
  lost: RunChange[];
  still: RunChange[];
  differed: RunChange[];
}

/**
 * A requirement an application could not show, and what the CV now names.
 *
 * Not evidence, and the copy never calls it that. Deciding that a sentence
 * proves a requirement is the match's job — a model call with a verifier
 * behind it — and this is a lexicon hit between two strings. It is a reason
 * to run the match again, which is what the screen offers.
 */
export interface SinceAnswer {
  requirement_id: RequirementId;
  kind: Kind;
  /** The verdict it got when the application went out. */
  status: Status;
  /** Lines added since, which name the same thing. */
  line_ids: LineId[];
  /** The shared terms, spelled as the CV writes them. */
  terms: string[];
}

export interface SinceResult {
  version: 1;
  match_id: string;
  /** Whole days since it went out; null when nothing datable was recorded. */
  days: number | null;
  /** Whether `days` counts from the day it was marked sent, or the day it was run. */
  dated_from: "sent" | "checked";
  /** The CV is no longer the document this application was checked against. */
  cv_changed: boolean;
  /** Lines written into the CV since it went out. */
  added: LineId[];
  /** Must-haves first. Empty is the common answer. */
  answers: SinceAnswer[];
}

export interface LedgerResult {
  version: 1;
  /** Applications counted. Below `MIN_MATCHES` every list is empty. */
  applications: number;
  /** Left out: checked against a different parse of this CV, where the same
   *  line ids mean different sentences. Said out loud rather than swallowed. */
  skipped: number;
  /** CV lines that could be cited — everything but the header. */
  eligible: number;
  /** Of those, how many have been evidence at least once. */
  cited: number;
  /** Cited lines, most applications first. */
  working: LedgerLine[];
  /** Lines no application has ever cited. Not a cut list. */
  idle: LedgerLine[];
  /** The lines the user added themselves, and what they have proved since. */
  added: LedgerLine[];
}

/**
 * One requirement the CV cannot prove, and the question that asks about it.
 *
 * `angle` is null far more often than not — it is dropped rather than softened
 * when the verifier cannot trace it to the lines in `line_ids` — so the card
 * has to read well without one.
 */
export interface GapItem {
  requirement_id: RequirementId;
  question: string;
  angle: string | null;
  line_ids: LineId[];
  /** The model's phrasing was refused and the blunt fallback is showing. */
  templated: boolean;
}

export interface GapResult {
  version: 1;
  match_id: string;
  items: GapItem[];
}

/**
 * What an interviewer is most likely to press on, for one requirement.
 *
 * Named after the *shape* of the evidence, never after a judgement about the
 * person — the same split as `CvFindingKind`: the engine finds, the UI
 * phrases. `listed_not_shown` is the one worth knowing by heart: the match
 * was right that the word is in the CV, and every line it could cite was in
 * the skills list.
 */
export type BriefRisk =
  | "no_evidence"
  | "listed_not_shown"
  | "self_added"
  | "related_only"
  | "proved";

export type ClaimSource = "bullet" | "letter";

/** A sentence the user already sent, and the CV lines underneath it. */
export interface BriefClaim {
  source: ClaimSource;
  text: string;
  line_ids: LineId[];
}

/**
 * One requirement, its evidence and what was claimed about it.
 *
 * Carries no requirement text and no line text: the screen has the match and
 * the CV in hand, and a second copy here could disagree with the match map
 * about what a line says.
 */
export interface BriefItem {
  requirement_id: RequirementId;
  kind: Kind;
  risk: BriefRisk;
  line_ids: LineId[];
  claims: BriefClaim[];
}

export interface InterviewBrief {
  version: 1;
  match_id: string;
  /** The CV the brief was built from — not always the one the match used. */
  cv_hash: string;
  /** The CV moved after this was sent: the interviewer has the older one. */
  cv_changed: boolean;
  risks: BriefItem[];
  proved: BriefItem[];
  loose_claims: BriefClaim[];
}

/**
 * What the CV could do with one question an employer asked.
 *
 * Named from the evidence, never from a judgement about the person — the same
 * split as `CvFindingKind` and `BriefRisk`, and the UI writes the sentence.
 *
 * `not_about_you` is the one this feature exists for: "why do you want to work
 * here" cannot be answered from a CV, because a CV records what someone did
 * and not what they want. The app writes nothing, and says why.
 */
export type AnswerKind = "answered" | "no_evidence" | "not_about_you";

export interface AnswerSentence {
  text: string;
  line_ids: LineId[];
}

export interface QuestionAnswer {
  /** The question as the user pasted it, so the screen pairs the two safely. */
  question: string;
  kind: AnswerKind;
  /** Empty unless `kind` is `answered`; the engine enforces that, not the UI. */
  sentences: AnswerSentence[];
  /** Sentences the verifier refused. Shown, never hidden. */
  dropped: number;
}

export interface AnswerResult {
  version: 1;
  /** The application the questions arrived with, when there was one. */
  match_id: string | null;
  items: QuestionAnswer[];
}

export interface LetterParagraph {
  text: string;
  line_ids: LineId[];
}

/**
 * Why the follow-up screen says what it says.
 *
 * `nothing_new` is the refusal the feature exists for: an application that has
 * gone quiet and a CV that has not moved leaves nothing worth a stranger's
 * minute, and the app writes nothing rather than the warm paragraph every
 * other tool sends.
 */
export type FollowupKind = "new_evidence" | "nothing_new";

export interface FollowupResult {
  version: 1;
  match_id: string;
  kind: FollowupKind;
  /** Days since it went out, and which clock that is (`SinceResult`). */
  days: number | null;
  dated_from: "sent" | "checked";
  /** Same shape and same contract as a cover letter's paragraphs. */
  paragraphs: LetterParagraph[];
  /** What the reader must still fill in by hand. */
  placeholders: string[];
  /** The lines the note stands on, all written after it went out. */
  line_ids: LineId[];
  /** What those lines name, spelled as the CV spells it. */
  terms: string[];
}

/**
 * A headline and an About section, written from the CV and nothing else.
 *
 * The only generated surface with no posting behind it — and therefore no
 * posting wording to lend it a concept. `headline` is empty when nothing
 * survived the verifier, which the screen says rather than hiding.
 */
export interface ProfileResult {
  version: 1;
  cv_hash: string;
  headline: string;
  headline_line_ids: LineId[];
  about: LetterParagraph[];
}

export interface LetterResult {
  version: 1;
  match_id: string;
  tone: Tone;
  paragraphs: LetterParagraph[];
  placeholders: string[];
}

/** Which document `export_cv` renders. */
export type CvExportMode = "full" | "additions";

/**
 * The CV back out.
 *
 * No `unverified` counterpart to `ExportResult`: there is nothing to verify,
 * because every line in the file is a line of the CV it was built from.
 */
export interface CvExportResult {
  filename: string;
  content_b64: string;
  mime: string;
  /** How many CV lines the document carries. */
  lines: number;
}

export interface ExportResult {
  filename: string;
  content_b64: string;
  mime: string;
  /** Hand-edited lines the CV could no longer vouch for. */
  unverified?: number;
}

/** Error codes from docs/docs.md §3. Every one has a string in both locales. */
export type ErrorCode =
  | "file_too_large"
  | "unreadable_file"
  | "cv_too_short"
  | "no_requirements_found"
  | "model_output_invalid"
  | "sampling_unavailable"
  | "cancelled"
  | "upload_expired"
  | "invalid_args"
  | "rate_limited"
  | "internal_error"
  | "host_unavailable"
  | "url_fetch_failed"
  // UI-only: the engine succeeded but the surrounding host call did not.
  | "save_failed"
  | "export_failed"
  | "export_empty"
  | "cv_changed";

export interface EngineError {
  code: ErrorCode;
  message: string;
  retriable: boolean;
  details?: Record<string, unknown>;
}

/** Progress stages the plugin emits (docs/docs.md §3). */
export type Stage = "normalize" | "extract" | "match" | "guard" | "summarize" | "done";

export interface ProgressEvent {
  stage: Stage;
  pct: number;
  partial?: {
    requirements?: { id: RequirementId; text: string; kind: Kind }[];
    matched?: { id: RequirementId; status: Status; line_ids: LineId[] }[];
    summary?: MatchSummary;
    truncated?: boolean;
  };
}

/** Tracker entry — one row per saved match. */
export type ApplicationStatus = "drafted" | "applied" | "interview" | "offer" | "closed";

export interface TrackerEntry {
  id: string;
  company: string | null;
  role: string | null;
  created_at: string;
  /**
   * The posting this run was made against (`MatchResult.posting.hash`).
   *
   * What lets the app find an earlier run of the same posting without reading
   * every record. Absent on rows written before v1.3, and that absence is
   * honoured: an older run the app cannot identify is not claimed to exist.
   */
  posting?: string;
  /**
   * When the status was last changed.
   *
   * Absent on every record written before v1.3, and that absence is a real
   * answer: "applied 9 days ago" cannot be said about a row that never
   * recorded the day, so the screen dates from `created_at` and says so.
   */
  status_at?: string;
  strong: number;
  total: number;
  status: ApplicationStatus;
  /**
   * Which CV this application was checked against.
   *
   * Absent on every record written before v1.2, which is exactly what
   * `DEFAULT_CV_ID` means: there was only one CV then, and it is the one those
   * matches were made against.
   */
  cv?: string;
}

/**
 * The user disagreeing with a verdict, recorded beside it.
 *
 * The match this app produced is never rewritten. A model that missed a
 * requirement is wrong, and the person whose career it is gets to say so — but
 * the correction stays *theirs*: labelled everywhere it travels, kept out of
 * the evidence counts, and never turned into something the app claims to have
 * checked.
 */
export interface Assertion {
  /** CV lines the user says cover the requirement, in the order they picked. */
  line_ids: LineId[];
  /** When they said so. */
  at: string;
}

export interface StoredMatch {
  match: MatchResult;
  tailor?: TailorResult;
  letter?: LetterResult;
  status: ApplicationStatus;
  /** When `status` was last set. Absent on records written before v1.3. */
  status_at?: string;
  /** Accepted (and possibly edited) bullets, keyed by their first CV line. */
  accepted?: Record<string, string>;
  /** The CV profile it was checked against; absent means the first one. */
  cv?: string;
  /**
   * Requirements the user told the app it got wrong, by requirement id.
   *
   * Kept beside `match` rather than merged into `match.evidence`, and that is
   * the whole design: the engine's verdict stays exactly as it was produced,
   * so the record can always answer "what did the app find" and "what did the
   * person say" separately. It also means the cross-application screens keep
   * counting what the market can see, not what only the candidate can.
   */
  assertions?: Record<string, Assertion>;
}

/** Interface appearance. Absent on records written before v1.0.1. */
export type Theme = "system" | "light" | "dark";

export interface Profile {
  locale: Locale;
  onboarding_done: boolean;
  created_at: string;
  theme?: Theme;
}

export interface StoredCv {
  doc: CVDoc;
  filename: string | null;
  updated_at: string;
}

/**
 * One of the CVs the user keeps — not to be confused with `Profile`, which is
 * this app's own settings record.
 *
 * A career switcher applies to two kinds of role with two different documents,
 * and until v1.2 the app held one. That was not only inconvenient: the screens
 * that read across applications (`recurring_gaps`, `compare_postings`) would
 * mix both careers into one report and tell someone to go and learn the thing
 * half their applications never asked for.
 */
export interface CvProfile {
  id: string;
  /** The user's own word for it — "Backend", "Data". Never generated. */
  name: string;
  created_at: string;
}

/**
 * The set of CVs and which one is in use.
 *
 * Written only once there is a second CV or a rename: a user with one CV never
 * gets this key, and their document stays exactly where v1.0 put it.
 */
export interface CvProfiles {
  version: 1;
  active: string;
  list: CvProfile[];
}
