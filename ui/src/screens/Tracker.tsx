/**
 * Saved matches.
 *
 * This is the retention screen: opening a row reloads the match from storage
 * with no model call, and the status select is why someone opens Receipts on a
 * day they are not applying to anything new.
 */

import { useState } from "preact/hooks";

import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { Screen } from "../components/Screen";
import { TrackerRow } from "../components/TrackerRow";
import { t } from "../i18n";
import { navigate } from "../router";
import { openMatch, removeMatch, tracker, updateMatchStatus } from "../state";

export function Tracker() {
  const entries = tracker.value;
  // Deleting a row cannot be undone and the match behind it cost a real
  // analysis, so the delete button asks first — the same rule as "Your data",
  // and it sits one tap from a status dropdown on a phone.
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  return (
    <Screen heading={t("tracker.heading")}>
      {entries.length === 0 ? (
        <EmptyState
          text={t("tracker.empty")}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      ) : (
        <ul class="list">
          {entries.map((entry) => (
            <TrackerRow
              key={entry.id}
              entry={entry}
              onOpen={(id) => void openMatch(id)}
              onStatus={(id, status) => void updateMatchStatus(id, status)}
              onDelete={(id) => setPendingDelete(id)}
            />
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title={t("tracker.deleteConfirmTitle")}
        body={t("tracker.deleteConfirmBody")}
        confirmLabel={t("tracker.delete")}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          const id = pendingDelete;
          setPendingDelete(null);
          if (id) void removeMatch(id);
        }}
      />
    </Screen>
  );
}
