/**
 * Every screen that can fail says why.
 *
 * `docs/CLAUDE.md`'s Definition of Done asks for empty, loading and error
 * states, and that is exactly the kind of promise a screen quietly stops
 * keeping. Two of them already had: `save_failed` is set the moment a
 * finished match cannot be stored and lands the user on the match map, which
 * rendered nothing about it; a failed "Delete all my data" left "Your data"
 * looking exactly like a successful one. Both messages existed, were
 * translated, and could not reach a screen.
 *
 * So the rule is a test rather than a habit: a screen that runs something
 * which can fail renders the error signal. Source-level, like the i18n
 * orphan check — the alternative is a rendering harness this repository does
 * not have and does not need for one assertion.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SCREENS = join(process.cwd(), "ui/src/screens");

/** A screen does async work if it drives a phase or calls a state action. */
function canFail(source: string): boolean {
  return /Phase\.value|void run[A-Z]|await run[A-Z]|export[A-Z]\w*Document|deleteEverything/.test(
    source,
  );
}

const screens = readdirSync(SCREENS)
  .filter((name) => name.endsWith(".tsx"))
  .map((name) => ({ name, source: readFileSync(join(SCREENS, name), "utf8") }));

describe("error states", () => {
  it("has screens to check", () => {
    expect(screens.length).toBeGreaterThan(20);
  });

  it.each(screens.filter((screen) => canFail(screen.source)).map((s) => [s.name, s.source]))(
    "%s renders the error signal",
    (_name, source) => {
      expect(source).toContain("ErrorNotice");
      expect(source).toContain("error.value");
    },
  );
});

describe("loading states", () => {
  it.each(screens.filter((screen) => /Phase\.value/.test(screen.source)).map((s) => [s.name, s.source]))(
    "%s says something while it waits",
    (_name, source) => {
      // Either a running line of its own or a disabled control that names the
      // wait ("Preparing…"): both tell the user the app is not stuck.
      expect(/running|preparing|aria-live/i.test(source)).toBe(true);
    },
  );
});
