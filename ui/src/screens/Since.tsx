/**
 * Since you applied.
 *
 * The app is honest right up to the moment an application is sent, and then
 * it goes quiet about that application forever — while three of its own
 * screens keep growing the CV underneath it. Someone applies to a posting
 * that wanted Kafka, comes back a week later and writes the sentence about
 * the Kafka consumer they actually rewrote, and nothing anywhere connects
 * that sentence to the five applications it would have changed. The evidence
 * arrived after the envelope.
 *
 * Only this app can join those two records: it stores the per-requirement
 * verdict for every application, and the date on every line the user has
 * written into their CV. **No model, no tokens** — dates and a lexicon
 * lookup over records that already exist.
 *
 * The care is all in one word. The screen says the CV now **names** the
 * thing, never that it proves it: proving is the match's job, a model call
 * with a verifier behind it, and a lexicon hit between two strings is a
 * reason to run that again rather than a verdict. Every sentence of copy here
 * is written to keep that distinction, because the honest version of this
 * screen is also the useful one — it ends in a new match.
 */

import { useEffect } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { StatusLabel } from "../components/StatusLabel";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  activeCv,
  currentMatch,
  dismissError,
  error,
  reRunPosting,
  runSince,
  sincePhase,
  sinceResult,
} from "../state";
import type { CvLine, LineId, Requirement, SinceAnswer } from "../lib/types";
import "./Since.css";

export function Since() {
  const report = sinceResult.value;
  const phase = sincePhase.value;
  const match = currentMatch.value;
  const doc = activeCv();

  useEffect(() => {
    if (match && doc && phase === "idle") void runSince();
  }, [match?.id, doc?.hash, phase]);

  if (!match || !doc) {
    return (
      <Screen heading={t("since.heading")}>
        <EmptyState
          text={t("since.noMatch")}
          action={
            <button type="button" class="button" onClick={() => navigate("/matches")}>
              {t("nav.matches")}
            </button>
          }
        />
      </Screen>
    );
  }

  const requirements = new Map(match.requirements.map((item) => [item.id, item]));
  const lines = new Map(doc.lines.map((line) => [line.id, line]));
  const role = match.posting.title ?? t("tracker.untitledRole");
  const answers = report?.answers ?? [];
  const added = report?.added.length ?? 0;

  return (
    <Screen heading={t("since.heading")} lede={t("since.body", { role })}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runSince()} onDismiss={dismissError} />
      )}

      {phase === "running" && !report && (
        <p class="muted" aria-live="polite">
          {t("since.running")}
        </p>
      )}

      {/* Which clock it counted on is part of the sentence. A row that never
          recorded the day it was sent cannot be told it was sent nine days
          ago, so it is told what it does know. */}
      {report?.days !== null && report !== null && (
        <p class="since__age" aria-live="polite">
          {ageSentence(report.dated_from, report.days ?? 0)}
        </p>
      )}

      {report && answers.length === 0 && (
        <EmptyState
          text={added > 0 ? t("since.nothingRelevant", { count: added }) : t("since.nothing")}
          action={
            <button type="button" class="button button--secondary" onClick={() => navigate("/matches")}>
              {t("since.backToMatches")}
            </button>
          }
        />
      )}

      {answers.length > 0 && (
        <section class="stack stack--tight since__section">
          <h2>{t("since.worthHeading")}</h2>
          {/* The one paragraph that has to be exactly right: what the app
              knows is that the same term appears in both. What it proves is
              the next match's answer, not this screen's. */}
          <p class="muted since__lede">{t("since.worthBody")}</p>
          <ul class="list">
            {answers.map((answer) => (
              <Answer
                key={answer.requirement_id}
                answer={answer}
                requirement={requirements.get(answer.requirement_id)}
                lines={lines}
              />
            ))}
          </ul>

          <div class="row since__actions">
            {/* The posting text is not kept — storing the employer's words
                for months is not this app's to do — so this hands the user
                the new-match screen with the URL it does have. */}
            <button type="button" class="button" onClick={reRunPosting}>
              {t("since.runAgain")}
            </button>
            <button
              type="button"
              class="button button--quiet"
              onClick={() => navigate(`/match/${match.id}`)}
            >
              {t("since.backToMatch")}
            </button>
          </div>
          <p class="small muted since__note">
            {match.posting.url ? t("since.runAgainUrl") : t("since.runAgainPaste")}
          </p>
        </section>
      )}
    </Screen>
  );
}

/**
 * How old this application is, counted on the clock the record actually has.
 *
 * "1 days ago" is the kind of seam that makes a person stop trusting the
 * numbers around it, so one day gets its own sentence — and so does today,
 * where the honest thing to say about a row that has only ever been *run* is
 * how to make the better clock available.
 */
function ageSentence(from: "sent" | "checked", days: number): string {
  // Spelled out rather than composed: `tests/ui/i18n.spec.ts` fails a key
  // nothing in the source looks up, and that guard is worth more than six
  // saved lines.
  if (from === "sent") {
    if (days === 0) return t("since.sentToday");
    if (days === 1) return t("since.sentDay");
    return t("since.sentDays", { count: days });
  }
  if (days === 0) return t("since.checkedToday");
  if (days === 1) return t("since.checkedDay");
  return t("since.checkedDays", { count: days });
}

interface AnswerProps {
  answer: SinceAnswer;
  requirement: Requirement | undefined;
  lines: Map<LineId, CvLine>;
}

function Answer({ answer, requirement, lines }: AnswerProps) {
  // A record written by an older version can name a requirement this match no
  // longer carries; the id is the honest fallback (`Interview.tsx`).
  const heading = requirement?.text ?? answer.requirement_id;
  const cited = answer.line_ids.map((id) => lines.get(id)).filter(isLine);

  return (
    <li class="since">
      <div class="since__head">
        <h3 class="since__requirement">{heading}</h3>
        {answer.kind === "must" && <span class="since__must small">{t("map.mustHave")}</span>}
      </div>

      {/* What it got when the application went out — the thing that has not
          changed yet, and will not until the match is run again. */}
      <p class="since__verdict">
        <StatusLabel status={answer.status} />
        {/* An annotation on the label, at the size the app annotates things
            with elsewhere ("Added by you", "Must have") — at body size it
            read as a second, unrelated fragment. */}
        <span class="small muted">{t("since.whenSent")}</span>
      </p>

      {cited.length > 0 && (
        <ul class="stack stack--tight since__lines">
          {cited.map((line) => (
            <li key={line.id} class="since__line">
              <p class="since__quote">{line.text}</p>
              <div class="row since__chips">
                <SourceChip line={line.id} />
                <span class="small muted">{t("cv.preview.addedByYou")}</span>
              </div>
            </li>
          ))}
        </ul>
      )}

      {answer.terms.length > 0 && (
        <p class="since__terms">{t("since.names", { list: answer.terms.join(", ") })}</p>
      )}
    </li>
  );
}

function isLine(line: CvLine | undefined): line is CvLine {
  return line !== undefined;
}
