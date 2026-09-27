/**
 * Strings.
 *
 * The parity test is the important one: a key present in English and missing
 * in Turkish renders the English sentence to a Turkish user, which looks like
 * a bug and reads like carelessness.
 */

import { readFileSync, readdirSync } from "node:fs";

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
  "rate_limited",
  "internal_error",
  "host_unavailable",
  "url_fetch_failed",
  // UI-only codes: the engine succeeded, the surrounding host call did not.
  "save_failed",
  "export_failed",
  "export_empty",
  "cv_changed",
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
    expect(t("app.name")).not.toBe("app.name");
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

/**
 * Reachability.
 *
 * The other direction of the parity test, and the one the Definition of Done
 * asks for: a string nobody renders is dead weight that still has to be
 * translated, reviewed and kept in tone. Most keys are looked up as literals,
 * so a text scan finds them; the rest are built from a union type at the call
 * site (`t(`error.${code}`)`), so each of those families is declared here with
 * the values its type admits, and the family has to match the table exactly.
 * Adding `status.unknown` to en.json without teaching `Status` about it fails
 * here rather than shipping a string that never renders.
 */

const SOURCE = (() => {
  const dir = new URL("../../ui/src/", import.meta.url);
  const read = (at: URL): string =>
    readdirSync(at, { withFileTypes: true })
      .map((entry) => {
        const child = new URL(entry.name + (entry.isDirectory() ? "/" : ""), at);
        if (entry.isDirectory()) return read(child);
        return /\.tsx?$/.test(entry.name) ? readFileSync(child, "utf8") : "";
      })
      .join("\n");
  return read(dir);
})();

/** key prefix → the values the call site's union type admits. */
const DYNAMIC_FAMILIES: Record<string, string[]> = {
  "error.": [...ERROR_CODES, "cancelled"],
  "status.": ["strong", "partial", "missing"],
  "progress.stage.": ["normalize", "extract", "match", "guard", "summarize", "done"],
  "letter.tone.": ["plain", "warm", "formal"],
  "letter.length.": ["short", "standard"],
  "tracker.status.": ["drafted", "applied", "interview", "offer", "closed"],
  "settings.theme.": ["system", "light", "dark"],
  "cv.warning.": ["multi_column_suspected", "tables_flattened", "truncated"],
  // Two families over the same union: what the audit found, and what it asks
  // the user for. Both are keyed by `CvFindingKind`, so both have to stay in
  // step with the engine's `CvFindingKind` literal.
  "audit.kind.": ["skill_unevidenced", "title_unevidenced", "date_conflict"],
  "audit.ask.": ["skill_unevidenced", "title_unevidenced", "date_conflict"],
  // Keyed by `BriefRisk` and `ClaimSource`: the interview brief's verdicts
  // are phrased here, never in the engine, for the same reason as above.
  // `BriefRisk` minus `proved`: a proved requirement gets no sentence at all,
  // because the section heading and the highlighter under it already say it.
  "brief.risk.": [
    "no_evidence",
    "self_asserted",
    "listed_not_shown",
    "self_added",
    "related_only",
  ],
  "brief.source.": ["bullet", "letter"],
};

describe("every string is rendered by something", () => {
  it("builds each dynamic family from a template literal in the source", () => {
    for (const prefix of Object.keys(DYNAMIC_FAMILIES)) {
      expect(SOURCE, prefix).toContain("`" + prefix + "${");
    }
  });

  it("keeps each family and the table in step", () => {
    for (const [prefix, values] of Object.entries(DYNAMIC_FAMILIES)) {
      const inTable = Object.keys(en)
        .filter((key) => key.startsWith(prefix))
        .map((key) => key.slice(prefix.length))
        .sort();
      expect(inTable, prefix).toEqual([...values].sort());
    }
  });

  it("leaves no key that nothing looks up", () => {
    const dynamic = new Set(
      Object.entries(DYNAMIC_FAMILIES).flatMap(([prefix, values]) =>
        values.map((value) => prefix + value),
      ),
    );
    const orphans = Object.keys(en).filter(
      (key) => !dynamic.has(key) && !SOURCE.includes(`"${key}"`),
    );
    expect(orphans).toEqual([]);
  });
});

// ─── Two silent failure modes ─────────────────────────────────────────
//
// Both of these break without anything throwing: a Turkish sentence that
// dropped its `{count}` renders with a hole in it, and a `t("key")` nothing
// defines renders the key itself. Neither shows up in a type check and
// neither is visible unless someone happens to read that screen in that
// language.

describe("placeholders survive translation", () => {
  const tokens = (value: string): string[] =>
    [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1] as string).sort();

  it.each(Object.keys(en).filter((key) => /\{\w+\}/.test(en[key] as string)))(
    "%s keeps its placeholders in Turkish",
    (key) => {
      expect(tokens(tr[key] as string)).toEqual(tokens(en[key] as string));
    },
  );
});

describe("every key a screen asks for exists", () => {
  it("resolves every literal t(\"…\") in the source", () => {
    // `\bt(` rather than `t(`: `exportCvDocument("full")` ends in a `t(` too.
    const asked = [...SOURCE.matchAll(/\bt\(\s*"([a-z0-9_.]+)"/g)].map((m) => m[1] as string);
    const missing = [...new Set(asked)].filter((key) => !(key in en));
    expect(missing).toEqual([]);
  });
});
