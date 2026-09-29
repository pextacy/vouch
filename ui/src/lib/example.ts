/**
 * The pre-recorded example (`docs/prd.md` F8).
 *
 * "See an example" shows a finished match without calling the model. That is
 * deliberate on two counts: a first-time visitor sees the output before
 * committing their CV, and a demo click never produces a Qualified App Run,
 * so it cannot inflate the MAU number the programme pays on.
 *
 * The same fixture backs preview mode, so the UI is fully explorable outside
 * the host iframe.
 */

import type {
  CvAudit,
  CVDoc,
  GapResult,
  InterviewBrief,
  LetterResult,
  MatchResult,
  TailorResult,
} from "./types";

export const EXAMPLE_CV: CVDoc = {
  version: 1,
  hash: "example-cv-hash",
  detected_language: "en",
  warnings: [],
  lines: [
    { id: "L1", text: "Maya Collins — Backend Engineer, Berlin", section: "header" },
    { id: "L2", text: "Acme Payments — Backend Engineer, 2018–2024", section: "experience" },
    {
      id: "L3",
      text: "Built payment reconciliation services in Go for 1,200 merchant accounts.",
      section: "experience",
    },
    {
      id: "L4",
      text: "Migrated the reporting pipeline from MySQL to PostgreSQL with zero downtime.",
      section: "experience",
    },
    {
      id: "L5",
      text: "Ran the settlement workers on k8s across two regions.",
      section: "experience",
    },
    {
      id: "L6",
      text: "Led a team of 4 engineers and owned the on-call rotation.",
      section: "experience",
    },
    {
      id: "L7",
      text: "Reduced settlement errors by 18% across the ledger.",
      section: "experience",
    },
    { id: "L8", text: "MSc Computer Science, University of Edinburgh, 2016", section: "education" },
    { id: "L9", text: "Go, Python, PostgreSQL, Kubernetes, Docker, gRPC, Redis", section: "skills" },
  ],
};

export const EXAMPLE_MATCH: MatchResult = {
  version: 1,
  id: "example",
  created_at: "2026-09-16T09:12:00+00:00",
  cv_hash: "example-cv-hash",
  posting: {
    title: "Senior Backend Engineer",
    company: "Northwind Ledger",
    url: null,
    hash: "example-posting-hash",
    language: "en",
  },
  requirements: [
    {
      id: "R1",
      text: "5+ years of backend engineering",
      kind: "must",
      category: "experience",
      source_quote: "5+ years of backend engineering experience",
    },
    {
      id: "R2",
      text: "Production experience with Go",
      kind: "must",
      category: "skill",
      source_quote: "Strong production experience with Go",
    },
    {
      id: "R3",
      text: "Running services on Kubernetes",
      kind: "must",
      category: "skill",
      source_quote: "Experience running services on Kubernetes",
    },
    {
      id: "R4",
      text: "PostgreSQL and schema migrations",
      kind: "must",
      category: "skill",
      source_quote: "Working knowledge of PostgreSQL and schema migrations",
    },
    {
      id: "R5",
      text: "Leading a small team",
      kind: "must",
      category: "experience",
      source_quote: "Experience leading a small team",
    },
    {
      id: "R6",
      text: "Event streaming with Kafka",
      kind: "must",
      category: "skill",
      source_quote: "Production experience with Kafka or a similar event bus",
    },
    {
      id: "R7",
      text: "Payments or fintech domain",
      kind: "nice",
      category: "domain",
      source_quote: "Payments or fintech domain experience",
    },
    {
      id: "R8",
      text: "Terraform for infrastructure",
      kind: "nice",
      category: "skill",
      source_quote: "Familiarity with Terraform",
    },
  ],
  evidence: [
    {
      requirement_id: "R1",
      status: "strong",
      line_ids: ["L2"],
      why: "Six years at Acme Payments, 2018–2024.",
    },
    {
      requirement_id: "R2",
      status: "strong",
      line_ids: ["L3"],
      why: "Built reconciliation services in Go in production.",
    },
    {
      requirement_id: "R3",
      status: "strong",
      line_ids: ["L5"],
      why: "Ran settlement workers on k8s across two regions.",
    },
    {
      requirement_id: "R4",
      status: "strong",
      line_ids: ["L4"],
      why: "Migrated a reporting pipeline to PostgreSQL.",
    },
    {
      requirement_id: "R5",
      status: "strong",
      line_ids: ["L6"],
      why: "Led a team of four engineers.",
    },
    { requirement_id: "R6", status: "missing", line_ids: [], why: "" },
    {
      requirement_id: "R7",
      status: "strong",
      line_ids: ["L3", "L7"],
      why: "Payment reconciliation and settlement work.",
    },
    { requirement_id: "R8", status: "missing", line_ids: [], why: "" },
  ],
  summary: {
    total: 8,
    strong: 6,
    partial: 0,
    missing: 2,
    must_missing: 1,
    sentence: "6 of 8 requirements have evidence in your CV. 1 must-have doesn't.",
  },
};

export const EXAMPLE_TAILOR: TailorResult = {
  version: 1,
  match_id: "example",
  bullets: [
    {
      source_line_ids: ["L3"],
      original: "Built payment reconciliation services in Go for 1,200 merchant accounts.",
      suggestion:
        "Built and ran production payment reconciliation services in Go serving 1,200 merchant accounts.",
      targets: ["R2", "R7"],
    },
    {
      source_line_ids: ["L5"],
      original: "Ran the settlement workers on k8s across two regions.",
      suggestion: "Operated settlement workers on Kubernetes across two regions.",
      targets: ["R3"],
    },
    {
      source_line_ids: ["L6"],
      original: "Led a team of 4 engineers and owned the on-call rotation.",
      suggestion: "Led a team of 4 engineers and owned the on-call rotation for settlement.",
      targets: ["R5"],
    },
    {
      source_line_ids: ["L7"],
      original: "Reduced settlement errors by 18% across the ledger.",
      suggestion: null,
      targets: ["R1"],
      dropped_reason: "unsupported_claims",
      unsupported_tokens: ["$2M", "99.9%"],
    },
  ],
};

export const EXAMPLE_LETTER: LetterResult = {
  version: 1,
  match_id: "example",
  tone: "plain",
  paragraphs: [
    {
      text: "I am writing about the Senior Backend Engineer role at Northwind Ledger. I have spent six years building payment infrastructure, which is the same problem your posting describes.",
      line_ids: ["L2"],
    },
    {
      text: "At Acme Payments I built the reconciliation services in Go that handled 1,200 merchant accounts, and I migrated the reporting pipeline to PostgreSQL without downtime.",
      line_ids: ["L3", "L4"],
    },
    {
      text: "I ran those settlement workers on Kubernetes across two regions and led a team of four engineers through the on-call rotation that kept them up.",
      line_ids: ["L5", "L6"],
    },
    {
      text: "I would be glad to talk about how that experience maps onto what you are building. Thank you for your time.",
      line_ids: [],
    },
  ],
  placeholders: [],
};

/**
 * The gap sheet for the recorded match: R6 (Kafka) and R8 (Terraform).
 *
 * Both card shapes are here on purpose, because both are common and they look
 * nothing alike. R6 carries an angle the verifier could trace to L5; R8 has
 * `angle: null`, which is what the engine returns whenever the CV holds nothing
 * adjacent — the usual outcome, not a failure.
 */
export const EXAMPLE_GAPS: GapResult = {
  version: 1,
  match_id: "example",
  items: [
    {
      requirement_id: "R6",
      question:
        "Has anything you built passed messages between services without you calling them directly?",
      angle: "You ran the settlement workers across two regions.",
      line_ids: ["L5"],
      templated: false,
    },
    {
      requirement_id: "R8",
      question: "Have you ever written the configuration that creates infrastructure, not just used it?",
      angle: null,
      line_ids: [],
      templated: false,
    },
  ],
};

/**
 * The audit of the recorded CV.
 *
 * These are the findings `audit.py` actually produces for `EXAMPLE_CV`, checked
 * by running it: the skills line (L9) names Docker, gRPC, Python and Redis, and
 * no experience, project or certification line shows any of the four in use.
 * Nothing is invented for the demo — if the example CV improved, this list
 * would have to shrink with it.
 */
export const EXAMPLE_AUDIT: CvAudit = {
  version: 1,
  cv_hash: "example-cv-hash",
  findings: [
    { kind: "skill_unevidenced", subject: "docker", surface: "Docker", line_ids: ["L9"] },
    { kind: "skill_unevidenced", subject: "grpc", surface: "gRPC", line_ids: ["L9"] },
    { kind: "skill_unevidenced", subject: "python", surface: "Python", line_ids: ["L9"] },
    { kind: "skill_unevidenced", subject: "redis", surface: "Redis", line_ids: ["L9"] },
  ],
};

/**
 * The interview brief for the recorded match.
 *
 * What `interview_brief()` returns for the fixtures above, run through the
 * engine rather than written by hand — with every suggested bullet accepted,
 * which is the premise the screen is showing: this is the application as it
 * would have been sent. Nothing is invented for the demo, so improving the
 * example CV would move this list too.
 *
 * Both halves are here because both are the point: R6 and R8 are what the CV
 * cannot back, and the proved rows carry the sentences that were sent with
 * the line numbers underneath them.
 */
export const EXAMPLE_BRIEF: InterviewBrief = {
  version: 1,
  match_id: "example",
  cv_hash: "example-cv-hash",
  cv_changed: false,
  risks: [
    { requirement_id: "R6", kind: "must", risk: "no_evidence", line_ids: [], claims: [] },
    { requirement_id: "R8", kind: "nice", risk: "no_evidence", line_ids: [], claims: [] },
  ],
  proved: [
    {
      requirement_id: "R1",
      kind: "must",
      risk: "proved",
      line_ids: ["L2"],
      claims: [
        {
          source: "letter",
          text: "I am writing about the Senior Backend Engineer role at Northwind Ledger. I have spent six years building payment infrastructure, which is the same problem your posting describes.",
          line_ids: ["L2"],
        },
      ],
    },
    {
      requirement_id: "R2",
      kind: "must",
      risk: "proved",
      line_ids: ["L3"],
      claims: [
        {
          source: "bullet",
          text: "Built and ran production payment reconciliation services in Go serving 1,200 merchant accounts.",
          line_ids: ["L3"],
        },
        {
          source: "letter",
          text: "At Acme Payments I built the reconciliation services in Go that handled 1,200 merchant accounts, and I migrated the reporting pipeline to PostgreSQL without downtime.",
          line_ids: ["L3", "L4"],
        },
      ],
    },
    {
      requirement_id: "R3",
      kind: "must",
      risk: "proved",
      line_ids: ["L5"],
      claims: [
        {
          source: "bullet",
          text: "Operated settlement workers on Kubernetes across two regions.",
          line_ids: ["L5"],
        },
        {
          source: "letter",
          text: "I ran those settlement workers on Kubernetes across two regions and led a team of four engineers through the on-call rotation that kept them up.",
          line_ids: ["L5", "L6"],
        },
      ],
    },
    {
      requirement_id: "R4",
      kind: "must",
      risk: "proved",
      line_ids: ["L4"],
      claims: [
        {
          source: "letter",
          text: "At Acme Payments I built the reconciliation services in Go that handled 1,200 merchant accounts, and I migrated the reporting pipeline to PostgreSQL without downtime.",
          line_ids: ["L3", "L4"],
        },
      ],
    },
    {
      requirement_id: "R5",
      kind: "must",
      risk: "proved",
      line_ids: ["L6"],
      claims: [
        {
          source: "bullet",
          text: "Led a team of 4 engineers and owned the on-call rotation for settlement.",
          line_ids: ["L6"],
        },
        {
          source: "letter",
          text: "I ran those settlement workers on Kubernetes across two regions and led a team of four engineers through the on-call rotation that kept them up.",
          line_ids: ["L5", "L6"],
        },
      ],
    },
    {
      requirement_id: "R7",
      kind: "nice",
      risk: "proved",
      line_ids: ["L3", "L7"],
      claims: [
        {
          source: "bullet",
          text: "Built and ran production payment reconciliation services in Go serving 1,200 merchant accounts.",
          line_ids: ["L3"],
        },
        {
          source: "letter",
          text: "At Acme Payments I built the reconciliation services in Go that handled 1,200 merchant accounts, and I migrated the reporting pipeline to PostgreSQL without downtime.",
          line_ids: ["L3", "L4"],
        },
      ],
    },
  ],
  loose_claims: [
    {
      source: "letter",
      text: "I would be glad to talk about how that experience maps onto what you are building. Thank you for your time.",
      line_ids: [],
    },
  ],
};

export const EXAMPLE_POSTING = `Senior Backend Engineer — Northwind Ledger (Remote, EU)

Requirements
- 5+ years of backend engineering experience
- Strong production experience with Go
- Experience running services on Kubernetes
- Working knowledge of PostgreSQL and schema migrations
- Experience leading a small team
- Production experience with Kafka or a similar event bus

Nice to have
- Payments or fintech domain experience
- Familiarity with Terraform`;
