/**
 * File input with a drop target.
 *
 * A plain `<input type="file">` styled as a large label, so keyboard and
 * screen-reader users get the real control and everyone else gets the drop
 * area. The size check happens here rather than after a two-megabyte upload.
 */

import { useState } from "preact/hooks";

import { UploadIcon } from "./Icons";
import { t } from "../i18n";
import { MAX_FILE_BYTES } from "../lib/engine";
import "./DropZone.css";

interface DropZoneProps {
  onFile: (file: File) => void;
  onTooLarge: () => void;
  disabled?: boolean;
}

export function DropZone({ onFile, onTooLarge, disabled }: DropZoneProps) {
  const [over, setOver] = useState(false);

  function take(file: File | undefined | null): void {
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      onTooLarge();
      return;
    }
    onFile(file);
  }

  return (
    <label
      class={`drop${over ? " drop--over" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        take(event.dataTransfer?.files?.[0]);
      }}
    >
      <input
        class="visually-hidden"
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        disabled={disabled}
        onChange={(event) => {
          const input = event.target as HTMLInputElement;
          take(input.files?.[0]);
          input.value = "";
        }}
      />
      <UploadIcon size={20} />
      <span class="drop__title">{t("cv.add.upload")}</span>
      <span class="drop__hint small muted">{t("cv.add.dropHint")}</span>
    </label>
  );
}
