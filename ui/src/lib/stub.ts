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
  EXAMPLE_AUDIT,
  EXAMPLE_BRIEF,
  EXAMPLE_CV,
  EXAMPLE_GAPS,
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
  let matchCounter = 0;

  function engine(args: EngineArgs): unknown {
    switch (args.action) {
      case "health":
        return ok({ healthy: true, version: "preview", sampling: false, tool_id: "stub" });

      case "forget":
        uploads.clear();
        return ok({ uploads_dropped: 0, cached_postings_dropped: 0 });

      case "discard_upload":
        return ok({ dropped: uploads.delete(String(args.upload_id ?? "")) });

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
        // The recorded example's content, but a fresh identity: stamped with
        // the hash of the CV that was actually passed, and with an id of its
        // own. Production ties a match to one CV and gives every run its own
        // record — a preview that reuses the example's id sends the tracker
        // row back to the read-only example instead of the user's match, and
        // hides every bug those two ties exist to catch.
        return ok({
          ...EXAMPLE_MATCH,
          id: mintMatchId(),
          created_at: new Date().toISOString(),
          posting: { ...EXAMPLE_MATCH.posting, ...postingMeta(String(args.posting_text ?? "")) },
          cv_hash: hashOf(args.cv) ?? EXAMPLE_MATCH.cv_hash,
          // The one place the recorded verdicts bend to the CV in front of
          // them: a requirement the example leaves unproved, answered by a
          // line the user typed into Vouch themselves, comes back with
          // that line cited. Without it the whole loop this product is built
          // on — answer the gap, run it again, watch it close — is invisible
          // in preview mode, which is where the app is reviewed before any
          // real job search reaches it. It is not a pretend analysis: it
          // reflects a sentence the user actually wrote, and only ever
          // upgrades a verdict the example already admitted it could not
          // support.
          ...withAnswers(args.cv, EXAMPLE_MATCH),
        });

      case "tailor":
        if (!samePairing(args)) return fail("invalid_args", "match belongs to another CV");
        return ok({ ...EXAMPLE_TAILOR, match_id: matchIdOf(args) });

      case "recurring_gaps":
        return ok(groupByWording(args.items));

      case "compare_postings":
        return ok(compareByWording(args.items));

      case "audit_cv":
        // The real audit is set arithmetic the stub cannot do without the
        // lexicon, so preview mode shows the recorded one — stamped with the
        // hash of whatever CV was actually passed, the way `run_match` is.
        return ok({ ...EXAMPLE_AUDIT, cv_hash: hashOf(args.cv) ?? EXAMPLE_AUDIT.cv_hash });

      case "answer_question": {
        // The stub has no model, so it does the one thing it honestly can:
        // it looks for a CV line that shares a distinctive word with the
        // question and quotes it back, and otherwise says there is no
        // evidence. It never invents a sentence — a preview of this screen
        // that made something up would be demonstrating the opposite of the
        // feature.
        const asked = (args.questions as unknown[] | undefined) ?? [];
        if (!Array.isArray(asked) || asked.length === 0) {
          return fail("invalid_args", "answer_question needs a questions list");
        }
        const withMatch = (args.match as { id?: unknown } | null)?.id;
        return ok(
          crudeAnswers(
            args.cv,
            asked.map(String),
            typeof withMatch === "string" ? withMatch : null,
          ),
        );
      }

      case "check_document": {
        // The one screen the stub must answer *about the text in front of the
        // user*: a recorded result would quote sentences they never typed,
        // which on this screen is the whole thing being wrong. So the rule is
        // real but crude — numbers and capitalised words the CV does not
        // contain — because the lexicon, the unit arithmetic and the Turkish
        // folding all live in the engine. Preview flags less than production;
        // it never flags something production would call clean.
        const doc = String(args.document ?? "");
        if (!doc.trim()) return fail("invalid_args", "check_document needs a document");
        return ok(crudeCheck(args.cv, doc));
      }

      case "worth_rerunning":
        // Dates are arithmetic the stub does properly; the term match is the
        // same crude capitalised-word rule it uses everywhere, because the
        // lexicon lives in the engine. It finds fewer applications than
        // production and never one production would leave alone.
        return ok(crudeWorth(args.cv, args.items));

      case "compare_runs":
        // Comparing two verdicts is arithmetic the stub can do honestly; what
        // it cannot do is decide that two runs worded the same demand
        // differently, which is the lexicon's job. So preview mode pairs on
        // the exact wording and leaves the rest in `differed` — it finds
        // fewer gains than production and never invents one.
        return ok(crudeDiff(args.cv, args.before, args.match));

      case "profile": {
        // Built from the CV that was actually passed rather than recorded:
        // a canned headline would describe somebody else's career, which is
        // the one thing this screen must never do. The stub keeps the
        // paragraphs honest and leaves the headline to the real model — an
        // empty headline is a state the screen is built for.
        const lines = (((args.cv as { lines?: unknown[] } | null)?.lines ?? []) as {
          id: string;
          text?: string;
          section?: string;
        }[]).filter((line) => {
          if (line.section !== "experience") return false;
          // Only a line that already reads as something the person *did*. A
          // job header ("Acme Payments — Backend Engineer, 2018–2024") turns
          // into nonsense the moment an "I" is put in front of it, and a
          // preview that prints nonsense reads as a broken feature.
          const first = String(line.text ?? "").split(/\s+/)[0]?.toLowerCase() ?? "";
          return first.endsWith("ed") || ["built", "led", "ran", "owned", "wrote"].includes(first);
        });
        return ok({
          version: 1,
          cv_hash: hashOf(args.cv) ?? "",
          headline: "",
          headline_line_ids: [],
          about: lines.slice(0, 2).map((line) => ({
            text: `I ${String(line.text ?? "").replace(/^[A-ZÇĞİÖŞÜ]/, (c) => c.toLowerCase())}`,
            line_ids: [line.id],
          })),
        });
      }

      case "followup": {
        // The refusal is the feature, so preview mode has to be able to
        // reach it: a CV with nothing written since the application went out
        // gets the same "nothing to send" it would get in production. The
        // note itself is assembled from the user's own new line rather than
        // recorded, because a canned follow-up would quote a sentence they
        // never wrote.
        const since = crudeSince(args.cv, args.match, args.sent_at) as {
          days: number | null;
          dated_from: string;
          answers: { line_ids: string[]; terms: string[] }[];
        };
        const lineIds = [...new Set(since.answers.flatMap((answer) => answer.line_ids))];
        const terms = [...new Set(since.answers.flatMap((answer) => answer.terms))];
        const lines = (((args.cv as { lines?: unknown[] } | null)?.lines ?? []) as {
          id: string;
          text?: string;
        }[]).filter((line) => lineIds.includes(line.id));
        if (lines.length === 0) {
          return ok({
            version: 1,
            match_id: matchIdOf(args),
            kind: "nothing_new",
            days: since.days,
            dated_from: since.dated_from,
            paragraphs: [],
            placeholders: [],
            line_ids: [],
            terms: [],
          });
        }
        return ok({
          version: 1,
          match_id: matchIdOf(args),
          kind: "new_evidence",
          days: since.days,
          dated_from: since.dated_from,
          paragraphs: [
            {
              text: "I am following up on my application for the [Role] role.",
              line_ids: [],
            },
            ...lines.map((line) => ({
              // "Since I applied, I owned…" — the pronoun matters: a real
              // model writes prose, and a preview that reads like a broken
              // sentence makes the feature look broken.
              text: `Since I applied, I ${String(line.text ?? "").replace(/^[A-ZÇĞİÖŞÜ]/, (c) => c.toLowerCase())}`,
              line_ids: [line.id],
            })),
            { text: "Happy to talk it through, [Hiring Manager].", line_ids: [] },
          ],
          placeholders: ["[Hiring Manager]"],
          line_ids: lineIds.slice(0, 3),
          terms: terms.slice(0, 5),
        });
      }

      case "since_applied":
        // The dates are real arithmetic and the stub does them properly; what
        // it cannot do is the lexicon, so the term match is crude — a word
        // the requirement and the new line share, capitalised in both. It
        // finds less than production does and never finds what production
        // would call a coincidence, which is the right way round.
        return ok(crudeSince(args.cv, args.match, args.sent_at));

      case "line_ledger":
        // Counting *is* the feature, and the stub can count: what it cannot
        // do is decide that two postings worded the same demand differently,
        // which is lexicon work. So preview mode answers with real tallies of
        // whatever feed it was handed, and merges nothing.
        return ok(tallyLines(args.cv, args.items));

      case "interview_brief": {
        // Like `audit_cv`: the real brief reads sections and `added_at` off
        // the parsed CV, so preview mode shows the recorded one — stamped
        // with the hash of whatever CV was actually passed.
        //
        // The corrections are the exception, and they have to be applied for
        // real: a preview that showed a user's own claim as a receipt would
        // be demonstrating the one thing this feature exists to prevent.
        const asserted = new Map(
          ((args.assertions as { requirement_id?: unknown; line_ids?: unknown }[] | undefined) ?? [])
            .filter((item) => typeof item.requirement_id === "string")
            .map((item) => [
              String(item.requirement_id),
              (Array.isArray(item.line_ids) ? item.line_ids : []).map(String),
            ]),
        );
        const withClaims = (items: typeof EXAMPLE_BRIEF.risks) =>
          items.map((item) =>
            asserted.has(item.requirement_id)
              ? {
                  ...item,
                  risk: "self_asserted" as const,
                  line_ids: asserted.get(item.requirement_id)!,
                }
              : item,
          );
        const risks = withClaims(EXAMPLE_BRIEF.risks);
        const proved = withClaims(EXAMPLE_BRIEF.proved);
        return ok({
          ...EXAMPLE_BRIEF,
          match_id: matchIdOf(args),
          cv_hash: hashOf(args.cv) ?? EXAMPLE_BRIEF.cv_hash,
          // The one thing the stub can answer for real, and the one the
          // screen would otherwise get silently wrong after a gap answer.
          cv_changed: !samePairing(args),
          // A correction is never a receipt, so it moves sides if it has to.
          risks: [...risks, ...proved.filter((item) => item.risk === "self_asserted")],
          proved: proved.filter((item) => item.risk !== "self_asserted"),
        });
      }

      case "gaps":
        if (!samePairing(args)) return fail("invalid_args", "match belongs to another CV");
        return ok({ ...EXAMPLE_GAPS, match_id: matchIdOf(args) });

      case "letter":
        if (!samePairing(args)) return fail("invalid_args", "match belongs to another CV");
        return ok({ ...EXAMPLE_LETTER, match_id: matchIdOf(args), tone: args.tone ?? "plain" });

      case "export_cv": {
        // The real one renders python-docx bytes; the stub answers the shape
        // and the count, which is what the screen shows. A preview download
        // still fails at `files.download`, the same as `export_docx`.
        const lines = ((args.cv as { lines?: unknown[] } | null)?.lines ?? []) as {
          added_at?: string;
        }[];
        const wanted = args.mode === "additions" ? lines.filter((line) => line.added_at) : lines;
        if (wanted.length === 0) return fail("invalid_args", "nothing to export");
        return ok({
          filename: args.mode === "additions" ? "cv-additions-preview.docx" : "cv-preview.docx",
          content_b64: "",
          mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          lines: wanted.length,
        });
      }

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

  /**
   * A title and a company read off the posting's own first line.
   *
   * The verdicts stay the recorded example's — the stub has no model — but the
   * heading should say which posting was pasted. Three preview matches that
   * all read "Senior Backend Engineer — Northwind Ledger" make every screen
   * that lists applications look broken, and the comparison screen unreadable.
   */
  function postingMeta(text: string): { title?: string; company?: string } {
    const headline = text
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line.length > 0);
    if (!headline) return {};
    const [title, rest] = headline.split(/\s+[—–-]\s+/, 2);
    const company = rest?.replace(/\s*\(.*$/, "").trim();
    return {
      ...(title ? { title: title.trim().slice(0, 120) } : {}),
      ...(company ? { company: company.slice(0, 120) } : {}),
    };
  }

  /** Words too common to mean a question is about a particular CV line. */
  const COMMON = new Set([
    "about", "and", "any", "are", "can", "describe", "did", "does", "experience",
    "for", "have", "how", "into", "job", "made", "many", "most", "much",
    "own", "role", "tell", "that", "the", "their", "them", "there", "this",
    "time", "told", "under", "use", "used", "want", "was", "were", "what",
    "when", "where", "which", "who", "why", "will", "with", "work", "worked",
    "you", "your", "yourself",
  ]);

  /** Questions that ask what someone wants rather than what they did. */
  const WANTING = /\b(why|excites?|motivat|passion|interest|culture|values?|see yourself|weakness|goals?)\b/i;

  /**
   * Preview answers: the candidate's own CV lines, or nothing at all.
   *
   * Quoting a line back is not what production does — production writes a
   * sentence and verifies it — but it is the only thing a stub can do without
   * inventing, and inventing is the one mistake this screen must never
   * demonstrate.
   */
  function crudeAnswers(cv: unknown, questions: string[], matchId: string | null): unknown {
    // Skills lists and the header are excluded, the same sections `audit.py`
    // refuses to count as evidence: "Kubernetes" appearing in a comma list is
    // the thing this product tells people an interviewer will not accept, and
    // a preview that answered with it would demonstrate the opposite of the
    // feature.
    const lines = ((cv as { lines?: { id?: unknown; text?: unknown; section?: unknown }[] } | null)
      ?.lines ?? [])
      .filter((line) => line.section !== "skills" && line.section !== "header")
      .map((line) => ({ id: String(line.id ?? ""), text: String(line.text ?? "") }));

    const items = questions.slice(0, 5).map((question) => {
      if (WANTING.test(question)) {
        return { question, kind: "not_about_you", sentences: [], dropped: 0 };
      }
      const wanted = new Set(
        (question.toLowerCase().match(/[\p{L}\p{N}+#.]{3,}/gu) ?? []).filter(
          (word) => !COMMON.has(word),
        ),
      );
      const hits = lines.filter((line) =>
        (line.text.toLowerCase().match(/[\p{L}\p{N}+#.]{3,}/gu) ?? []).some((word) =>
          wanted.has(word),
        ),
      );
      if (hits.length === 0) {
        return { question, kind: "no_evidence", sentences: [], dropped: 0 };
      }
      return {
        question,
        kind: "answered",
        sentences: hits.slice(0, 3).map((line) => ({ text: line.text, line_ids: [line.id] })),
        dropped: 0,
      };
    });

    return { version: 1, match_id: matchId, items };
  }

  /**
   * A stand-in for `verify/grounding.py`, good enough to review the screen.
   *
   * Deliberately narrow: a number the CV does not state, or a capitalised word
   * it never uses. That is a subset of the real rule, so the preview is quiet
   * where production would speak — the safe direction for a stub to be wrong
   * in, on a screen whose job is to say "you cannot back this".
   */
  function crudeCheck(cv: unknown, document: string): unknown {
    const lines = ((cv as { lines?: { text?: unknown }[] } | null)?.lines ?? []).map((line) =>
      String(line.text ?? ""),
    );
    const source = lines.join(" ").toLowerCase();
    const known = new Set(source.match(/[\p{L}\p{N}%+#.]+/gu) ?? []);

    const units = document
      .split("\n")
      .flatMap((line) => line.trim().split(/(?<=[.!?])\s+(?=\p{L})/u))
      .map((unit) => unit.trim())
      .filter((unit) => unit.length > 0);

    const flagged: unknown[] = [];
    let unbacked = 0;
    units.forEach((unit, index) => {
      const claims: { kind: string; surface: string }[] = [];
      for (const hit of unit.match(/\d+(?:[.,]\d+)?%?/g) ?? []) {
        if (!known.has(hit.toLowerCase())) claims.push({ kind: "number", surface: hit });
      }
      for (const hit of unit.matchAll(/\b\p{Lu}[\p{L}.+#-]{2,}/gu)) {
        const word = hit[0];
        // A capitalised word that only opens the sentence is grammar, not a
        // claim — the engine's rule, kept here because a preview that
        // bracketed "Cut" in "Cut latency by 40%" would teach a reviewer to
        // distrust the brackets that matter. An acronym still counts.
        const internallyCapitalised = /\p{Lu}/u.test(word.slice(1));
        if (hit.index === 0 && !internallyCapitalised) continue;
        const bare = word.replace(/[.,;:]+$/, "");
        if (!known.has(bare.toLowerCase()) && !known.has(`${bare.toLowerCase()}.`)) {
          claims.push({ kind: "proper_noun", surface: bare });
        }
      }
      const distinct = claims.filter(
        (claim, at) => claims.findIndex((other) => other.surface === claim.surface) === at,
      );
      if (distinct.length === 0) return;
      unbacked += 1;
      if (flagged.length < 40) {
        flagged.push({ index, text: unit.slice(0, 400), claims: distinct.slice(0, 6) });
      }
    });

    return {
      version: 1,
      cv_hash: hashOf(cv) ?? "preview",
      checked: units.length,
      unbacked,
      flagged,
      truncated: false,
      masked: [],
    };
  }

  /**
   * The example's verdicts, with any gap the user has since answered closed.
   *
   * Preview mode cannot analyse anything — there is no model behind it — so
   * every run returns the recorded match. That made one thing impossible to
   * show: the moment a sentence the user wrote turns a "no evidence yet" into
   * a receipt. This closes exactly the gaps the user's own added lines name,
   * by the crude word match the stub uses everywhere, and touches nothing
   * else: a proved requirement stays proved and an unanswered gap stays open.
   */
  function withAnswers(cv: unknown, example: typeof EXAMPLE_MATCH) {
    const evidence = answeredByTheUser(cv, example);
    if (evidence === example.evidence) return { evidence };
    // The counts go with the verdicts. A summary left behind would put "6 of
    // 8 have evidence" above a map showing seven, which is the kind of quiet
    // disagreement the whole app exists to not have.
    const must = new Set(
      example.requirements.filter((item) => item.kind === "must").map((item) => item.id),
    );
    const strong = evidence.filter((item) => item.status === "strong").length;
    const partial = evidence.filter((item) => item.status === "partial").length;
    const missing = evidence.filter((item) => item.status === "missing");
    return {
      evidence,
      summary: {
        ...example.summary,
        strong,
        partial,
        missing: missing.length,
        must_missing: missing.filter((item) => must.has(item.requirement_id)).length,
      },
    };
  }

  function answeredByTheUser(cv: unknown, example: typeof EXAMPLE_MATCH) {
    const lines = (((cv ?? {}) as { lines?: unknown[] }).lines ?? []) as {
      id: string;
      text?: string;
      added_at?: string;
    }[];
    const written = lines.filter((line) => line.added_at);
    if (written.length === 0) return example.evidence;

    const words = (text: string) =>
      new Set(
        text
          .split(/\s+/)
          .slice(1)
          .map((word) => word.replace(/[^\p{L}\p{N}+#.]/gu, ""))
          .filter((word) => word.length > 2 && word[0] === word[0]?.toUpperCase()),
      );
    const requirements = new Map(example.requirements.map((item) => [item.id, item]));

    return example.evidence.map((item) => {
      if (item.status === "strong") return item;
      const wanted = words(requirements.get(item.requirement_id)?.text ?? "");
      const answer = written.find((line) =>
        [...words(String(line.text ?? ""))].some((word) => wanted.has(word)),
      );
      return answer
        ? { ...item, status: "strong" as const, line_ids: [answer.id], why: item.why }
        : item;
    });
  }

  function hashOf(value: unknown): string | null {
    const hash = (value as { hash?: unknown } | null)?.hash;
    return typeof hash === "string" && hash ? hash : null;
  }

  /** The engine's `_assert_same_cv`, enforced here for the same reason. */
  /** A fresh id per run, so preview matches behave like real ones. */
  function mintMatchId(): string {
    matchCounter += 1;
    return `preview-${matchCounter}-${Date.now().toString(36)}`;
  }

  function matchIdOf(args: EngineArgs): string {
    const id = (args.match as { id?: unknown } | null)?.id;
    return typeof id === "string" ? id : EXAMPLE_TAILOR.match_id;
  }

  function samePairing(args: EngineArgs): boolean {
    const cvHash = hashOf(args.cv);
    const matchHash = (args.match as { cv_hash?: unknown } | null)?.cv_hash;
    if (!cvHash || typeof matchHash !== "string") return true;
    return cvHash === matchHash;
  }

  /**
   * Group past requirements by their exact wording.
   *
   * The engine groups by lexicon term, so "Kafka in production" and "Event
   * streaming with Kafka" land together; the stub has no lexicon and does not
   * pretend to — identical wordings only. That is weaker, and it is honest
   * about being weaker: every number it returns is a true count of the matches
   * the preview actually ran, which is what makes preview mode a rehearsal
   * rather than a story.
   *
   * The two rules that matter are enforced here as well, because they are what
   * the screen's copy depends on: at least two applications, and unproven in
   * every one of them.
   */
  /**
   * Which lines carried which applications — counted for real.
   *
   * Unlike the audit and the brief, there is no recorded example to fall back
   * on: the answer is about the CV in front of the user and the applications
   * they have actually saved, so a canned one would put someone else's
   * receipts under their sentences. The rules that the screen's copy leans on
   * are the ones enforced here — three applications minimum, citations only
   * from a verdict that proved something, and nothing counted from a CV that
   * was parsed differently.
   */
  /**
   * What arrived after the envelope — counted for real, matched crudely.
   *
   * Like the ledger, there is no recorded example to fall back on: the answer
   * is about this CV and this application, and a canned one would tell
   * someone a sentence they never wrote has changed an application they never
   * sent. The rules the copy leans on are enforced here too — only lines
   * added *after* it went out, and only requirements the match left unproved.
   */
  /**
   * Two runs of one posting, lined up on their exact wording.
   *
   * No recorded example again: the answer is about two applications this user
   * actually ran, and a canned one would congratulate someone for closing a
   * gap they never had. The rule the screen's strongest sentence leans on is
   * enforced here as well — a gain is only credited when the newer run cites
   * a line written after the older run.
   */
  /**
   * Every saved application the CV has since gained an answer for.
   *
   * No recorded example, for the same reason as the ledger and the diff: the
   * answer is about this user's own applications and their own sentences. The
   * rule the screen leans on is enforced here as well — only a line written
   * *after* an application went out can make it worth reopening.
   */
  function crudeWorth(cv: unknown, items: unknown): unknown {
    const doc = (cv ?? {}) as { lines?: { id: string; text?: string; added_at?: string }[] };
    const at = (value: unknown) => {
      const parsed = Date.parse(String(value ?? ""));
      return Number.isNaN(parsed) ? null : parsed;
    };
    const written = (doc.lines ?? []).filter((line) => line.added_at);
    const rows = (Array.isArray(items) ? items : []) as {
      match?: string;
      text?: string;
      kind?: string;
      status?: string;
      created_at?: string;
    }[];

    const terms = (text: string) =>
      new Set(
        text
          .split(/\s+/)
          .slice(1)
          .map((word) => word.replace(/[^\p{L}\p{N}+#.]/gu, ""))
          .filter((word) => word.length > 2 && word[0] === word[0]?.toUpperCase()),
      );

    interface Row {
      unproved: number;
      requirements: number;
      must: number;
      terms: string[];
      line_ids: string[];
      texts: string[];
    }
    const seen: string[] = [];
    const found = new Map<string, Row>();

    for (const row of rows) {
      const id = String(row.match ?? "");
      if (!id) continue;
      if (!found.has(id)) {
        seen.push(id);
        found.set(id, { unproved: 0, requirements: 0, must: 0, terms: [], line_ids: [], texts: [] });
      }
      const entry = found.get(id);
      if (!entry || row.status === "strong") continue;
      entry.unproved += 1;

      const boundary = at(row.created_at);
      if (boundary === null) continue;
      const candidates = written.filter((line) => (at(line.added_at) ?? 0) > boundary);
      const wanted = terms(String(row.text ?? ""));
      let named = false;
      for (const line of candidates) {
        const shared = [...terms(String(line.text ?? ""))].filter((word) => wanted.has(word));
        if (shared.length === 0) continue;
        named = true;
        if (!entry.line_ids.includes(line.id)) entry.line_ids.push(line.id);
        for (const word of shared) if (!entry.terms.includes(word)) entry.terms.push(word);
      }
      if (!named) continue;
      entry.requirements += 1;
      if (row.kind === "must") entry.must += 1;
      const wording = String(row.text ?? "");
      if (wording && !entry.texts.includes(wording)) entry.texts.push(wording);
    }

    const worth = seen
      .map((match) => ({ match, ...(found.get(match) as Row) }))
      .filter((row) => row.requirements > 0)
      .map((row) => ({
        ...row,
        terms: row.terms.slice(0, 5),
        line_ids: row.line_ids.slice(0, 3),
        texts: row.texts.slice(0, 3),
      }))
      .sort((a, b) => b.must - a.must || b.requirements - a.requirements);

    return {
      version: 1,
      applications: seen.length,
      written: written.length,
      items: worth.slice(0, 10),
    };
  }

  function crudeDiff(cv: unknown, before: unknown, after: unknown): unknown {
    const doc = (cv ?? {}) as { lines?: { id: string; added_at?: string }[] };
    const at = (value: unknown) => {
      const parsed = Date.parse(String(value ?? ""));
      return Number.isNaN(parsed) ? null : parsed;
    };
    type Run = {
      id?: string;
      created_at?: string;
      requirements?: { id: string; text?: string; kind?: string }[];
      evidence?: { requirement_id: string; status?: string; line_ids?: string[] }[];
      summary?: { strong?: number; total?: number };
    };
    const older = (before ?? {}) as Run;
    const newer = (after ?? {}) as Run;
    // A function rather than a lookup: an unknown verdict reads as the
    // weakest one, which is how silence is read everywhere else in this app.
    const rank = (status: string): number => (status === "strong" ? 2 : status === "partial" ? 1 : 0);

    const sides = (run: Run) => {
      const verdicts = new Map((run.evidence ?? []).map((item) => [item.requirement_id, item]));
      const out = new Map<string, { surface: string; kind: string; status: string; lines: string[] }>();
      for (const requirement of run.requirements ?? []) {
        const key = String(requirement.text ?? "").trim().toLowerCase();
        if (!key) continue;
        const found = verdicts.get(requirement.id);
        const status = found?.status ?? "missing";
        const side = out.get(key) ?? {
          surface: String(requirement.text ?? ""),
          kind: "nice",
          status: "missing",
          lines: [] as string[],
        };
        if (requirement.kind === "must") side.kind = "must";
        if (rank(status) >= rank(side.status)) side.status = status;
        for (const id of found?.line_ids ?? []) if (!side.lines.includes(id)) side.lines.push(id);
        out.set(key, side);
      }
      return out;
    };

    const boundary = at(older.created_at);
    const earned = new Set(
      (doc.lines ?? [])
        .filter((line) => line.added_at && boundary !== null && (at(line.added_at) ?? 0) > boundary)
        .map((line) => line.id),
    );

    const first = sides(older);
    const second = sides(newer);
    const gained = [];
    const lost = [];
    const still = [];
    const differed = [];

    for (const key of new Set([...first.keys(), ...second.keys()])) {
      const old = first.get(key);
      const now = second.get(key);
      const side = now ?? old;
      if (!side) continue;
      const row = {
        key,
        surface: side.surface,
        kind: side.kind,
        before: old?.status ?? null,
        after: now?.status ?? null,
        direction: "same",
        line_ids: now ? now.lines.slice(0, 5) : [],
        credited: false,
        texts: [side.surface],
      };
      if (!old || !now) {
        differed.push({ ...row, direction: now ? "new_ask" : "dropped_ask" });
      } else if (rank(now.status) > rank(old.status)) {
        gained.push({
          ...row,
          direction: "gained",
          credited: now.lines.some((id) => earned.has(id)),
        });
      } else if (rank(now.status) < rank(old.status)) {
        lost.push({ ...row, direction: "lost" });
      } else if (now.status !== "strong") {
        still.push(row);
      }
    }

    const days =
      boundary === null || at(newer.created_at) === null
        ? null
        : Math.max(0, Math.floor(((at(newer.created_at) ?? 0) - boundary) / 86_400_000));

    return {
      version: 1,
      before_id: older.id ?? "",
      after_id: newer.id ?? "",
      days_between: days,
      before_strong: older.summary?.strong ?? 0,
      before_total: older.summary?.total ?? 0,
      after_strong: newer.summary?.strong ?? 0,
      after_total: newer.summary?.total ?? 0,
      added_between: [...earned],
      gained: gained.slice(0, 12),
      lost: lost.slice(0, 12),
      still: still.slice(0, 12),
      differed: differed.slice(0, 12),
    };
  }

  function crudeSince(cv: unknown, match: unknown, sentAt: unknown): unknown {
    const doc = (cv ?? {}) as { hash?: string; lines?: { id: string; text?: string; added_at?: string }[] };
    const record = (match ?? {}) as {
      id?: string;
      created_at?: string;
      cv_hash?: string;
      requirements?: { id: string; text?: string; kind?: string }[];
      evidence?: { requirement_id: string; status?: string }[];
    };
    const at = (value: unknown) => {
      const parsed = Date.parse(String(value ?? ""));
      return Number.isNaN(parsed) ? null : parsed;
    };
    const reference = at(sentAt) ?? at(record.created_at);
    const added = (doc.lines ?? []).filter(
      (line) => line.added_at && reference !== null && (at(line.added_at) ?? 0) > reference,
    );
    const verdict = new Map(
      (record.evidence ?? []).map((item) => [item.requirement_id, item.status]),
    );
    // Capitalised words that are not the start of the sentence: the crude
    // stand-in for "a term the lexicon knows".
    const terms = (text: string) =>
      new Set(
        text
          .split(/\s+/)
          .slice(1)
          .map((word) => word.replace(/[^\p{L}\p{N}+#.]/gu, ""))
          .filter((word) => word.length > 2 && word[0] === word[0]?.toUpperCase()),
      );

    const answers = [];
    for (const requirement of record.requirements ?? []) {
      if ((verdict.get(requirement.id) ?? "missing") === "strong") continue;
      const wanted = terms(String(requirement.text ?? ""));
      const hits: string[] = [];
      const shared = new Set<string>();
      for (const line of added) {
        const found = [...terms(String(line.text ?? ""))].filter((word) => wanted.has(word));
        if (found.length === 0) continue;
        hits.push(line.id);
        for (const word of found) shared.add(word);
      }
      if (hits.length > 0) {
        answers.push({
          requirement_id: requirement.id,
          kind: requirement.kind ?? "nice",
          status: verdict.get(requirement.id) ?? "missing",
          line_ids: hits.slice(0, 3),
          terms: [...shared].slice(0, 5),
        });
      }
    }
    answers.sort((a, b) => (a.kind === "must" ? 0 : 1) - (b.kind === "must" ? 0 : 1));

    const days =
      reference === null ? null : Math.max(0, Math.floor((Date.now() - reference) / 86_400_000));
    return {
      version: 1,
      match_id: record.id ?? "",
      days,
      dated_from: at(sentAt) === null ? "checked" : "sent",
      cv_changed: Boolean(doc.hash && record.cv_hash && doc.hash !== record.cv_hash),
      added: added.map((line) => line.id),
      answers: answers.slice(0, 8),
    };
  }

  function tallyLines(cv: unknown, items: unknown): unknown {
    const doc = (cv ?? {}) as { hash?: string; lines?: { id: string; section?: string; added_at?: string }[] };
    const base = (value: string) => value.replace(/~e\d+$/, "");
    const body = (doc.lines ?? []).filter((line) => line.section !== "header");
    const known = new Map(body.map((line) => [line.id, line]));
    const rows = (Array.isArray(items) ? items : []) as {
      match?: string;
      text?: string;
      kind?: string;
      status?: string;
      line_ids?: string[];
      cv_hash?: string;
    }[];

    const mine = rows.filter((row) => base(String(row.cv_hash ?? "")) === base(String(doc.hash ?? "")));
    const applications = new Set(mine.map((row) => row.match));
    const skipped = new Set(rows.map((row) => row.match)).size - applications.size;
    const empty = {
      version: 1,
      applications: applications.size,
      skipped,
      eligible: body.length,
      cited: 0,
      working: [],
      idle: [],
      added: [],
    };
    if (applications.size < 3) return empty;

    interface Tally {
      matches: Set<string>;
      citations: number;
      must: number;
      decisive: number;
      proves: string[];
    }
    const tallies = new Map<string, Tally>();
    for (const row of mine) {
      if (row.status === "missing") continue;
      const cited = [...new Set(row.line_ids ?? [])].filter((id) => known.has(id));
      for (const id of cited) {
        const tally: Tally = tallies.get(id) ?? {
          matches: new Set(),
          citations: 0,
          must: 0,
          decisive: 0,
          proves: [],
        };
        tally.matches.add(String(row.match));
        tally.citations += 1;
        if (row.kind === "must") {
          tally.must += 1;
          if (cited.length === 1) tally.decisive += 1;
        }
        const wording = String(row.text ?? "").trim();
        if (wording && !tally.proves.includes(wording)) tally.proves.push(wording);
        tallies.set(id, tally);
      }
    }

    const row = (id: string, tally: Tally | undefined) => ({
      id,
      applications: tally?.matches.size ?? 0,
      citations: tally?.citations ?? 0,
      must: tally?.must ?? 0,
      decisive: tally?.decisive ?? 0,
      proves: (tally?.proves ?? []).slice(0, 5),
      added: Boolean(known.get(id)?.added_at),
    });

    return {
      ...empty,
      cited: tallies.size,
      working: [...tallies.keys()]
        .map((id) => row(id, tallies.get(id)))
        .sort((a, b) => b.applications - a.applications || b.citations - a.citations)
        .slice(0, 12),
      idle: body.filter((line) => !tallies.has(line.id)).map((line) => row(line.id, undefined)).slice(0, 12),
      added: body
        .filter((line) => line.added_at)
        .map((line) => ({ ...row(line.id, tallies.get(line.id)), added: true }))
        .slice(0, 8),
    };
  }

  function groupByWording(items: unknown): unknown {
    const rows = Array.isArray(items) ? items : [];
    interface Bucket {
      surface: string;
      kind: string;
      ids: string[];
      asked: Set<string>;
      unproven: Set<string>;
      must: Set<string>;
    }
    const buckets = new Map<string, Bucket>();
    const seen = new Set<string>();

    for (const row of rows) {
      const { id, match, text, kind, status } = (row ?? {}) as {
        id?: string;
        match?: string;
        text?: string;
        kind?: string;
        status?: string;
      };
      if (!id || !match || !text) continue;
      seen.add(match);
      const key = text.trim().toLowerCase();
      const bucket: Bucket = buckets.get(key) ?? {
        surface: text.trim(),
        kind: "nice",
        ids: [],
        asked: new Set(),
        unproven: new Set(),
        must: new Set(),
      };
      bucket.ids.push(id);
      bucket.asked.add(match);
      if (kind === "must") {
        bucket.kind = "must";
        bucket.must.add(match);
      }
      if (status !== "strong") bucket.unproven.add(match);
      buckets.set(key, bucket);
    }

    const shape = (key: string, bucket: Bucket) => ({
      key,
      surface: bucket.surface,
      kind: bucket.kind,
      asked: bucket.asked.size,
      unproven: bucket.unproven.size,
      must: bucket.must.size,
      ids: bucket.ids,
      texts: [bucket.surface],
    });
    const rows2 = [...buckets.entries()].filter(([, b]) => b.asked.size > 1);

    return {
      version: 1,
      matches: seen.size,
      groups: seen.size < 3
        ? []
        : rows2
            .filter(([, b]) => b.unproven.size === b.asked.size)
            .map(([key, b]) => shape(key, b)),
      strengths: seen.size < 3
        ? []
        : rows2.filter(([, b]) => b.unproven.size === 0).map(([key, b]) => shape(key, b)),
    };
  }

  /**
   * Line up postings by their exact wording.
   *
   * The same shape `compare.py` returns and the same two rules — fewest
   * unproved must-haves first, and a shared row only when every posting agrees
   * — but with no lexicon, so "Kubernetes in production" and "Experience
   * running services on Kubernetes" stay apart here. Weaker, and honest about
   * being weaker: every count it returns is a true count of the matches the
   * preview actually ran.
   */
  function compareByWording(items: unknown): unknown {
    interface Row {
      id: string;
      match: string;
      text: string;
      kind: string;
      status: string;
    }
    interface Term {
      surface: string;
      kind: string;
      proved: boolean;
      ids: string[];
    }

    const rows = (Array.isArray(items) ? items : []) as Row[];
    const order: string[] = [];
    const byMatch = new Map<string, Row[]>();
    for (const row of rows) {
      if (!row?.match || !row.text) continue;
      let own = byMatch.get(row.match);
      if (!own) {
        // Past the cap the posting is dropped whole, the way the engine drops
        // it: half a posting's requirements would make its counts false.
        if (order.length >= 4) continue;
        own = [];
        order.push(row.match);
        byMatch.set(row.match, own);
      }
      own.push(row);
    }

    const empty = { version: 1, postings: order.length, columns: [], shared_gaps: [], shared_proved: [] };
    const first = order[0];
    if (order.length < 2 || first === undefined) return empty;

    const keyOf = (text: string) => text.trim().toLowerCase();
    const terms = new Map<string, Map<string, Term>>();
    for (const match of order) {
      const map = new Map<string, Term>();
      for (const row of byMatch.get(match) ?? []) {
        const key = keyOf(row.text);
        const term = map.get(key) ?? { surface: row.text.trim(), kind: "nice", proved: false, ids: [] };
        term.ids.push(row.id);
        if (row.kind === "must") term.kind = "must";
        if (row.status === "strong") term.proved = true;
        map.set(key, term);
      }
      terms.set(match, map);
    }
    const termsOf = (match: string): Map<string, Term> => terms.get(match) ?? new Map();

    const columns = order.map((match) => {
      const own = byMatch.get(match) ?? [];
      const musts = own.filter((row) => row.kind === "must");
      return {
        match,
        asked: own.length,
        proved: own.filter((row) => row.status === "strong").length,
        related: own.filter((row) => row.status === "partial").length,
        must_asked: musts.length,
        must_proved: musts.filter((row) => row.status === "strong").length,
        blockers: musts
          .filter((row) => row.status !== "strong")
          .map((row) => row.text.trim())
          .slice(0, 5),
        edge: [...termsOf(match).entries()]
          .filter(
            ([key, term]) =>
              term.proved && order.some((other) => other !== match && !termsOf(other).has(key)),
          )
          .map(([, term]) => term.surface)
          .slice(0, 5),
      };
    });
    columns.sort(
      (a, b) =>
        a.must_asked - a.must_proved - (b.must_asked - b.must_proved) ||
        b.must_proved - a.must_proved ||
        b.proved - a.proved ||
        order.indexOf(a.match) - order.indexOf(b.match),
    );

    const shared = (proved: boolean) =>
      [...termsOf(first).entries()]
        .filter(([key]) =>
          order.every((match) => termsOf(match).get(key)?.proved === proved),
        )
        .map(([key, term]) => ({
          key,
          surface: term.surface,
          kind: order.some((match) => termsOf(match).get(key)?.kind === "must") ? "must" : "nice",
          asked: order.length,
          unproven: proved ? 0 : order.length,
          must: order.filter((match) => termsOf(match).get(key)?.kind === "must").length,
          ids: order.flatMap((match) => termsOf(match).get(key)?.ids ?? []),
          texts: [term.surface],
        }))
        .slice(0, 6);

    return {
      version: 1,
      postings: order.length,
      columns,
      shared_gaps: shared(false),
      shared_proved: shared(true),
    };
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
