/**
 * Shown when the bundle is running without the Anna host.
 *
 * It matters that this is unmissable: everything below it is a recorded
 * fixture, and an app whose entire promise is "we only show you what is real"
 * cannot be ambiguous about when it is showing something that is not.
 */

import { t } from "../i18n";
import "./PreviewBanner.css";

export function PreviewBanner() {
  return (
    <div class="preview" role="status">
      <strong class="preview__title">{t("preview.title")}</strong>
      <span class="preview__body">{t("preview.body")}</span>
    </div>
  );
}
