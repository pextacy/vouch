/**
 * Which one to spend the hour on.
 *
 * Three postings are open in three tabs and there is time to tailor one
 * properly. Every other tool answers that with a fit score — a number invented
 * by the same model that wrote the bullets, precise to a percentage point
 * about something it guessed. This app already holds something better: a
 * verified per-requirement verdict for each of those postings, each one citing
 * lines, made one application at a time.
 *
 * So there is no gauge and no score on this screen. There are counts a person
 * can check against the match map they came from, the must-haves that are
 * standing in the way, and the one thing a comparison can say that a single
 * match cannot: what this posting asks for that the others do not, and your CV
 * can prove.
 *
 * Nothing here calls the model. Changing the selection re-runs it, because
 * re-running costs nothing at all.
 */

import { useEffect } from "preact/hooks";

import { CheckIcon } from "../components/Icons";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { navigate } from "../router";
import { MAX_POSTINGS, MIN_POSTINGS } from "../lib/compare";
import {
  comparePhase,
  compareResult,
  compareSelection,
  dismissError,
  error,
  openMatch,
  runCompare,
  startCompare,
  toggleCompare,
  tracker,
} from "../state";
import type { CompareColumn, RecurringGroup, TrackerEntry } from "../lib/types";
import "./Compare.css";

export function Compare() {
  const entries = tracker.value;
  const selection = compareSelection.value;
  const phase = comparePhase.value;
  const result = compareResult.value;

  // The two most recent are selected on arrival, so the screen answers a
  // question instead of handing the user a form to fill in first.
  useEffect(() => {
    if (entries.length >= MIN_POSTINGS) startCompare();
  }, [entries.length]);

  useEffect(() => {
    if (selection.length >= MIN_POSTINGS && phase === "idle") void runCompare();
  }, [selection.join(","), phase]);

  if (entries.length < MIN_POSTINGS) {
    return (
      <Screen heading={t("compare.heading")}>
        <EmptyState
          text={t("compare.needMatches")}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      </Screen>
    );
  }

  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const columns = result?.columns ?? [];

  return (
    <Screen heading={t("compare.heading")} lede={t("compare.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runCompare()} onDismiss={dismissError} />
      )}

      <fieldset class="compare__picker">
        <legend class="compare__legend">{t("compare.pickLabel")}</legend>
        <p class="small muted compare__hint">
          {t("compare.pickHint", { max: MAX_POSTINGS })}
        </p>
        <ul class="compare__options">
          {entries.map((entry) => (
            <PickOption
              key={entry.id}
              entry={entry}
              checked={selection.includes(entry.id)}
              /* A fifth column would not fit a phone, so the box says no
                 rather than silently dropping the posting the user just
                 picked. */
              disabled={!selection.includes(entry.id) && selection.length >= MAX_POSTINGS}
            />
          ))}
        </ul>
      </fieldset>

      {selection.length < MIN_POSTINGS && <p class="compare__need">{t("compare.needTwo")}</p>}

      {phase === "running" && !result && (
        <p class="muted" aria-live="polite">
          {t("compare.running")}
        </p>
      )}

      {columns.length > 0 && (
        <>
          <ol class="compare__columns">
            {columns.map((column) => (
              <PostingRow key={column.match} column={column} entry={byId.get(column.match)} />
            ))}
          </ol>
          {/* The ranking is by evidence and by nothing else. Saying so is what
              keeps the order from reading as advice about where to work. */}
          <p class="small muted compare__ordering">{t("compare.ordering")}</p>
        </>
      )}

      {(result?.shared_gaps.length ?? 0) > 0 && (
        <section class="stack stack--tight compare__shared">
          <h2 class="compare__sharedHeading">{t("compare.sharedGapsHeading")}</h2>
          <p class="muted">{t("compare.sharedGapsBody")}</p>
          <ul class="compare__terms">
            {result?.shared_gaps.map((group) => (
              <SharedTerm key={group.key} group={group} />
            ))}
          </ul>
        </section>
      )}

      {(result?.shared_proved.length ?? 0) > 0 && (
        <section class="stack stack--tight compare__shared">
          <h2 class="compare__sharedHeading">{t("compare.sharedProvedHeading")}</h2>
          <ul class="compare__terms">
            {result?.shared_proved.map((group) => (
              <SharedTerm key={group.key} group={group} />
            ))}
          </ul>
        </section>
      )}

      <div class="row">
        <button type="button" class="button button--secondary" onClick={() => navigate("/matches")}>
          {t("compare.backToMatches")}
        </button>
      </div>
    </Screen>
  );
}

function PickOption({
  entry,
  checked,
  disabled,
}: {
  entry: TrackerEntry;
  checked: boolean;
  disabled: boolean;
}) {
  const role = entry.role ?? t("tracker.untitledRole");
  const company = entry.company ?? t("tracker.unknownCompany");
  return (
    <li>
      <label class={`compare__option${checked ? " compare__option--on" : ""}`}>
        {/* Hidden but real, the way the tone switch does it: the label is the
            tap target, and a 18 px box is not one. */}
        <input
          type="checkbox"
          class="visually-hidden"
          checked={checked}
          disabled={disabled}
          onChange={() => toggleCompare(entry.id)}
        />
        <span class="compare__mark">{checked && <CheckIcon size={14} />}</span>
        <span class="compare__optionText">
          <span>{role}</span>
          <span class="small muted">{company}</span>
        </span>
      </label>
    </li>
  );
}

function PostingRow({ column, entry }: { column: CompareColumn; entry: TrackerEntry | undefined }) {
  const role = entry?.role ?? t("tracker.untitledRole");
  const company = entry?.company ?? t("tracker.unknownCompany");

  return (
    <li class="compare__row">
      <h2 class="compare__role">{role}</h2>
      <p class="small muted">{company}</p>

      {/* Must-haves first and on their own line: they are what decides whether
          the application is worth sending, and burying them in a total would
          hide the one number this screen exists to show. */}
      <p class="compare__count">
        {column.must_asked > 0
          ? t("compare.mustCoverage", { proved: column.must_proved, asked: column.must_asked })
          : t("compare.noMusts")}
      </p>
      <p class="compare__count small muted">
        {t("compare.overall", {
          proved: column.proved,
          asked: column.asked,
          related: column.related,
        })}
      </p>

      {column.blockers.length > 0 && (
        <div class="compare__terms compare__terms--blockers">
          <h3 class="compare__termsLabel">{t("compare.blockersLabel")}</h3>
          <p>{column.blockers.join(", ")}</p>
        </div>
      )}

      {column.edge.length > 0 && (
        <div class="compare__terms">
          <h3 class="compare__termsLabel">{t("compare.edgeLabel")}</h3>
          <p>{column.edge.join(", ")}</p>
        </div>
      )}

      <button
        type="button"
        class="button button--quiet compare__open"
        onClick={() => void openMatch(column.match)}
      >
        {t("compare.open")}
      </button>
    </li>
  );
}

/**
 * One term the whole set agrees on.
 *
 * The wordings that were merged travel with it, set as the postings wrote
 * them, so a user who disagrees with the grouping can see what it merged
 * rather than take it on trust — the same rule the recurring view follows.
 */
function SharedTerm({ group }: { group: RecurringGroup }) {
  // Only when the merge is worth seeing. A group whose single wording is the
  // heading already shown would print the same sentence twice, which reads as
  // a bug rather than as the receipts the list is there to give.
  const merged = group.texts.filter((text) => text !== group.surface);
  return (
    <li class="compare__sharedTerm">
      <span class="compare__term">{group.surface}</span>
      {merged.length > 0 && (
        <ul class="compare__wordings">
          {merged.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      )}
    </li>
  );
}
