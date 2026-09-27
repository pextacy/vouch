/**
 * What keeps coming up.
 *
 * Every other screen answers "does this CV fit this job". This one answers the
 * question a single match structurally cannot: across everything you have
 * applied to, what is the one thing that keeps costing you? No model touches
 * it — the numbers are counts of verdicts the verifier already made, one
 * application at a time, which is why this app can say them out loud and a
 * tool that guesses cannot.
 *
 * Two things keep it from becoming a horoscope. A gap is only named when it
 * was asked more than once and proved **none** of those times, so a skill with
 * a mixed record is passed over in silence rather than scored. And the
 * grouping is shown rather than asserted: each row lists the wordings that
 * were merged under it, so a user who disagrees can see why.
 *
 * The strengths list is not decoration. A report that is only a list of
 * failures stops being read — the same reason the match summary drops its
 * second sentence when there is nothing to warn about.
 */

import { useEffect, useState } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { navigate } from "../router";
import { MIN_MATCHES } from "../lib/recurring";
import {
  answerRecurring,
  answeredRecurring,
  dismissError,
  error,
  hasCv,
  recurringPhase,
  recurringResult,
  runRecurring,
  tracker,
} from "../state";
import type { RecurringGroup } from "../lib/types";
import "./Recurring.css";

export function Recurring() {
  const report = recurringResult.value;
  const phase = recurringPhase.value;

  useEffect(() => {
    if (phase === "idle") void runRecurring();
  }, [phase]);

  if (tracker.value.length === 0) {
    return (
      <Screen heading={t("recurring.heading")}>
        <EmptyState
          text={t("recurring.noMatches")}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      </Screen>
    );
  }

  const matches = report?.matches ?? 0;
  const groups = report?.groups ?? [];
  const strengths = report?.strengths ?? [];

  return (
    <Screen heading={t("recurring.heading")} lede={t("recurring.body")}>
      {error.value && (
        <ErrorNotice
          error={error.value}
          onRetry={() => void runRecurring()}
          onDismiss={dismissError}
        />
      )}

      {phase === "running" && !report && (
        <p class="muted" aria-live="polite">
          {t("recurring.running")}
        </p>
      )}

      {/* Under three applications there is no "keeps coming up" to speak of,
          and a pattern drawn from two would be a horoscope. Saying how many
          are needed turns a dead end into a next step. */}
      {report && matches < MIN_MATCHES && (
        <EmptyState
          text={t("recurring.tooFew", { count: matches, needed: MIN_MATCHES })}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      )}

      {report && matches >= MIN_MATCHES && groups.length === 0 && (
        <EmptyState text={t("recurring.none", { count: matches })} />
      )}

      {groups.length > 0 && (
        <>
          <p class="recurring__read" aria-live="polite">
            {t("recurring.read", { count: matches })}
          </p>
          <ul class="list">
            {groups.map((group) => (
              <GapRow
                key={group.key}
                group={group}
                answered={answeredRecurring.value.has(group.key)}
                readOnly={!hasCv.value}
              />
            ))}
          </ul>
        </>
      )}

      {strengths.length > 0 && (
        <section class="stack stack--tight recurring__strengths">
          <h2 class="recurring__group">{t("recurring.strengthsHeading")}</h2>
          <p class="muted">{t("recurring.strengthsBody")}</p>
          <ul class="recurring__strengthList">
            {strengths.map((strength) => (
              <li key={strength.key}>
                {t("recurring.strength", {
                  subject: strength.surface,
                  count: strength.asked,
                })}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div class="row">
        <button type="button" class="button button--secondary" onClick={() => navigate("/matches")}>
          {t("recurring.backToMatches")}
        </button>
      </div>
    </Screen>
  );
}

interface GapRowProps {
  group: RecurringGroup;
  answered: boolean;
  readOnly: boolean;
}

function GapRow({ group, answered, readOnly }: GapRowProps) {
  const [draft, setDraft] = useState("");
  const [showTexts, setShowTexts] = useState(false);
  const [saving, setSaving] = useState(false);
  const inputId = `recurring-${group.key.replace(/\W+/g, "-")}`;
  const textsId = `${inputId}-texts`;

  async function save(): Promise<void> {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      await answerRecurring(group.key, draft);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li class="recur">
      <h2 class="recur__subject">{group.surface}</h2>
      {/* "Asked in 5 applications, proved in none" — the denominator is in the
          sentence, because the count on its own says nothing about whether
          this is the thing to go and learn. */}
      <p class="recur__count">{t("recurring.asked", { count: group.asked })}</p>
      {group.must > 0 && (
        <p class="recur__must">{t("recurring.must", { count: group.must })}</p>
      )}

      {/* The grouping is the one judgement here the user cannot check from the
          numbers, so it is one tap away rather than hidden. */}
      <button
        type="button"
        class="button button--quiet recur__toggle"
        aria-expanded={showTexts}
        aria-controls={textsId}
        onClick={() => setShowTexts(!showTexts)}
      >
        {showTexts ? t("recurring.hideWordings") : t("recurring.showWordings")}
      </button>
      {showTexts && (
        <ul class="recur__texts" id={textsId}>
          {group.texts.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      )}

      {answered ? (
        <p class="recur__saved">{t("recurring.saved")}</p>
      ) : (
        <div class="stack stack--tight recur__answer">
          <label class="recur__label" for={inputId}>
            {t("recurring.answerLabel")}
          </label>
          <textarea
            id={inputId}
            class="textarea recur__input"
            rows={3}
            value={draft}
            disabled={readOnly}
            placeholder={t("recurring.answerPlaceholder")}
            onInput={(event) => setDraft((event.target as HTMLTextAreaElement).value)}
          />
          <p class="small muted">{t("recurring.answerNote")}</p>
          <div class="row">
            <button
              type="button"
              class="button"
              disabled={readOnly || saving || !draft.trim()}
              onClick={() => void save()}
            >
              {saving ? t("recurring.adding") : t("recurring.add")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
