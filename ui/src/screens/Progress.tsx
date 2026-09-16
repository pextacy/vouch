/**
 * The wait.
 *
 * Requirements appear as they are extracted and get marked as evidence is
 * found, so the screen is showing the work rather than a spinner over it. No
 * percentage: the honest unit here is the stage, and a number that leaps from
 * 30 to 70 teaches people not to believe the next one.
 */

import { ErrorNotice } from "../components/ErrorNotice";
import { MarkerHighlight } from "../components/MarkerHighlight";
import { ProgressLedger } from "../components/ProgressLedger";
import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { navigate } from "../router";
import { arrivedEvidence, cancelMatch, dismissError, error, matchPhase, progress, startMatch } from "../state";
import type { Status } from "../lib/types";
import "./Progress.css";

export function Progress() {
  const event = progress.value;
  const heading = event && event.stage !== "normalize" ? t("progress.checking") : t("progress.reading");
  const requirements = event?.partial?.requirements ?? [];
  const matched = new Map(
    (event?.partial?.matched ?? []).map((item) => [item.id, item.status as Status]),
  );

  if (matchPhase.value === "error" && error.value) {
    return (
      <Screen heading={t("progress.reading")}>
        <ErrorNotice
          error={error.value}
          onRetry={() => void startMatch()}
          onDismiss={() => {
            dismissError();
            navigate("/new");
          }}
        />
      </Screen>
    );
  }

  return (
    <Screen heading={heading}>
      <ProgressLedger progress={event} />

      {requirements.length > 0 && (
        <ul class="found" aria-live="polite">
          {requirements.map((requirement, index) => {
            const status = matched.get(requirement.id);
            const arrived = arrivedEvidence.value.has(requirement.id);
            return (
              <li key={requirement.id} class="found__item">
                {status && status !== "missing" ? (
                  <MarkerHighlight status={status} animate={arrived} sweepIndex={index}>
                    {requirement.text}
                  </MarkerHighlight>
                ) : (
                  <span class={status === "missing" ? "muted" : undefined}>{requirement.text}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div class="row">
        <button
          type="button"
          class="button button--secondary"
          onClick={() => {
            cancelMatch();
            navigate("/new");
          }}
        >
          {t("progress.cancel")}
        </button>
      </div>
    </Screen>
  );
}
