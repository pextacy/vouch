/**
 * Add a CV: upload a file, or paste the text.
 *
 * Paste is not a fallback tucked away at the bottom — for a two-column PDF or
 * a scanned export it is the path that works, and the error copy sends people
 * straight here.
 */

import { useState } from "preact/hooks";

import { DropZone } from "../components/DropZone";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { addCvFromFile, addCvFromText, cvPhase, cvUpload, dismissError, error } from "../state";
import "./AddCv.css";

export function AddCv() {
  const [text, setText] = useState("");
  const busy = cvPhase.value === "running";
  const upload = cvUpload.value;

  return (
    <Screen heading={t("cv.add.heading")} lede={t("cv.add.body")}>
      {error.value && <ErrorNotice error={error.value} onDismiss={dismissError} />}

      <DropZone
        onFile={(file) => void addCvFromFile(file)}
        onTooLarge={() =>
          (error.value = {
            code: "file_too_large",
            message: "file over 2 MB",
            retriable: false,
          })
        }
        disabled={busy}
      />

      {busy && (
        <p class="muted" aria-live="polite">
          {upload && upload.total > 1
            ? `${t("cv.add.uploading")} ${upload.sent}/${upload.total}`
            : t("cv.add.reading")}
        </p>
      )}

      <div class="field">
        <label class="field__label" for="cv-text">
          {t("cv.add.pasteLabel")}
        </label>
        <textarea
          id="cv-text"
          class="textarea"
          placeholder={t("cv.add.pastePlaceholder")}
          value={text}
          disabled={busy}
          onInput={(event) => setText((event.target as HTMLTextAreaElement).value)}
        />
        <div class="row">
          <button
            type="button"
            class="button"
            disabled={busy || text.trim().length < 200}
            onClick={() => void addCvFromText(text)}
          >
            {t("cv.add.pasteAction")}
          </button>
        </div>
      </div>
    </Screen>
  );
}
