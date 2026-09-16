/**
 * TypeScript twins of the Pydantic models in `receipts_engine/schemas.py`.
 *
 * These two files are the contract (docs.md §4). When one changes the other
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

export interface LetterParagraph {
  text: string;
  line_ids: LineId[];
}

export interface LetterResult {
  version: 1;
  match_id: string;
  tone: Tone;
  paragraphs: LetterParagraph[];
  placeholders: string[];
}

export interface ExportResult {
  filename: string;
  content_b64: string;
  mime: string;
}

/** Error codes from docs.md §3. Every one has a string in both locales. */
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
  | "internal_error"
  | "host_unavailable"
  | "url_fetch_failed";

export interface EngineError {
  code: ErrorCode;
  message: string;
  retriable: boolean;
  details?: Record<string, unknown>;
}

/** Progress stages the plugin emits (docs.md §3). */
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
  strong: number;
  total: number;
  status: ApplicationStatus;
}

export interface StoredMatch {
  match: MatchResult;
  tailor?: TailorResult;
  letter?: LetterResult;
  status: ApplicationStatus;
}

export interface Profile {
  locale: Locale;
  onboarding_done: boolean;
  created_at: string;
}

export interface StoredCv {
  doc: CVDoc;
  filename: string | null;
  updated_at: string;
}
