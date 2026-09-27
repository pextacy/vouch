/**
 * "Check how we read your CV."
 *
 * Every later claim cites these line numbers, so a line the parser mangled is
 * worth a few seconds now rather than a confusing citation later. Editing is
 * inline and one line at a time — a full editor would invite rewriting the CV
 * here, which is not what this screen is for.
 */

import { useState } from "preact/hooks";

import { CvLine } from "../components/CvLine";
import { CvSwitch } from "../components/CvSwitch";
import { DocumentSheet } from "../components/DocumentSheet";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { DownloadIcon, PencilIcon } from "../components/Icons";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  clearCheck,
  cv,
  cvExportLines,
  cvExportMode,
  cvExportPhase,
  cvHasAdditions,
  dismissError,
  editCvLine,
  error,
  exportCvDocument,
  hasCv,
  removeCv,
} from "../state";
import type { LineId } from "../lib/types";
import "./CvPreview.css";

export function CvPreview() {
  const [editingId, setEditingId] = useState<LineId | null>(null);
  const [draft, setDraft] = useState("");

  if (!hasCv.value) {
    navigate("/cv/add");
    return null;
  }

  const doc = cv.value!.doc;

  return (
    <Screen heading={t("cv.preview.heading")} lede={t("cv.preview.body")}>
      {error.value && <ErrorNotice error={error.value} onDismiss={dismissError} />}

      <CvSwitch />

      {doc.warnings.length > 0 && (
        <ul class="stack stack--tight">
          {doc.warnings.map((warning) => (
            <li key={warning} class="cvwarning">
              {t(`cv.warning.${warning}`)}
            </li>
          ))}
        </ul>
      )}

      <DocumentSheet title={t("cv.preview.lineCount", { count: doc.lines.length })}>
        {doc.lines.map((line) =>
          editingId === line.id ? (
            <div key={line.id} class="cvedit">
              <label class="visually-hidden" for={`edit-${line.id}`}>
                {t("cv.preview.fix")}
              </label>
              <textarea
                id={`edit-${line.id}`}
                class="textarea cvedit__field"
                value={draft}
                onInput={(event) => setDraft((event.target as HTMLTextAreaElement).value)}
              />
              <div class="row">
                <button
                  type="button"
                  class="button"
                  onClick={() => {
                    void editCvLine(line.id, draft.trim() || line.text);
                    setEditingId(null);
                  }}
                >
                  {t("cv.preview.save")}
                </button>
                <button
                  type="button"
                  class="button button--quiet"
                  onClick={() => setEditingId(null)}
                >
                  {t("cv.preview.cancel")}
                </button>
              </div>
            </div>
          ) : (
            <div key={line.id} class="cvrow">
              <CvLine line={line} />
              <button
                type="button"
                class="button button--quiet cvrow__edit"
                onClick={() => {
                  setDraft(line.text);
                  setEditingId(line.id);
                }}
                aria-label={`${t("cv.preview.fix")} ${line.id}`}
              >
                <PencilIcon size={16} />
              </button>
            </div>
          ),
        )}
      </DocumentSheet>

      {/* The way out.
          Three screens write the user's own sentences into this document —
          a gap answer, an audit finding, a recurring gap — and until this
          button existed not one of them could reach the CV an employer
          reads. The note is part of the feature: what comes out is the plain
          text the parser saw, not the layout the person designed. */}
      <div class="stack stack--tight cvexport">
        <div class="row">
          <button
            type="button"
            class="button button--secondary"
            disabled={cvExportPhase.value === "running"}
            onClick={() => void exportCvDocument("full")}
          >
            <DownloadIcon size={16} />
            {cvExportPhase.value === "running" && cvExportMode.value === "full"
              ? t("export.preparing")
              : t("cv.export.download")}
          </button>
          {cvHasAdditions.value && (
            <button
              type="button"
              class="button button--quiet"
              disabled={cvExportPhase.value === "running"}
              onClick={() => void exportCvDocument("additions")}
            >
              {cvExportPhase.value === "running" && cvExportMode.value === "additions"
                ? t("export.preparing")
                : t("cv.export.additions")}
            </button>
          )}
        </div>
        {cvExportPhase.value === "done" ? (
          <p class="small muted" aria-live="polite">
            {cvExportMode.value === "additions"
              ? t("cv.export.doneAdditions", { count: cvExportLines.value })
              : t("cv.export.done", { count: cvExportLines.value })}
          </p>
        ) : (
          <p class="small muted">{t("cv.export.note")}</p>
        )}
      </div>

      <div class="row">
        <button type="button" class="button" onClick={() => navigate("/new")}>
          {t("cv.preview.confirm")}
        </button>
        {/* The audit belongs here rather than behind a menu: this is the one
            moment the user is already looking at their own CV and asking
            whether it holds up. */}
        <button
          type="button"
          class="button button--secondary"
          onClick={() => navigate("/cv/audit")}
        >
          {t("cv.preview.audit")}
        </button>
        {/* The other thing this document is for. No posting involved: a
            profile has to be true on any day, to any reader. */}
        <button
          type="button"
          class="button button--quiet"
          onClick={() => navigate("/cv/profile")}
        >
          {t("cv.preview.profile")}
        </button>
        {/* The audit reads this CV; this reads the document that is actually
            being sent, which after an export and an evening in Word is not
            the same document at all. */}
        <button
          type="button"
          class="button button--secondary"
          onClick={() => {
            clearCheck();
            navigate("/check");
          }}
        >
          {t("cv.preview.check")}
        </button>
        <button
          type="button"
          class="button button--quiet"
          onClick={() => {
            void removeCv();
            navigate("/cv/add");
          }}
        >
          {t("cv.preview.replace")}
        </button>
      </div>
    </Screen>
  );
}
