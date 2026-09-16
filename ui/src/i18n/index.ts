/**
 * Strings, in English and Turkish.
 *
 * Both files carry the same keys; `tests/ui/i18n.spec.ts` fails the build if
 * one drifts. A missing key falls back to English rather than rendering the
 * key itself — a user should never see `tailor.dropped` on screen.
 */

import { signal } from "@preact/signals";

import en from "./en.json";
import tr from "./tr.json";
import type { Locale } from "../lib/types";

type Dictionary = Record<string, string>;

const DICTIONARIES: Record<Locale, Dictionary> = { en, tr };

export const locale = signal<Locale>("en");

export function setLocale(next: Locale): void {
  locale.value = next;
  if (typeof document !== "undefined") {
    document.documentElement.lang = next;
  }
}

/** Pick a starting locale from the browser, defaulting to English. */
export function detectLocale(): Locale {
  if (typeof navigator === "undefined") return "en";
  return navigator.language?.toLowerCase().startsWith("tr") ? "tr" : "en";
}

export function t(key: string, values?: Record<string, string | number>): string {
  const dictionary = DICTIONARIES[locale.value];
  const template = dictionary[key] ?? DICTIONARIES.en[key] ?? key;
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}

/** The summary sentence, composed here so it follows the interface language. */
export function summarySentence(total: number, evidenced: number, mustMissing: number): string {
  const head = t("summary.sentence", { total, evidenced });
  if (mustMissing === 1) return `${head} ${t("summary.mustMissing.one")}`;
  if (mustMissing > 1) return `${head} ${t("summary.mustMissing.many", { count: mustMissing })}`;
  return head;
}

export const DICTIONARY_KEYS = { en: Object.keys(en), tr: Object.keys(tr) };
