/**
 * What an interviewer will press on — in the CV the user already has.
 *
 * Every verifier in this codebase guards the text the app *writes*. This is the
 * only screen that turns the same suspicion on the document the user arrived
 * with, which is where their real interview risk lives: a tool in the skills
 * list that no job ever shows them using, a seniority word the roles below do
 * not carry, two jobs that overlap by three years.
 *
 * It states no verdict. A finding says what could not be found and offers the
 * same loop the gap questions do — the person says where it actually happened,
 * their sentence goes into the CV verbatim, and the audit runs again so the
 * finding clears because it was answered, not because it was dismissed.
 *
 * No model, no tokens, and no posting required: this is the one screen that
 * works the moment a CV exists.
 */

import { useEffect, useState } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  activeCv,
  answerFinding,
  answeredFindings,
  auditPhase,
  auditResult,
  dismissError,
  error,
  findingKey,
  runAudit,
  showingExample,
} from "../state";
import type { CvFinding } from "../lib/types";
import "./CvAudit.css";

export function CvAudit() {
  const result = auditResult.value;
  const phase = auditPhase.value;
  // The recorded example has a CV of its own, and this screen is worth showing
  // there: it is the one thing the app can do before a posting exists.
  const doc = activeCv();

  useEffect(() => {
    if (doc && !result && phase === "idle") void runAudit();
  }, [doc?.hash, result, phase]);

  if (!doc) {
    navigate("/cv/add");
    return null;
  }

  return (
    <Screen heading={t("audit.heading")} lede={t("audit.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runAudit()} onDismiss={dismissError} />
      )}

      {phase === "running" && !result && (
        <p class="muted" aria-live="polite">
          {t("audit.running")}
        </p>
      )}

      {/* Nothing found is the good outcome and it gets said properly, rather
          than leaving a blank page that reads like a failed load. */}
      {result && result.findings.length === 0 && (
        <EmptyState
          text={t("audit.clean")}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      )}

      {result && result.findings.length > 0 && (
        <>
          <p class="audit__count" aria-live="polite">
            {result.findings.length === 1
              ? t("audit.countOne")
              : t("audit.countMany", { count: result.findings.length })}
          </p>
          <ul class="list">
            {result.findings.map((finding) => (
              <FindingCard
                key={findingKey(finding)}
                finding={finding}
                answered={answeredFindings.value.has(findingKey(finding))}
                readOnly={showingExample.value}
              />
            ))}
          </ul>
        </>
      )}

      <div class="row">
        <button type="button" class="button button--secondary" onClick={() => navigate("/cv/preview")}>
          {t("audit.backToCv")}
        </button>
      </div>
    </Screen>
  );
}

interface FindingCardProps {
  finding: CvFinding;
  answered: boolean;
  readOnly: boolean;
}

function FindingCard({ finding, answered, readOnly }: FindingCardProps) {
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const inputId = `finding-${finding.kind}-${finding.subject.replace(/\W+/g, "-")}`;
  // `surface` is the CV's own spelling; `subject` is the canonical term the
  // engine compared with, and it is not what a person should be shown.
  const subject = finding.surface;

  async function save(): Promise<void> {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      await answerFinding(finding, draft);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li class="finding">
      <h2 class="finding__claim">{t(`audit.kind.${finding.kind}`, { subject })}</h2>
      <p class="finding__ask">{t(`audit.ask.${finding.kind}`, { subject })}</p>

      {finding.line_ids.length > 0 && (
        <div class="row finding__chips">
          {finding.line_ids.map((line) => (
            <SourceChip key={line} line={line} />
          ))}
        </div>
      )}

      {/* A date conflict is not something to answer in prose — it is either
          correct and worth being ready to explain, or a typo to fix on the CV
          itself. Offering an answer box would invite an explanation nobody
          reading the CV will ever see. */}
      {finding.kind === "date_conflict" ? (
        <div class="row">
          <button
            type="button"
            class="button button--quiet"
            onClick={() => navigate("/cv/preview")}
          >
            {t("audit.fixDates")}
          </button>
        </div>
      ) : answered ? (
        <p class="finding__saved">{t("audit.saved")}</p>
      ) : (
        <div class="stack stack--tight finding__answer">
          <label class="finding__label" for={inputId}>
            {t("audit.answerLabel")}
          </label>
          <textarea
            id={inputId}
            class="textarea finding__input"
            rows={3}
            value={draft}
            disabled={readOnly}
            placeholder={t("audit.answerPlaceholder")}
            onInput={(event) => setDraft((event.target as HTMLTextAreaElement).value)}
          />
          <p class="small muted">{t("audit.answerNote")}</p>
          <div class="row">
            <button
              type="button"
              class="button"
              disabled={readOnly || saving || !draft.trim()}
              onClick={() => void save()}
            >
              {saving ? t("audit.adding") : t("audit.add")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
