/**
 * What changed.
 *
 * Four screens in this app ask the user to write a sentence into their own CV
 * — a gap question, an audit finding, a recurring gap — and the last of them
 * ends in "run this posting again". They run it again, and until this screen
 * existed the app handed back a fresh match map with no memory of the first
 * attempt. The one moment the whole product is built towards — **the sentence
 * you wrote turned a "no evidence yet" into a receipt** — was the moment it
 * had nothing to say.
 *
 * No model, no tokens: two stored results, lined up on the same lexicon every
 * cross-application screen in this app uses.
 *
 * Two things keep it a record rather than a congratulation. What went the
 * other way is shown with the same weight as what improved — a posting read
 * twice is not read identically, and a screen that only ever reported gains
 * would be flattering the user rather than informing them. And credit is only
 * claimed where the citation proves it: "because of the line you added"
 * appears when the newer run is standing on a sentence written after the
 * older one, and never otherwise.
 */

import { useEffect } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { MarkerHighlight } from "../components/MarkerHighlight";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { navigate } from "../router";
import { isEmpty } from "../lib/rerun";
import {
  activeCv,
  currentMatch,
  dismissError,
  earlierRun,
  error,
  rerunPhase,
  rerunResult,
  runRerun,
} from "../state";
import type { CvLine, LineId, RunChange } from "../lib/types";
import "./Changed.css";

export function Changed() {
  const diff = rerunResult.value;
  const phase = rerunPhase.value;
  const match = currentMatch.value;
  const doc = activeCv();
  const earlier = earlierRun.value;

  useEffect(() => {
    if (match && doc && earlier && phase === "idle") void runRerun();
  }, [match?.id, earlier?.id, doc?.hash, phase]);

  if (!match || !doc || !earlier) {
    return (
      <Screen heading={t("changed.heading")}>
        <EmptyState
          text={t("changed.noEarlier")}
          action={
            <button type="button" class="button" onClick={() => navigate("/matches")}>
              {t("nav.matches")}
            </button>
          }
        />
      </Screen>
    );
  }

  const lines = new Map(doc.lines.map((line) => [line.id, line]));
  const role = match.posting.title ?? t("tracker.untitledRole");

  return (
    <Screen
      heading={t("changed.heading")}
      lede={
        diff?.days_between === null || diff === null
          ? t("changed.body", { role })
          : t("changed.bodyDays", { role, count: diff.days_between })
      }
    >
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runRerun()} onDismiss={dismissError} />
      )}

      {phase === "running" && !diff && (
        <p class="muted" aria-live="polite">
          {t("changed.running")}
        </p>
      )}

      {diff && (
        <>
          {/* Both totals, because a posting is read again on every run and the
              denominator can move. Hiding that would make a gain of one
              requirement look like a gain of three. */}
          <p class="changed__read" aria-live="polite">
            {t("changed.read", {
              after: diff.after_strong,
              afterTotal: diff.after_total,
              before: diff.before_strong,
              beforeTotal: diff.before_total,
            })}
          </p>

          {diff.added_between.length > 0 && (
            <p class="small muted changed__wrote">
              {diff.added_between.length === 1
                ? t("changed.wroteOne")
                : t("changed.wrote", { count: diff.added_between.length })}
            </p>
          )}

          {isEmpty(diff) && <EmptyState text={t("changed.nothing")} />}

          {diff.gained.length > 0 && (
            <section class="stack stack--tight changed__section">
              <h2>{t("changed.gainedHeading")}</h2>
              <ul class="list">
                {diff.gained.map((change) => (
                  <Change key={change.key} change={change} lines={lines} marked />
                ))}
              </ul>
            </section>
          )}

          {/* Shown with the same weight as the gains, and explained: the
              honest reason is usually that the posting was read differently,
              not that the candidate got worse. */}
          {diff.lost.length > 0 && (
            <section class="stack stack--tight changed__section">
              <h2>{t("changed.lostHeading")}</h2>
              <p class="muted changed__lede">{t("changed.lostBody")}</p>
              <ul class="list">
                {diff.lost.map((change) => (
                  <Change key={change.key} change={change} lines={lines} />
                ))}
              </ul>
            </section>
          )}

          {diff.still.length > 0 && (
            <section class="stack stack--tight changed__section">
              <h2>{t("changed.stillHeading")}</h2>
              <p class="muted changed__lede">{t("changed.stillBody")}</p>
              <ul class="list">
                {diff.still.map((change) => (
                  <Change key={change.key} change={change} lines={lines} />
                ))}
              </ul>
              <div class="row">
                <button
                  type="button"
                  class="button button--secondary"
                  onClick={() => navigate("/gaps")}
                >
                  {t("changed.prepare")}
                </button>
              </div>
            </section>
          )}

          {/* The lexicon's limits, in plain sight rather than papered over. */}
          {diff.differed.length > 0 && (
            <section class="stack stack--tight changed__section changed__section--quiet">
              <h2>{t("changed.differedHeading")}</h2>
              <p class="muted changed__lede">{t("changed.differedBody")}</p>
              <ul class="list">
                {diff.differed.map((change) => (
                  <Change key={change.key} change={change} lines={lines} />
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <div class="row changed__actions">
        <button
          type="button"
          class="button button--secondary"
          onClick={() => navigate(`/match/${match.id}`)}
        >
          {t("changed.backToMatch")}
        </button>
        <button
          type="button"
          class="button button--quiet"
          onClick={() => navigate(`/match/${earlier.id}`)}
        >
          {t("changed.openEarlier")}
        </button>
      </div>
    </Screen>
  );
}

interface ChangeProps {
  change: RunChange;
  lines: Map<LineId, CvLine>;
  marked?: boolean;
}

function Change({ change, lines, marked }: ChangeProps) {
  const cited = change.line_ids.map((id) => lines.get(id)).filter(isLine);

  return (
    <li class="change">
      <div class="change__head">
        <h3 class="change__subject">
          {marked ? <MarkerHighlight status="strong">{change.surface}</MarkerHighlight> : change.surface}
        </h3>
        {change.kind === "must" && <span class="change__must small">{t("map.mustHave")}</span>}
      </div>

      {/* Both verdicts, in the app's own words for them, and never a score. */}
      <p class="change__move">{verdictSentence(change)}</p>

      {/* The sentence that did it. This is the payoff of every answer box in
          the product, so it is the one line on the screen that names the
          user's own writing as the cause — and only where the citation shows
          it (`lib/rerun.renderable`). */}
      {change.credited && <p class="change__credit">{t("changed.credited")}</p>}

      {cited.length > 0 && (
        <ul class="stack stack--tight change__lines">
          {cited.map((line) => (
            <li key={line.id} class="change__line">
              <p class="change__quote">{line.text}</p>
              <div class="row change__chips">
                <SourceChip line={line.id} />
                {line.added_at && <span class="small muted">{t("cv.preview.addedByYou")}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** What the two runs said, spelled out rather than arrowed. */
function verdictSentence(change: RunChange): string {
  if (change.direction === "new_ask") {
    return t("changed.onlyNow", { after: t(`status.${change.after ?? "missing"}`) });
  }
  if (change.direction === "dropped_ask") {
    return t("changed.onlyThen", { before: t(`status.${change.before ?? "missing"}`) });
  }
  return t("changed.move", {
    before: t(`status.${change.before ?? "missing"}`),
    after: t(`status.${change.after ?? "missing"}`),
  });
}

function isLine(line: CvLine | undefined): line is CvLine {
  return line !== undefined;
}
