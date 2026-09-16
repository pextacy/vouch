/**
 * Where an application stands. A native select: five options, and the
 * platform's own control is the one everybody already knows how to use.
 */

import { t } from "../i18n";
import type { ApplicationStatus } from "../lib/types";
import "./StatusSelect.css";

const OPTIONS: ApplicationStatus[] = ["drafted", "applied", "interview", "offer", "closed"];

interface StatusSelectProps {
  value: ApplicationStatus;
  onChange: (status: ApplicationStatus) => void;
}

export function StatusSelect({ value, onChange }: StatusSelectProps) {
  return (
    <label class="statusselect">
      <span class="visually-hidden">{t("tracker.status")}</span>
      <select
        class="statusselect__control"
        value={value}
        onChange={(event) => onChange((event.target as HTMLSelectElement).value as ApplicationStatus)}
      >
        {OPTIONS.map((option) => (
          <option key={option} value={option}>
            {t(`tracker.status.${option}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
