/**
 * The gaps, as questions.
 *
 * The match map ends at "No evidence yet", which is a diagnosis. This is where
 * it becomes something to do. Every other tool in this category closes a gap by
 * writing the experience in for the candidate; here the app asks, the person
 * answers in their own words, and the answer is stored in their CV exactly as
 * typed — so the next match can cite it with a line number like any other fact.
 *
 * Nothing on this screen is a claim about the user. The question is a question;
 * the "angle" beneath it is the one sentence that does make a claim, and it
 * only ever appears when the verifier could trace it to the CV lines shown
 * beside it.
 */

import { useEffect, useState } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  answerGap,
  answeredGaps,
  currentMatch,
  cvMovedOnFromMatch,
  dismissError,
  error,
  gapsPhase,
  gapsResult,
  runGaps,
  showingExample,
} from "../state";
import type { GapItem, Requirement } from "../lib/types";
import "./Gaps.css";

export function Gaps() {
  const match = currentMatch.value;
  const result = gapsResult.value;
  const phase = gapsPhase.value;

  useEffect(() => {
    if (match && !result && phase === "idle" && !showingExample.value) {
      void runGaps();
    }
  }, [match?.id, result, phase]);

  if (!match) {
    navigate("/matches");
    return null;
  }

  const byId = new Map(match.requirements.map((item) => [item.id, item]));
  const answered = answeredGaps.value;

  return (
    <Screen heading={t("gaps.heading")} lede={t("gaps.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runGaps()} onDismiss={dismissError} />
      )}

      {phase === "running" && (
        <p class="muted" aria-live="polite">
          {t("gaps.running")}
        </p>
      )}

      {result && result.items.length === 0 && <EmptyState text={t("gaps.none")} />}

      {result && result.items.length > 0 && (
        <ul class="list">
          {result.items.map((item) => (
            <GapCard
              key={item.requirement_id}
              item={item}
              requirement={byId.get(item.requirement_id)}
              answered={answered.has(item.requirement_id)}
              readOnly={showingExample.value}
            />
          ))}
        </ul>
      )}

      {/* An answer changes the CV, which makes the match on screen out of date.
          Saying so here — next to the answers that caused it — is the difference
          between a rule the user understands and an error they run into. */}
      {cvMovedOnFromMatch.value && (
        <div class="stack stack--tight gaps__rerun">
          <p>{t("gaps.rerun")}</p>
          <button type="button" class="button" onClick={() => navigate("/new")}>
            {t("gaps.rerunAction")}
          </button>
        </div>
      )}

      <div class="row">
        <button
          type="button"
          class="button button--secondary"
          onClick={() => navigate(`/match/${match.id}`)}
        >
          {t("nav.back")}
        </button>
      </div>
    </Screen>
  );
}

interface GapCardProps {
  item: GapItem;
  requirement: Requirement | undefined;
  answered: boolean;
  readOnly: boolean;
}

function GapCard({ item, requirement, answered, readOnly }: GapCardProps) {
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const inputId = `gap-${item.requirement_id}`;

  async function save(): Promise<void> {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      await answerGap(item.requirement_id, draft);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li class="gap">
      {requirement && <p class="gap__requirement">{requirement.text}</p>}
      <h2 class="gap__question">{item.question}</h2>

      {item.angle && (
        <div class="gap__angle">
          <p>{item.angle}</p>
          {item.line_ids.length > 0 && (
            <div class="row gap__chips">
              {item.line_ids.map((line) => (
                <SourceChip key={line} line={line} />
              ))}
            </div>
          )}
        </div>
      )}

      {answered ? (
        <p class="gap__saved">{t("gaps.saved")}</p>
      ) : (
        <div class="stack stack--tight gap__answer">
          <label class="gap__label" for={inputId}>
            {t("gaps.answerLabel")}
          </label>
          <textarea
            id={inputId}
            class="textarea gap__input"
            rows={3}
            value={draft}
            disabled={readOnly}
            placeholder={t("gaps.answerPlaceholder")}
            onInput={(event) => setDraft((event.target as HTMLTextAreaElement).value)}
          />
          <p class="small muted">{t("gaps.answerNote")}</p>
          <div class="row">
            <button
              type="button"
              class="button"
              disabled={readOnly || saving || !draft.trim()}
              onClick={() => void save()}
            >
              {saving ? t("gaps.adding") : t("gaps.add")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
