/**
 * Saved matches.
 *
 * This is the retention screen: opening a row reloads the match from storage
 * with no model call, and the status select is why someone opens Receipts on a
 * day they are not applying to anything new.
 */

import { EmptyState } from "../components/EmptyState";
import { Screen } from "../components/Screen";
import { TrackerRow } from "../components/TrackerRow";
import { t } from "../i18n";
import { navigate } from "../router";
import { openMatch, removeMatch, tracker, updateMatchStatus } from "../state";

export function Tracker() {
  const entries = tracker.value;

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
              onDelete={(id) => void removeMatch(id)}
            />
          ))}
        </ul>
      )}
    </Screen>
  );
}
