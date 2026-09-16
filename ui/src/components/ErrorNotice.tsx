/**
 * An error the user can act on.
 *
 * No apology, no "oops", no stack trace: what happened, and what to do about
 * it. Retry only appears when retrying can actually help — offering it on a
 * 3 MB PDF would just waste the user's time twice.
 */

import { t } from "../i18n";
import type { EngineError } from "../lib/types";
import "./ErrorNotice.css";

interface ErrorNoticeProps {
  error: EngineError;
  onRetry?: () => void;
  onDismiss?: () => void;
}

export function ErrorNotice({ error, onRetry, onDismiss }: ErrorNoticeProps) {
  const message = t(`error.${error.code}`);
  if (!message) return null;
  return (
    <div class="notice" role="alert">
      <p class="notice__text">{message}</p>
      <div class="row">
        {error.retriable && onRetry && (
          <button type="button" class="button button--secondary" onClick={onRetry}>
            {t("common.retry")}
          </button>
        )}
        {onDismiss && (
          <button type="button" class="button button--quiet" onClick={onDismiss}>
            {t("common.close")}
          </button>
        )}
      </div>
    </div>
  );
}
