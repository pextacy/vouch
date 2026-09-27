/**
 * Worth another look.
 *
 * "Since you applied" asks, of one application, whether the CV has gained a
 * line that names something that application could not show. It answers well,
 * and it is the wrong shape for the person this product is for: someone
 * sending thirty applications a month is never going to open thirty saved
 * applications to find out whether last Tuesday's sentence changed any of
 * them. The answer existed, and nothing was ever going to read it.
 *
 * So this is the same question asked of the whole shelf at once, and it is
 * the screen that gives someone a reason to open Receipts on a day they are
 * not applying to anything new: *these three are worth an hour, and here is
 * the sentence that made them worth it.*
 *
 * **No model, no tokens.** Dates and a lexicon over records that already
 * exist — and the same `naming_lines` rule the per-application screen uses,
 * so the two can never disagree about what counts.
 *
 * The word is still "names", never "proves". Each row ends at the screen that
 * explains it and offers the one thing that can settle it: running the match
 * again.
 */

import { useEffect } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  activeCv,
  dismissError,
  error,
  openSince,
  runWorth,
  tracker,
  worthPhase,
  worthResult,
} from "../state";
import type { TrackerEntry, WorthItem } from "../lib/types";
import "./Worth.css";

export function Worth() {
  const report = worthResult.value;
  const phase = worthPhase.value;
  const doc = activeCv();

  useEffect(() => {
    if (doc && phase === "idle") void runWorth();
  }, [doc?.hash, phase]);

  const entries = new Map(tracker.value.map((entry) => [entry.id, entry]));
  const items = (report?.items ?? []).filter((item) => entries.has(item.match));

  return (
    <Screen heading={t("worth.heading")} lede={t("worth.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runWorth()} onDismiss={dismissError} />
      )}

      {phase === "running" && !report && (
        <p class="muted" aria-live="polite">
          {t("worth.running")}
        </p>
      )}

      {report && report.applications === 0 && (
        <EmptyState
          text={t("worth.noMatches")}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      )}

      {/* Nothing written yet is a different answer from nothing found, and it
          has a different next step: this screen only ever has something to
          say once the user has answered something. */}
      {report && report.applications > 0 && report.written === 0 && (
        <EmptyState
          text={t("worth.nothingWritten")}
          action={
            <button type="button" class="button" onClick={() => navigate("/recurring")}>
              {t("worth.toRecurring")}
            </button>
          }
        />
      )}

      {report && report.applications > 0 && report.written > 0 && items.length === 0 && (
        <EmptyState text={t("worth.none", { count: report.applications })} />
      )}

      {items.length > 0 && report && (
        <>
          <p class="worth__read" aria-live="polite">
            {items.length === 1
              ? t("worth.readOne", { total: report.applications })
              : t("worth.read", { count: items.length, total: report.applications })}
          </p>
          <ul class="list">
            {items.map((item) => (
              <Row key={item.match} item={item} entry={entries.get(item.match)!} />
            ))}
          </ul>
        </>
      )}

      <div class="row worth__actions">
        <button type="button" class="button button--secondary" onClick={() => navigate("/matches")}>
          {t("worth.backToMatches")}
        </button>
      </div>
    </Screen>
  );
}

function Row({ item, entry }: { item: WorthItem; entry: TrackerEntry }) {
  const role = entry.role ?? t("tracker.untitledRole");
  const company = entry.company;
  const days = daysSince(entry.status_at ?? entry.created_at);

  return (
    <li class="worth">
      <div class="worth__head">
        <h2 class="worth__role">{role}</h2>
        {company && <span class="worth__company small muted">{company}</span>}
      </div>

      {days !== null && (
        <p class="small muted worth__age">
          {days === 0
            ? t("worth.sentToday")
            : days === 1
              ? t("worth.sentDay")
              : t("worth.sentDays", { count: days })}
        </p>
      )}

      {/* The claim, with its denominator: two of the five things it could not
          show, not two out of nowhere. */}
      <p class="worth__claim">
        {t("worth.names", { list: item.terms.join(", ") })}{" "}
        {t("worth.of", { count: item.requirements, total: item.unproved })}
      </p>
      {/* Meta, not a second claim: everywhere else in this app a must-have is
          a small quiet label beside the thing it qualifies. */}
      {item.must > 0 && (
        <p class="small worth__must">
          {item.must === 1 ? t("worth.mustOne") : t("worth.must", { count: item.must })}
        </p>
      )}

      {/* What the posting actually asked for, so the row can be checked
          rather than trusted — the same habit as the recurring report. */}
      {item.texts.length > 0 && (
        <ul class="worth__texts">
          {item.texts.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      )}

      <div class="row worth__chips">
        {item.line_ids.map((id) => (
          <SourceChip key={id} line={id} />
        ))}
        <span class="small muted">{t("worth.fromYourLines")}</span>
      </div>

      <div class="row">
        {/* Straight to the screen that explains it and offers the re-run: one
            screen, one job, and this one is the index. */}
        <button
          type="button"
          class="button button--quiet"
          onClick={() => void openSince(item.match)}
        >
          {t("worth.open")}
        </button>
      </div>
    </li>
  );
}

/** Whole days since an ISO timestamp, or null when it cannot be read. */
function daysSince(value: string): number | null {
  const moment = Date.parse(value);
  if (Number.isNaN(moment)) return null;
  return Math.max(0, Math.floor((Date.now() - moment) / 86_400_000));
}
