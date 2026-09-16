/**
 * One saved application.
 *
 * Opening a row reloads the match from storage — no model call, no new
 * qualified run. The status select is the reason people come back.
 */

import { StatusSelect } from "./StatusSelect";
import { TabIcon, TrashIcon } from "./Icons";
import { t } from "../i18n";
import type { ApplicationStatus, TrackerEntry } from "../lib/types";
import "./TrackerRow.css";

interface TrackerRowProps {
  entry: TrackerEntry;
  onOpen: (id: string) => void;
  onStatus: (id: string, status: ApplicationStatus) => void;
  onDelete: (id: string) => void;
}

export function TrackerRow({ entry, onOpen, onStatus, onDelete }: TrackerRowProps) {
  const role = entry.role ?? t("tracker.untitledRole");
  const company = entry.company ?? t("tracker.unknownCompany");

  return (
    <li class="trackrow">
      <button type="button" class="trackrow__open" onClick={() => onOpen(entry.id)}>
        <TabIcon size={16} />
        <span class="trackrow__text">
          <span class="trackrow__role">{role}</span>
          <span class="trackrow__company small muted">{company}</span>
        </span>
      </button>

      <span class="trackrow__coverage small muted numeric">
        {t("tracker.coverage", { strong: entry.strong, total: entry.total })}
      </span>

      <StatusSelect value={entry.status} onChange={(status) => onStatus(entry.id, status)} />

      <button
        type="button"
        class="button button--quiet trackrow__delete"
        onClick={() => onDelete(entry.id)}
        aria-label={`${t("tracker.delete")} — ${role}`}
      >
        <TrashIcon size={16} />
      </button>
    </li>
  );
}
