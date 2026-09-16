/**
 * Strings.
 *
 * The parity test is the important one: a key present in English and missing
 * in Turkish renders the English sentence to a Turkish user, which looks like
 * a bug and reads like carelessness.
 */

import { describe, expect, it } from "vitest";

import en from "../../ui/src/i18n/en.json";
import tr from "../../ui/src/i18n/tr.json";
import { setLocale, summarySentence, t } from "../../ui/src/i18n";

const ERROR_CODES = [
  "file_too_large",
  "unreadable_file",
  "cv_too_short",
  "no_requirements_found",
  "model_output_invalid",
  "sampling_unavailable",
  "upload_expired",
  "invalid_args",
  "internal_error",
  "host_unavailable",
  "url_fetch_failed",
];

describe("dictionaries", () => {
  it("carry exactly the same keys", () => {
    expect(Object.keys(tr).sort()).toEqual(Object.keys(en).sort());
  });

  it("have no empty strings except the deliberately silent ones", () => {
    const silent = new Set(["error.cancelled"]);
    for (const [key, value] of Object.entries(en)) {
      if (!silent.has(key)) expect(value, `en.${key}`).not.toBe("");
    }
    for (const [key, value] of Object.entries(tr)) {
      if (!silent.has(key)) expect(value, `tr.${key}`).not.toBe("");
    }
  });

  it("cover every error code the engine can raise", () => {
    for (const code of ERROR_CODES) {
      expect(en, `en.error.${code}`).toHaveProperty(`error.${code}`);
      expect(tr, `tr.error.${code}`).toHaveProperty(`error.${code}`);
    }
  });

  it("keep the same placeholders in both languages", () => {
    const placeholders = (value: string) => (value.match(/\{\w+\}/g) ?? []).sort();
    for (const key of Object.keys(en)) {
      expect(placeholders(tr[key as keyof typeof tr]), key).toEqual(
        placeholders(en[key as keyof typeof en]),
      );
    }
  });
});

describe("t()", () => {
  it("interpolates values", () => {
    setLocale("en");
    expect(t("tracker.coverage", { strong: 6, total: 8 })).toBe("6 of 8 evidenced");
  });

  it("returns the Turkish string when the locale is Turkish", () => {
    setLocale("tr");
    expect(t("nav.matches")).toBe("Eşleşmeler");
    setLocale("en");
  });

  it("falls back to English rather than printing the key", () => {
    setLocale("tr");
    expect(t("app.tagline")).not.toBe("app.tagline");
    setLocale("en");
  });

  it("leaves an unknown placeholder alone instead of blanking it", () => {
    setLocale("en");
    expect(t("tracker.coverage", { strong: 1 })).toContain("{total}");
  });
});

describe("summary sentence", () => {
  it("names both counts in English", () => {
    setLocale("en");
    expect(summarySentence(14, 9, 2)).toBe(
      "9 of 14 requirements have evidence in your CV. 2 must-haves don't.",
    );
  });

  it("uses the singular for one gap", () => {
    setLocale("en");
    expect(summarySentence(10, 9, 1)).toContain("1 must-have doesn't.");
  });

  it("omits the warning when nothing is missing", () => {
    setLocale("en");
    expect(summarySentence(10, 10, 0)).toBe("10 of 10 requirements have evidence in your CV.");
  });

  it("reads as Turkish under the Turkish locale", () => {
    setLocale("tr");
    expect(summarySentence(14, 9, 2)).toBe(
      "14 gereksinimden 9 tanesi CV'nizde kanıtlanıyor. 2 zorunlu madde için kanıt yok.",
    );
    setLocale("en");
  });
});
