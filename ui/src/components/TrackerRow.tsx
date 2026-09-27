/**
 * One saved application.
 *
 * Opening a row reloads the match from storage — no model call, no new
 * qualified run. The status select is the reason people come back.
 */

import { StatusSelect } from "./StatusSelect";
import { TabIcon, TrashIcon } from "./Icons";
import { t } from "../i18n";
import { daysSilent, hasGoneQuiet } from "../lib/followup";
import type { ApplicationStatus, TrackerEntry } from "../lib/types";
import "./TrackerRow.css";

interface TrackerRowProps {
  entry: TrackerEntry;
  onOpen: (id: string) => void;
  onPrepare: (id: string) => void;
  onSince: (id: string) => void;
  onFollowup: (id: string) => void;
  onStatus: (id: string, status: ApplicationStatus) => void;
  onDelete: (id: string) => void;
}

export function TrackerRow({
  entry,
  onOpen,
  onPrepare,
  onSince,
  onFollowup,
  onStatus,
  onDelete,
}: TrackerRowProps) {
  const role = entry.role ?? t("tracker.untitledRole");
  const quiet = hasGoneQuiet(entry) ? daysSilent(entry) : null;
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

      {/* Marking a row *Interview* used to change a word and nothing else.
          This is what it changes now, and it appears only on the rows where
          there is an interview to prepare for. */}
      {entry.status === "interview" && (
        <button
          type="button"
          class="button button--quiet trackrow__prepare"
          onClick={() => onPrepare(entry.id)}
        >
          {t("tracker.prepare")}
        </button>
      )}

      {/* A sent application is the one the app used to have nothing more to
          say about, while three other screens kept adding lines to the CV
          underneath it. It appears on the rows that have been sent, because
          that is the only place the question means anything. */}
      {(entry.status === "applied" || entry.status === "interview") && (
        <button
          type="button"
          class="button button--quiet trackrow__since"
          onClick={() => onSince(entry.id)}
        >
          {t("tracker.since")}
        </button>
      )}

      {/* The app knows the day it was marked sent and nothing about whether
          anyone replied, so the line says only the first — and it says it
          only once the wait is past the median, not before (`lib/followup`). */}
      {quiet !== null && (
        <span class="trackrow__quiet small muted">
          {quiet === 1 ? t("tracker.quietDay") : t("tracker.quiet", { count: quiet })}
        </span>
      )}
      {quiet !== null && (
        <button
          type="button"
          class="button button--quiet trackrow__followup"
          onClick={() => onFollowup(entry.id)}
        >
          {t("tracker.followup")}
        </button>
      )}

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
