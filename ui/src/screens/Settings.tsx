/**
 * "Your data."
 *
 * Deleting everything is one click plus one confirmation, and the confirmation
 * says exactly what goes. An app that holds someone's CV should make leaving
 * easy to find and impossible to misread.
 */

import { useState } from "preact/hooks";

import { ConfirmDialog } from "../components/ConfirmDialog";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { DownloadIcon, TrashIcon } from "../components/Icons";
import { locale, t } from "../i18n";
import {
  activeCvId,
  changeLocale,
  chooseTheme,
  cv,
  cvExportPhase,
  cvProfiles,
  deleteEverything,
  dismissError,
  error,
  exportCvDocument,
  matchesForCv,
  removeCvProfile,
  renameCv,
  theme,
  tracker,
  useCv,
} from "../state";
import type { Locale } from "../lib/types";
import type { Theme } from "../state";
import "./Settings.css";

const LOCALES: Locale[] = ["en", "tr"];
const THEMES: Theme[] = ["system", "light", "dark"];

export function Settings() {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const stored = cv.value;
  const profiles = cvProfiles.value;

  return (
    <Screen heading={t("settings.heading")} lede={t("settings.body")}>
      {/* A delete or an export that failed leaves this screen looking exactly
          like one that worked. `deleteEverything` deliberately keeps the data
          on screen rather than reporting a delete it did not do — and that
          decision is only honest if the reason is visible. */}
      {error.value && <ErrorNotice error={error.value} onDismiss={dismissError} />}
      <dl class="facts">
        <div class="facts__row">
          <dt class="facts__key">{t("nav.cv")}</dt>
          <dd class="facts__value">
            {stored
              ? t("settings.cvStored", { when: formatDate(stored.updated_at) })
              : t("settings.cvNone")}
          </dd>
        </div>
        <div class="facts__row">
          <dt class="facts__key">{t("nav.matches")}</dt>
          <dd class="facts__value">{t("settings.matchCount", { count: tracker.value.length })}</dd>
        </div>
      </dl>

      {/* One CV needs no list: the row above already says when it was saved.
          More than one and this is where they are named and removed, because
          a name the user cannot change is the app's word for their career. */}
      {profiles.length > 1 && (
        <section class="stack stack--tight cvlist">
          <h2 class="cvlist__heading">{t("cv.profiles.heading")}</h2>
          <ul class="cvlist__items">
            {profiles.map((profile) => (
              <li key={profile.id} class="cvlist__item">
                <input
                  class="input cvlist__name"
                  value={profile.name}
                  aria-label={t("cv.profiles.nameLabel")}
                  onChange={(event) =>
                    void renameCv(profile.id, (event.target as HTMLInputElement).value)
                  }
                />
                {/* The three trailing controls travel together, so a phone
                    wraps them under the name as one row rather than leaving
                    the delete button stranded on a line of its own. */}
                <div class="cvlist__actions">
                  <span class="small muted">
                    {matchesForCv(profile.id) === 1
                      ? t("cv.profiles.countOne")
                      : t("cv.profiles.count", { count: matchesForCv(profile.id) })}
                  </span>
                  {profile.id === activeCvId.value ? (
                    <span class="small muted">{t("cv.profiles.open")}</span>
                  ) : (
                    <button
                      type="button"
                      class="button button--quiet"
                      onClick={() => void useCv(profile.id)}
                    >
                      {t("cv.profiles.use")}
                    </button>
                  )}
                  <button
                    type="button"
                    class="button button--quiet cvlist__delete"
                    onClick={() => setDeleting(profile.id)}
                    aria-label={`${t("cv.profiles.delete")} — ${profile.name}`}
                  >
                    <TrashIcon size={16} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <fieldset class="choice">
        <legend class="choice__legend">{t("settings.language")}</legend>
        {LOCALES.map((value) => (
          <label
            key={value}
            class={`choice__option${locale.value === value ? " choice__option--on" : ""}`}
          >
            <input
              class="visually-hidden"
              type="radio"
              name="locale"
              checked={locale.value === value}
              onChange={() => void changeLocale(value)}
            />
            {value === "en" ? "English" : "Türkçe"}
          </label>
        ))}
      </fieldset>

      <fieldset class="choice">
        <legend class="choice__legend">{t("settings.theme")}</legend>
        {THEMES.map((value) => (
          <label
            key={value}
            class={`choice__option${theme.value === value ? " choice__option--on" : ""}`}
          >
            <input
              class="visually-hidden"
              type="radio"
              name="theme"
              checked={theme.value === value}
              onChange={() => void chooseTheme(value)}
            />
            {t(`settings.theme.${value}`)}
          </label>
        ))}
      </fieldset>

      {/* Leaving should be as easy as arriving, and taking the document with
          you is part of leaving. The same export as the CV screen. */}
      {stored && (
        <div class="row">
          <button
            type="button"
            class="button button--secondary"
            disabled={cvExportPhase.value === "running"}
            onClick={() => void exportCvDocument("full")}
          >
            <DownloadIcon size={16} />
            {cvExportPhase.value === "running" ? t("export.preparing") : t("cv.export.download")}
          </button>
        </div>
      )}

      <div class="row">
        <button type="button" class="button button--danger" onClick={() => setConfirming(true)}>
          <TrashIcon size={16} />
          {t("settings.delete")}
        </button>
      </div>

      {/* Deleting one CV takes its applications with it, and the sentence says
          so with the number in it: a record the user cannot open is not a
          record they kept. */}
      <ConfirmDialog
        open={deleting !== null}
        title={t("cv.profiles.deleteTitle")}
        body={t("cv.profiles.deleteBody", {
          count: deleting ? matchesForCv(deleting) : 0,
        })}
        confirmLabel={t("cv.profiles.delete")}
        onCancel={() => setDeleting(null)}
        onConfirm={() => {
          const id = deleting;
          setDeleting(null);
          if (id) void removeCvProfile(id);
        }}
      />

      <ConfirmDialog
        open={confirming}
        title={t("settings.deleteConfirmTitle")}
        body={t("settings.deleteConfirmBody")}
        confirmLabel={t("settings.deleteConfirmAction")}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          void deleteEverything();
        }}
      />
    </Screen>
  );
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat(locale.value, { dateStyle: "medium" }).format(new Date(iso));
  } catch {
    return iso.slice(0, 10);
  }
}
