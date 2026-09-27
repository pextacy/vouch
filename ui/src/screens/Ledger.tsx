/**
 * Which lines do the work.
 *
 * Every other screen treats the CV as a source: the match cites it, the
 * tailor rewrites from it, the brief quotes it. None of them ever read it as
 * a record — which of these twenty-odd sentences has actually carried an
 * application, and which has sat on the page for two years without a single
 * posting needing it.
 *
 * No other tool in this category can answer that. They can tell you a bullet
 * is "weak" because a model says so; this one counts the times a line was
 * accepted as evidence, in applications the user can open and check. It is
 * the same argument the whole product rests on, turned on the document
 * itself.
 *
 * **No model, no tokens.** The counting is arithmetic over verdicts the
 * verifier already made, which is why the screen can be re-read for free
 * whenever the CV moves.
 *
 * The second list is the one that needs care. "Never asked for" is not "cut
 * this", and the copy says so out loud: a line goes uncited when the jobs
 * this person applied to never asked about that work, which is a fact about
 * the postings they picked, not about the work they did. The app sorts; it
 * does not judge.
 */

import { useEffect } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { navigate } from "../router";
import { MIN_MATCHES } from "../lib/ledger";
import {
  activeCv,
  dismissError,
  error,
  hasCv,
  ledgerPhase,
  ledgerResult,
  runLedger,
  tracker,
} from "../state";
import type { CvLine, LedgerLine, LineId } from "../lib/types";
import "./Ledger.css";

export function Ledger() {
  const report = ledgerResult.value;
  const phase = ledgerPhase.value;
  const doc = activeCv();

  useEffect(() => {
    if (doc && phase === "idle") void runLedger();
  }, [doc?.hash, phase]);

  if (!hasCv.value || !doc) {
    navigate("/cv/add");
    return null;
  }

  const lines = new Map(doc.lines.map((line) => [line.id, line]));
  const applications = report?.applications ?? 0;
  const hidden = report ? report.eligible - report.cited - report.idle.length : 0;

  return (
    <Screen heading={t("ledger.heading")} lede={t("ledger.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runLedger()} onDismiss={dismissError} />
      )}

      {phase === "running" && !report && (
        <p class="muted" aria-live="polite">
          {t("ledger.running")}
        </p>
      )}

      {tracker.value.length === 0 && (
        <EmptyState
          text={t("ledger.noMatches")}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      )}

      {/* Said in every branch, not only under a full report: when the
          applications were all checked against an older parse of the CV, this
          is the only sentence that explains why a tracker with five rows in it
          is being told to come back after three. */}
      {report && report.skipped > 0 && (
        <p class="small muted ledger__skipped">
          {t("ledger.skipped", { count: report.skipped })}
        </p>
      )}

      {/* Two applications cannot say which line does the work — only which
          line the last two postings happened to ask about. Naming the number
          it needs turns a dead end into a next step. */}
      {report && tracker.value.length > 0 && applications < MIN_MATCHES && (
        <EmptyState
          text={t("ledger.tooFew", { count: applications, needed: MIN_MATCHES })}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      )}

      {report && applications >= MIN_MATCHES && (
        <>
          <p class="ledger__read" aria-live="polite">
            {t("ledger.read", {
              cited: report.cited,
              total: report.eligible,
              count: applications,
            })}
          </p>

          {report.working.length === 0 && <EmptyState text={t("ledger.noneCited")} />}

          {report.working.length > 0 && (
            <section class="stack stack--tight ledger__section">
              <h2>{t("ledger.workingHeading")}</h2>
              <p class="muted ledger__lede">{t("ledger.workingBody")}</p>
              <ul class="list">
                {report.working.map((line) => (
                  <Row
                    key={line.id}
                    line={line}
                    source={lines.get(line.id)}
                    applications={applications}
                  />
                ))}
              </ul>
            </section>
          )}

          {/* The honest framing is the feature. A list headed "cut these"
              would be the app deciding what someone's career is worth from
              four job ads. */}
          {report.idle.length > 0 && (
            <section class="stack stack--tight ledger__section">
              <h2>{t("ledger.idleHeading")}</h2>
              <p class="muted ledger__lede">{t("ledger.idleBody")}</p>
              <ul class="list">
                {report.idle.map((line) => (
                  <Row
                    key={line.id}
                    line={line}
                    source={lines.get(line.id)}
                    applications={applications}
                  />
                ))}
              </ul>
              {hidden > 0 && <p class="small muted">{t("ledger.idleMore", { count: hidden })}</p>}
            </section>
          )}

          {/* The payback of the answer loop. Three screens ask the user to
              write a sentence into their CV; until this one, nothing ever
              reported back on whether it was worth writing. */}
          {report.added.length > 0 && (
            <section class="stack stack--tight ledger__section ledger__section--added">
              <h2>{t("ledger.addedHeading")}</h2>
              <p class="muted ledger__lede">{t("ledger.addedBody")}</p>
              <ul class="list">
                {report.added.map((line) => (
                  <li key={line.id} class="ledgerrow">
                    <Quote source={lines.get(line.id)} id={line.id} />
                    <p class="ledgerrow__count">
                      {line.applications === 0
                        ? t("ledger.addedIdle")
                        : line.applications === 1
                          ? t("ledger.addedProvedOne")
                          : t("ledger.addedProved", { count: line.applications })}
                    </p>
                    <Proves line={line} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <div class="row ledger__actions">
        <button
          type="button"
          class="button button--secondary"
          onClick={() => navigate("/cv/preview")}
        >
          {t("ledger.back")}
        </button>
      </div>
    </Screen>
  );
}

interface RowProps {
  line: LedgerLine;
  source: CvLine | undefined;
  applications: number;
}

function Row({ line, source, applications }: RowProps) {
  return (
    <li class="ledgerrow">
      <Quote source={source} id={line.id} />
      {line.applications > 0 && (
        <p class="ledgerrow__count">
          {t("ledger.cited", { count: line.applications, total: applications })}
          {line.citations > line.applications
            ? ` ${t("ledger.citedMore", { count: line.citations })}`
            : ""}
        </p>
      )}
      {/* The sentence an interviewer's doubt would take down with it. */}
      {line.decisive > 0 && (
        <p class="ledgerrow__decisive">
          {line.decisive === 1
            ? t("ledger.decisiveOne")
            : t("ledger.decisiveMany", { count: line.decisive })}
        </p>
      )}
      <Proves line={line} />
    </li>
  );
}

interface QuoteProps {
  source: CvLine | undefined;
  id: LineId;
}

/**
 * The CV line itself, quoted.
 *
 * Deliberately unmarked. The highlighter means one thing in this app — a
 * receipt for a requirement (docs.md §8.3) — and a screen that marked every
 * row would spend the product's one bold element on a list bullet. Here the
 * line is the subject and the count underneath it is the claim.
 */
function Quote({ source, id }: QuoteProps) {
  // `lib/ledger.renderable` drops a row whose line this CV does not have, so
  // the fallback is a belt to that braces rather than a state to design for.
  const text = source?.text ?? "";

  return (
    <>
      <p class="ledgerrow__quote">{text}</p>
      <div class="row ledgerrow__chips">
        <SourceChip line={id} />
        {source?.added_at && <span class="small muted">{t("cv.preview.addedByYou")}</span>}
      </div>
    </>
  );
}

function Proves({ line }: { line: LedgerLine }) {
  if (line.proves.length === 0) return null;
  // The postings' own words, not the app's: what was merged is visible, the
  // same way the recurring report shows the wordings behind a group.
  return <p class="ledgerrow__proves">{t("ledger.proves", { list: line.proves.join(", ") })}</p>;
}
