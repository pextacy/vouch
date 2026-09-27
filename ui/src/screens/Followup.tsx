/**
 * The note after the silence — and the one the app refuses to write.
 *
 * An application goes out and nothing comes back. Every other tool in this
 * category will write the follow-up on demand: a warm paragraph saying the
 * candidate remains very interested, which hands a recruiter nothing they did
 * not already have and spends the one piece of attention a candidate gets.
 *
 * This app already knows whether there is anything to say, because it knows
 * what the CV has gained since the application went out (`since_applied`).
 * When there is nothing, the screen says so and points at the thing that
 * would change it — a gap answered in the user's own words. That refusal is
 * the feature; the note is what happens when the refusal does not apply.
 *
 * When it does write, every sentence stands on a line the user wrote *after*
 * they applied, cited and verified like the cover letter. The note never
 * writes a date: the app says how long it has been, from the tracker's own
 * record, because the model is never told and cannot be.
 */

import { useEffect, useState } from "preact/hooks";

import { DocumentSheet } from "../components/DocumentSheet";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { LetterParagraph } from "../components/LetterParagraph";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { navigate } from "../router";
import { namesFromMatch, resolvedParagraphs } from "../lib/letter";
import {
  activeCv,
  currentMatch,
  dismissError,
  error,
  followupPhase,
  followupResult,
  runFollowup,
} from "../state";
import "./Followup.css";

export function Followup() {
  const result = followupResult.value;
  const phase = followupPhase.value;
  const match = currentMatch.value;
  const doc = activeCv();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (match && doc && phase === "idle") void runFollowup();
  }, [match?.id, doc?.hash, phase]);

  if (!match || !doc) {
    return (
      <Screen heading={t("followup.heading")}>
        <EmptyState
          text={t("followup.noMatch")}
          action={
            <button type="button" class="button" onClick={() => navigate("/matches")}>
              {t("nav.matches")}
            </button>
          }
        />
      </Screen>
    );
  }

  // The stored text still says `[Company]`: the engine keeps a paragraph
  // exactly as it was verified and leaves the names to the point of use.
  const paragraphs = result ? resolvedParagraphs(result, namesFromMatch(match)) : [];
  const plain = paragraphs.map((paragraph) => paragraph.text).join("\n\n");
  const role = match.posting.title ?? t("tracker.untitledRole");

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(plain);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // The note is on screen and selectable either way.
    }
  }

  return (
    <Screen heading={t("followup.heading")} lede={t("followup.body", { role })}>
      {error.value && (
        <ErrorNotice
          error={error.value}
          onRetry={() => void runFollowup()}
          onDismiss={dismissError}
        />
      )}

      {phase === "running" && !result && (
        <p class="muted" aria-live="polite">
          {t("followup.running")}
        </p>
      )}

      {/* How long it has been, on the clock the record actually has. The note
          itself never says it: the model is not told the date. */}
      {result && result.days !== null && (
        <p class="followup__age" aria-live="polite">
          {ageSentence(result.dated_from, result.days)}
        </p>
      )}

      {/* The refusal, and the one thing that would change it. */}
      {result?.kind === "nothing_new" && (
        <EmptyState
          text={t("followup.nothingNew")}
          action={
            <button type="button" class="button" onClick={() => navigate("/gaps")}>
              {t("followup.toGaps")}
            </button>
          }
        />
      )}

      {result?.kind === "new_evidence" && (
        <>
          <p class="followup__stands">
            {t("followup.standsOn", { list: result.terms.join(", ") })}
          </p>

          {result.placeholders.length > 0 && (
            <p class="followup__warning">
              {t("followup.placeholderWarning", { items: result.placeholders.join(", ") })}
            </p>
          )}

          <DocumentSheet title={t("followup.sheetTitle")}>
            {paragraphs.map((paragraph, index) => (
              <LetterParagraph key={index} paragraph={paragraph} showCitations />
            ))}
          </DocumentSheet>

          {/* The lines it was allowed to use — all written after the
              application went out, which is the whole licence this note has. */}
          <div class="row followup__chips">
            <span class="small muted">{t("followup.builtOn")}</span>
            {result.line_ids.map((id) => (
              <SourceChip key={id} line={id} />
            ))}
          </div>

          <div class="row followup__actions">
            <button type="button" class="button" onClick={() => void copy()}>
              {copied ? t("letter.copied") : t("followup.copy")}
            </button>
            <button
              type="button"
              class="button button--quiet"
              onClick={() => navigate(`/match/${match.id}`)}
            >
              {t("followup.backToMatch")}
            </button>
          </div>
        </>
      )}
    </Screen>
  );
}

/** How long it has been, spelled out rather than composed (`Since.tsx`). */
function ageSentence(from: "sent" | "checked", days: number): string {
  if (from === "sent") {
    if (days === 0) return t("followup.sentToday");
    if (days === 1) return t("followup.sentDay");
    return t("followup.sentDays", { count: days });
  }
  if (days === 0) return t("followup.checkedToday");
  if (days === 1) return t("followup.checkedDay");
  return t("followup.checkedDays", { count: days });
}
