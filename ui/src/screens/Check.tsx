/**
 * The verifier, pointed at a document Vouch did not write.
 *
 * Every other screen checks text this app produced. That guarantee ends where
 * the export does: someone pastes their tailored bullets into the CV they
 * designed in Word, adds a line at 1 a.m., and sends it — or arrives with a
 * CV another tool "improved" for them and has never read closely since.
 * Neither document was checked by anything, and both are the one an employer
 * reads.
 *
 * So the user pastes it and gets the same verdict `tailor` is held to, per
 * sentence, with the words quoted back. The app cannot edit their file and
 * does not try. It offers the one honest repair it has — say where it
 * happened, and the sentence becomes a CV line, verbatim — and says the rest
 * plainly: if it did not happen, take it out.
 *
 * No model, no tokens, nothing stored. The document arrives, is read, and is
 * gone the moment the screen is left.
 */

import { useState } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { MarkerHighlight } from "../components/MarkerHighlight";
import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  activeCv,
  answerCheckedLine,
  answeredChecks,
  checkAgainst,
  checkDraft,
  checkPhase,
  checkResult,
  checkedKey,
  clearCheck,
  currentMatch,
  dismissError,
  error,
  runCheck,
  showingExample,
} from "../state";
import type { CheckedLine } from "../lib/types";
import "./Check.css";

export function Check() {
  const doc = activeCv();
  const result = checkResult.value;
  const phase = checkPhase.value;
  const match = currentMatch.value;
  const draft = checkDraft.value;

  if (!doc) {
    navigate("/cv/add");
    return null;
  }

  const posting = match?.posting.title ?? match?.posting.company ?? null;
  const applied = checkAgainst.value === match?.id;

  return (
    <Screen heading={t("check.heading")} lede={t("check.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runCheck()} onDismiss={dismissError} />
      )}

      {!result && (
        <div class="stack check__form">
          <label class="check__label" for="check-document">
            {t("check.pasteLabel")}
          </label>
          <textarea
            id="check-document"
            class="textarea check__input"
            rows={12}
            value={draft}
            placeholder={t("check.pastePlaceholder")}
            onInput={(event) => {
              checkDraft.value = (event.target as HTMLTextAreaElement).value;
            }}
          />

          {/* An application is context, not the subject: the employer being
              written to is the address on the envelope. Saying which words
              were set aside is the difference between that and a blind spot. */}
          {posting && (
            <p class="small muted check__context">
              {applied
                ? t("check.forPosting", { posting })
                : t("check.withoutPosting")}{" "}
              <button
                type="button"
                class="button button--quiet check__contextToggle"
                onClick={() => {
                  checkAgainst.value = applied ? null : (match?.id ?? null);
                }}
              >
                {applied ? t("check.dropPosting") : t("check.usePosting", { posting })}
              </button>
            </p>
          )}

          <div class="row">
            <button
              type="button"
              class="button check__run"
              disabled={!draft.trim() || phase === "running"}
              onClick={() => void runCheck()}
            >
              {phase === "running" ? t("check.running") : t("check.run")}
            </button>
            <button type="button" class="button button--secondary" onClick={() => navigate("/cv/preview")}>
              {t("check.backToCv")}
            </button>
          </div>
          <p class="small muted check__privacy">{t("check.privacy")}</p>
        </div>
      )}

      {result && (
        <>
          <p class="check__count" aria-live="polite">
            {result.unbacked === 0
              ? t("check.clean", { checked: result.checked })
              : result.unbacked === 1
                ? t("check.countOne", { checked: result.checked })
                : t("check.countMany", { count: result.unbacked, checked: result.checked })}
          </p>

          {result.masked.length > 0 && (
            <p class="small muted check__masked">
              {t("check.maskedNote", { terms: result.masked.join(", ") })}
            </p>
          )}

          {result.truncated && <p class="small muted">{t("check.truncated")}</p>}

          {result.unbacked === 0 ? (
            <EmptyState
              text={t("check.cleanNote")}
              action={
                <button type="button" class="button" onClick={clearCheck}>
                  {t("check.another")}
                </button>
              }
            />
          ) : (
            <>
              <ul class="list">
                {result.flagged.map((line) => (
                  <FlaggedLine
                    key={checkedKey(line)}
                    line={line}
                    answered={answeredChecks.value.has(checkedKey(line))}
                    readOnly={showingExample.value}
                  />
                ))}
              </ul>
              {result.unbacked > result.flagged.length && (
                <p class="small muted">
                  {t("check.more", { count: result.unbacked - result.flagged.length })}
                </p>
              )}
            </>
          )}

          <div class="row">
            <button type="button" class="button button--secondary" onClick={clearCheck}>
              {t("check.another")}
            </button>
            <button type="button" class="button button--quiet" onClick={() => navigate("/cv/preview")}>
              {t("check.backToCv")}
            </button>
          </div>
        </>
      )}
    </Screen>
  );
}

interface FlaggedLineProps {
  line: CheckedLine;
  answered: boolean;
  readOnly: boolean;
}

function FlaggedLine({ line, answered, readOnly }: FlaggedLineProps) {
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const inputId = `checked-${line.index}`;

  async function save(): Promise<void> {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      await answerCheckedLine(line, draft);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li class="checked">
      {/* The document's own sentence, on a document surface and in the
          document typeface: this is the thing being talked about, and the user
          has to recognise it in their own file at a glance. */}
      <blockquote class="checked__quote">{line.text}</blockquote>

      <p class="checked__claims">
        {t("check.cannotBack")}{" "}
        {line.claims.map((claim, index) => (
          <span key={`${claim.kind}-${claim.surface}`} class="checked__claim">
            {index > 0 && " "}
            <MarkerHighlight status="missing">{claim.surface}</MarkerHighlight>
          </span>
        ))}
      </p>

      {answered ? (
        <p class="checked__saved">{t("check.saved")}</p>
      ) : (
        <div class="stack stack--tight checked__answer">
          <label class="checked__label" for={inputId}>
            {t("check.answerLabel")}
          </label>
          <textarea
            id={inputId}
            class="textarea checked__input"
            rows={3}
            value={draft}
            disabled={readOnly}
            placeholder={t("check.answerPlaceholder")}
            onInput={(event) => setDraft((event.target as HTMLTextAreaElement).value)}
          />
          <p class="small muted">{t("check.answerNote")}</p>
          <div class="row">
            <button
              type="button"
              class="button"
              disabled={readOnly || saving || !draft.trim()}
              onClick={() => void save()}
            >
              {saving ? t("check.adding") : t("check.add")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
