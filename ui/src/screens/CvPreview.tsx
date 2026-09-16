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
import { DocumentSheet } from "../components/DocumentSheet";
import { Screen } from "../components/Screen";
import { PencilIcon } from "../components/Icons";
import { t } from "../i18n";
import { navigate } from "../router";
import { cv, editCvLine, hasCv, removeCv } from "../state";
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

      <div class="row">
        <button type="button" class="button" onClick={() => navigate("/new")}>
          {t("cv.preview.confirm")}
        </button>
        <button
          type="button"
          class="button button--secondary"
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
