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
import { MIN_MATCHES as LEDGER_MIN } from "../lib/ledger";
import "./Tracker.css";
import {
  openBrief,
  openFollowup,
  openMatch,
  openSince,
  removeMatch,
  tracker,
  updateMatchStatus,
} from "../state";

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
        <>
          {/* One action above the list, because it is the only one of the
              four that asks the user to do something rather than to read:
              which of these applications the CV has since gained an answer
              for. The three readings sit under the list (below). */}
          <div class="row tracker__actions">
            <button
              type="button"
              class="button button--secondary"
              onClick={() => navigate("/worth")}
            >
              {t("tracker.worth")}
            </button>
          </div>
        <ul class="list">
          {entries.map((entry) => (
            <TrackerRow
              key={entry.id}
              entry={entry}
              onOpen={(id) => void openMatch(id)}
              onPrepare={(id) => void openBrief(id)}
              onSince={(id) => void openSince(id)}
              onFollowup={(id) => void openFollowup(id)}
              onStatus={(id, status) => void updateMatchStatus(id, status)}
              onDelete={(id) => setPendingDelete(id)}
            />
          ))}
        </ul>

        {/* The screens that read across the shelf rather than change it, set
            as a group after the list they are drawn from: four peer buttons
            above the tracker turned its own rows into the second thing on
            the page. Each appears when it has something to say. */}
        {entries.length > 1 && (
          <section class="stack stack--tight tracker__reads">
            <h2 class="tracker__readsHeading">{t("tracker.readsHeading")}</h2>
            <ul class="tracker__readsList">
              <li>
                <button
                  type="button"
                  class="button button--quiet"
                  onClick={() => navigate("/recurring")}
                >
                  {t("tracker.recurring")}
                </button>
              </li>
              <li>
                <button
                  type="button"
                  class="button button--quiet"
                  onClick={() => navigate("/compare")}
                >
                  {t("tracker.compare")}
                </button>
              </li>
              {entries.length >= LEDGER_MIN && (
                <li>
                  <button
                    type="button"
                    class="button button--quiet"
                    onClick={() => navigate("/cv/ledger")}
                  >
                    {t("tracker.ledger")}
                  </button>
                </li>
              )}
            </ul>
          </section>
        )}
        </>
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
