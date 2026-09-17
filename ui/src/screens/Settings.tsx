/**
 * "Your data."
 *
 * Deleting everything is one click plus one confirmation, and the confirmation
 * says exactly what goes. An app that holds someone's CV should make leaving
 * easy to find and impossible to misread.
 */

import { useState } from "preact/hooks";

import { ConfirmDialog } from "../components/ConfirmDialog";
import { Screen } from "../components/Screen";
import { TrashIcon } from "../components/Icons";
import { locale, t } from "../i18n";
import {
  changeLocale,
  chooseTheme,
  cv,
  deleteEverything,
  theme,
  tracker,
} from "../state";
import type { Locale } from "../lib/types";
import type { Theme } from "../state";
import "./Settings.css";

const LOCALES: Locale[] = ["en", "tr"];
const THEMES: Theme[] = ["system", "light", "dark"];

export function Settings() {
  const [confirming, setConfirming] = useState(false);
  const stored = cv.value;

  return (
    <Screen heading={t("settings.heading")} lede={t("settings.body")}>
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

      <div class="row">
        <button type="button" class="button button--danger" onClick={() => setConfirming(true)}>
          <TrashIcon size={16} />
          {t("settings.delete")}
        </button>
      </div>

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
