#!/usr/bin/env node
/**
 * Accessibility audit over the built bundle.
 *
 *     pnpm build && node scripts/a11y.mjs
 *     node scripts/a11y.mjs --verbose
 *
 * The design system asks for AA contrast, a visible focus ring, full keyboard
 * access and 44 px touch targets (`docs/docs.md §8`). Verified by hand, that is
 * a promise which decays the moment a token changes — so this runs the same
 * checks on every screen, at phone and desktop width, in light and dark, and
 * exits non-zero when one fails.
 *
 * It deliberately adds no dependency: `playwright-core` is already the
 * screenshot tool (docs/plan.md §6), and the rules below are computed from the DOM
 * and the CSSOM rather than pulled from an audit library, so the failure
 * message names the element and the number rather than a rule id.
 *
 * What it cannot see: anything that needs judgement (is this label the *right*
 * word), and anything behind a host API. Those stay a looking exercise.
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

import {
  answerAGap,
  goTo,
  runExtraCv,
  runExtraMatches,
  runLiveMatch,
  runSamePostingAgain,
} from "./preview-flow.mjs";

const ROOT = resolve(fileURLToPath(new URL("..", import.meta.url)));
const BUNDLE = join(ROOT, "bundle");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".json": "application/json",
  ".png": "image/png",
};

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "mobile", width: 360, height: 780 },
];

const THEMES = ["light", "dark"];

/**
 * Every screen a user can reach without a host.
 *
 * The `live` ones run after a real (stub-answered) match, because the example
 * is read-only: Accept, Skip, Edit, the tone and length switches, and the
 * tracker's status select and delete only exist on a match the user owns, and
 * an audit that never renders them is an audit of the half that cannot be
 * clicked. They come last on purpose — the flow saves a CV, and the screens
 * above are the ones a user sees before they have one.
 */
/**
 * A document with something in it the CV cannot back, for the check screen.
 *
 * Written against the CV `runLiveMatch` saves, so the first line passes and
 * the second does not: a result list with both shapes on it is the one worth
 * measuring contrast and tap targets on.
 */
const CHECK_DOCUMENT = [
  "Built payment reconciliation services in Go.",
  "Cut checkout latency by 40% and led a team of 12 at Globex.",
].join("\n");

const FORM_QUESTIONS = [
  "Describe your experience with payment reconciliation.",
  "Why do you want to work here?",
  "Describe your Kubernetes work.",
].join("\n");

const SCREENS = [
  { name: "onboarding", hash: "#/" },
  { name: "add-cv", hash: "#/cv/add" },
  { name: "cv-audit", hash: "#/match/example", then: "#/cv/audit" },
  { name: "new-match", hash: "#/new" },
  { name: "match-map", hash: "#/match/example" },
  { name: "tailor", hash: "#/match/example", then: "#/tailor" },
  { name: "letter", hash: "#/match/example", then: "#/letter" },
  { name: "gaps", hash: "#/match/example", then: "#/gaps" },
  { name: "interview", hash: "#/match/example", then: "#/brief" },
  { name: "tracker", hash: "#/matches" },
  { name: "your-data", hash: "#/data" },
  // The correction, and then the picker it opens. The picker turns the whole
  // CV sheet into buttons — the one place in the app where a reading surface
  // becomes a control — so it is audited for focus, contrast and tap target
  // like every other control.
  { name: "match-live", live: "@match" },
  { name: "match-picking", live: "@match", open: ".req__dispute" },
  // The one artefact built to leave the account. Audited with the role title
  // both off and on, because the toggle is the consent model.
  { name: "share", live: "/share" },
  { name: "share-with-role", live: "/share", open: ".share__roleToggle" },
  { name: "tailor-live", live: "/tailor" },
  { name: "tailor-editing", live: "/tailor", open: ".bullet .button--quiet" },
  { name: "letter-live", live: "/letter" },
  // After the letter, so the brief has claims to quote as well as receipts.
  { name: "interview-live", live: "/brief" },
  { name: "tracker-live", live: "/matches" },
  { name: "tracker-confirming", live: "/matches", open: ".trackrow__delete" },
  { name: "recurring", live: "/recurring", extraMatches: 2 },
  // The wordings list only exists once it is expanded, and it is the part of
  // the screen a user leans on to disagree with the grouping.
  { name: "recurring-wordings", live: "/recurring", open: ".recur__toggle", extraMatches: 2 },
  // The comparison picks the two most recent by default, so it has an answer
  // on screen without a click — which is also how a user first meets it.
  { name: "compare", live: "/compare", extraMatches: 2 },
  // The ledger quotes CV lines in the document face and marks the ones that
  // carried an application, so it is the screen where the highlighter has to
  // clear contrast against a serif at body size.
  { name: "ledger", live: "/cv/ledger", extraMatches: 2 },
  // Walked after a gap has been answered, because the empty version of this
  // screen is the half nobody reads: what needs auditing is the list of
  // requirements with the user's own new sentence quoted under each one.
  { name: "since", live: "/since", answerGap: true },
  // The note itself, which only exists once the CV has gained a line since
  // the application went out — the refusal is the other half and is reached
  // by the same screen with nothing answered.
  { name: "followup", live: "/followup", answerGap: true },
  // The shelf-wide version of the same question, audited after a gap has been
  // answered — before that it is an empty state, which is the half of the
  // screen nobody has to read carefully.
  { name: "worth", live: "/worth", answerGap: true },
  // The payoff screen, and the only one that needs two runs of one posting:
  // audited after a gap has been answered *and* the posting re-run, because
  // the credited row — the app's one claim about the user's own writing — is
  // the part that has to read clearly.
  { name: "changed", live: "/changed", answerGap: true, sameAgain: true },
  // Three questions on purpose: one the CV answers, one it declines to answer
  // because the question is about what the candidate wants, and one it hands
  // back. All three render differently and all three ship in one payload.
  { name: "answers", live: "/answers", fill: { selector: "#answers-input", text: FORM_QUESTIONS } },
  {
    name: "answers-result",
    live: "/answers",
    fill: { selector: "#answers-input", text: FORM_QUESTIONS },
    open: ".answers__run",
  },
  // The document check has two screens in one: the paste form, and the list
  // of flagged sentences that only exists after a document has been read.
  // Auditing the form alone would audit the half nobody reads.
  { name: "check", live: "/check" },
  {
    name: "check-result",
    live: "/check",
    fill: { selector: "#check-document", text: CHECK_DOCUMENT },
    open: ".check__run",
  },
  // Last, and in this order: adding a second CV switches the workspace, so
  // every screen that needs the first CV's applications has already run.
  { name: "cv-preview", live: "/cv/preview" },
  { name: "profile", live: "/cv/profile" },
  { name: "cv-profiles", live: "/data", extraCv: true },
  { name: "cv-switch", live: "/cv/preview" },
];

/**
 * `--only=name,name` audits a subset.
 *
 * The flow is the slow part — every `live` screen replays a real run — and
 * fixing one finding should not cost a full walk of twenty screens. The
 * default is still everything, which is what CI and the Definition of Done
 * mean by "clean".
 */
const ONLY = (process.argv.find((arg) => arg.startsWith("--only=")) ?? "")
  .slice("--only=".length)
  .split(",")
  .map((name) => name.trim())
  .filter(Boolean);
const SELECTED = ONLY.length > 0 ? SCREENS.filter((screen) => ONLY.includes(screen.name)) : SCREENS;

/** WCAG AA. Large text is ≥ 24px, or ≥ 18.66px when bold. */
const CONTRAST_NORMAL = 4.5;
const CONTRAST_LARGE = 3.0;

/** The mobile review checklist's floor for anything you tap. */
const TOUCH_TARGET_PX = 44;

async function serveBundle() {
  if (!existsSync(join(BUNDLE, "index.html"))) {
    throw new Error("bundle/index.html is missing — run `pnpm build` first");
  }
  const server = createServer(async (request, response) => {
    const path = (request.url ?? "/").split("?")[0];
    const file = join(BUNDLE, path === "/" ? "index.html" : decodeURIComponent(path));
    if (!file.startsWith(BUNDLE)) {
      response.writeHead(403).end();
      return;
    }
    try {
      const body = await readFile(file);
      response.writeHead(200, { "Content-Type": MIME[extname(file)] ?? "application/octet-stream" });
      response.end(body);
    } catch {
      response.writeHead(404).end("not found");
    }
  });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  return { server, base: `http://127.0.0.1:${server.address().port}` };
}

/**
 * The audit, as it runs inside the page.
 *
 * One function so the whole DOM walk happens in one round trip, and so the
 * numbers come from the browser's own computed styles rather than from a
 * re-implementation of the cascade.
 */
function auditInPage({ contrastNormal, contrastLarge, touchTarget, isMobile }) {
  const findings = [];
  const report = (rule, element, detail) => {
    findings.push({ rule, detail, element: describe(element) });
  };

  function describe(element) {
    if (!element) return "(detached)";
    const classes = typeof element.className === "string" && element.className
      ? `.${element.className.trim().split(/\s+/).slice(0, 2).join(".")}`
      : "";
    const text = (element.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
    return `<${element.tagName.toLowerCase()}${classes}>${text ? ` “${text}”` : ""}`;
  }

  function visible(element) {
    const style = getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
      return false;
    }
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  }

  function parseColor(value) {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const parts = match[1].split(/[,/]/).map((piece) => parseFloat(piece.trim()));
    const [red, green, blue] = parts;
    const alpha = parts.length > 3 ? parts[3] : 1;
    return { red, green, blue, alpha };
  }

  function over(front, back) {
    const alpha = front.alpha;
    return {
      red: front.red * alpha + back.red * (1 - alpha),
      green: front.green * alpha + back.green * (1 - alpha),
      blue: front.blue * alpha + back.blue * (1 - alpha),
      alpha: 1,
    };
  }

  function effectiveBackground(element) {
    let current = element;
    let result = { red: 255, green: 255, blue: 255, alpha: 1 };
    const stack = [];
    while (current && current !== document.documentElement.parentElement) {
      const colour = parseColor(getComputedStyle(current).backgroundColor);
      if (colour && colour.alpha > 0) {
        stack.push(colour);
        if (colour.alpha === 1) break;
      }
      current = current.parentElement;
    }
    for (const colour of stack.reverse()) result = over(colour, result);
    return result;
  }

  function luminance({ red, green, blue }) {
    const channel = (value) => {
      const ratio = value / 255;
      return ratio <= 0.03928 ? ratio / 12.92 : ((ratio + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue);
  }

  function contrast(front, back) {
    const first = luminance(front) + 0.05;
    const second = luminance(back) + 0.05;
    return first > second ? first / second : second / first;
  }

  function ownText(element) {
    return [...element.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent.trim())
      .join(" ")
      .trim();
  }

  function accessibleName(element) {
    const label = element.getAttribute("aria-label");
    if (label && label.trim()) return label.trim();
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      const named = labelledBy
        .split(/\s+/)
        .map((id) => document.getElementById(id)?.textContent?.trim() ?? "")
        .join(" ")
        .trim();
      if (named) return named;
    }
    if (element.labels && element.labels.length > 0) {
      const fromLabel = [...element.labels].map((node) => node.textContent.trim()).join(" ").trim();
      if (fromLabel) return fromLabel;
    }
    const closestLabel = element.closest("label");
    if (closestLabel) {
      const text = closestLabel.textContent.trim();
      if (text) return text;
    }
    const title = element.getAttribute("title");
    if (title && title.trim()) return title.trim();
    return (element.textContent ?? "").trim();
  }

  // ── 1. the document says what language it is in ──────────────────────────
  if (!document.documentElement.lang) {
    report("lang", document.documentElement, "the root element has no lang attribute");
  }

  // ── 2. every control can be named out loud ───────────────────────────────
  const CONTROLS = "a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])";
  const controls = [...document.querySelectorAll(CONTROLS)].filter(
    (element) => visible(element) || element.matches("input.visually-hidden, .visually-hidden input"),
  );
  for (const control of controls) {
    if (control.disabled) continue;
    if (!accessibleName(control)) {
      report("name", control, "an interactive element with no accessible name");
    }
  }

  // ── 3. decoration is hidden, meaning is labelled ─────────────────────────
  for (const image of document.querySelectorAll("img")) {
    if (!image.hasAttribute("alt")) report("alt", image, "an image with no alt attribute");
  }
  for (const svg of document.querySelectorAll("svg")) {
    const labelled =
      svg.getAttribute("aria-hidden") === "true" ||
      svg.getAttribute("role") === "img" ||
      svg.getAttribute("aria-label") ||
      svg.closest("[aria-label], button, a");
    if (!labelled) report("svg", svg, "an svg that is neither hidden nor labelled");
  }

  // ── 4. text meets AA against what is actually behind it ──────────────────
  const texts = [...document.querySelectorAll("body *")].filter(
    (element) => visible(element) && ownText(element).length > 1,
  );
  for (const element of texts) {
    const style = getComputedStyle(element);
    const colour = parseColor(style.color);
    if (!colour || colour.alpha === 0) continue;
    const background = effectiveBackground(element);
    const ratio = contrast(over(colour, background), background);
    const size = parseFloat(style.fontSize);
    const bold = parseInt(style.fontWeight, 10) >= 700;
    const floor = size >= 24 || (bold && size >= 18.66) ? contrastLarge : contrastNormal;
    if (ratio + 0.01 < floor) {
      report(
        "contrast",
        element,
        `${ratio.toFixed(2)}:1 against its background, needs ${floor}:1 at ${size}px`,
      );
    }
  }

  // ── 5. focus is visible, and it is the pencil ring the design asks for ───
  for (const control of controls) {
    if (control.disabled) continue;
    control.focus();
    const target = control.matches(".visually-hidden") ? control.closest("label") ?? control : control;
    const style = getComputedStyle(target);
    const outline =
      style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0;
    const ring = style.boxShadow !== "none";
    const border = style.borderColor;
    if (!outline && !ring && !border) {
      report("focus", control, "focusing it changes nothing visible");
    }
    control.blur();
  }

  // ── 6. a tap target is big enough to tap ─────────────────────────────────
  if (isMobile) {
    for (const control of controls) {
      if (control.disabled || control.matches(".visually-hidden")) continue;
      const box = control.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      // A link inside a paragraph is read, not tapped as a button.
      if (control.matches("a") && control.closest("p")) continue;
      const height = Math.max(box.height, parseFloat(getComputedStyle(control).minHeight) || 0);
      if (height + 0.5 < touchTarget || box.width + 0.5 < 24) {
        report(
          "target",
          control,
          `${Math.round(box.width)}×${Math.round(height)} px, needs ${touchTarget} px of height`,
        );
      }
    }
  }

  // ── 7. headings step down one level at a time ────────────────────────────
  const headings = [...document.querySelectorAll("h1, h2, h3, h4, h5, h6")].filter(visible);
  let previous = 0;
  for (const heading of headings) {
    const level = Number(heading.tagName[1]);
    if (previous && level > previous + 1) {
      report("heading", heading, `h${previous} is followed by h${level}`);
    }
    previous = level;
  }
  if (headings.length > 0 && Number(headings[0].tagName[1]) !== 1) {
    report("heading", headings[0], "the first heading on the screen is not an h1");
  }

  // ── 8. nothing is reachable only by pointer ──────────────────────────────
  for (const element of document.querySelectorAll("[onclick], [role='button']")) {
    if (!element.matches(CONTROLS) && element.tabIndex < 0) {
      report("keyboard", element, "a clickable element the keyboard cannot reach");
    }
  }

  return findings;
}

async function main() {
  const verbose = process.argv.includes("--verbose");
  const { server, base } = await serveBundle();
  const browser = await chromium.launch();
  const failures = [];
  let checks = 0;

  try {
    for (const viewport of VIEWPORTS) {
      for (const theme of THEMES) {
        const context = await browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        const page = await context.newPage();

        let liveMatch = null;
        let extraMatches = null;
        let extraCv = null;
        let gapAnswered = false;
        let secondRun = null;
        for (const screen of SELECTED) {
          if (screen.live) {
            liveMatch ??= await runLiveMatch(page, base);
            // A screen that compares applications needs several of them. The
            // recurring report says nothing below three, on purpose.
            if (screen.extraMatches && !extraMatches) {
              extraMatches = await runExtraMatches(page, base, screen.extraMatches);
            }
            // A second CV, for the switch and the list that names them.
            if (screen.extraCv && !extraCv) {
              extraCv = await runExtraCv(page, base);
            }
            // A CV line written after an application went out — the state
            // "since you applied" exists for, and the only one nothing else
            // in this flow produces.
            if (screen.answerGap && !gapAnswered) {
              gapAnswered = await answerAGap(page, base);
            }
            // And the same posting run again, which is what pairs two runs
            // and gives "what changed" anything to compare.
            if (screen.sameAgain && !secondRun) {
              secondRun = await runSamePostingAgain(page, base);
            }
            // "@match" is the live match's own map — the one screen that
            // needs a real, writable application under it, because the
            // read-only example never offers a correction.
            await goTo(page, screen.live === "@match" ? liveMatch : screen.live, ".screen");
            // Some screens only have a result to audit once they have been
            // given something to work on.
            if (screen.fill) {
              await page.fill(screen.fill.selector, screen.fill.text);
            }
            // A control that only exists once something is open — the edit
            // textarea, the delete confirmation — is still a control. A miss
            // here means the flow stopped short, not that the rule passed.
            if (screen.open) {
              await page
                .locator(screen.open)
                .first()
                .click({ timeout: 15_000 })
                .catch(() => {
                  throw new Error(`${screen.name}: nothing matched ${screen.open}`);
                });
              await page.waitForTimeout(250);
            }
          } else {
            await page.goto(`${base}/index.html${screen.hash}`, { waitUntil: "networkidle" });
            await page.waitForSelector(".appbar, .screen", { timeout: 10_000 });
            if (screen.then) {
              await page.evaluate((next) => {
                window.location.hash = next;
              }, screen.then);
              await page.waitForTimeout(400);
            }
          }
          await page.waitForTimeout(150);

          const findings = await page.evaluate(auditInPage, {
            contrastNormal: CONTRAST_NORMAL,
            contrastLarge: CONTRAST_LARGE,
            touchTarget: TOUCH_TARGET_PX,
            isMobile: viewport.name === "mobile",
          });
          checks += 1;

          const where = `${screen.name} · ${viewport.name} · ${theme}`;
          if (findings.length === 0) {
            if (verbose) console.log(`  ok    ${where}`);
            continue;
          }
          for (const finding of findings) {
            failures.push({ where, ...finding });
          }
          console.log(`  FAIL  ${where} — ${findings.length} finding(s)`);
        }

        await context.close();
      }
    }
  } finally {
    await browser.close();
    server.close();
  }

  console.log(`\n${checks} screen/viewport/theme combinations audited`);
  if (failures.length === 0) {
    console.log("no accessibility findings");
    return 0;
  }

  const byRule = new Map();
  for (const failure of failures) {
    byRule.set(failure.rule, [...(byRule.get(failure.rule) ?? []), failure]);
  }
  console.log(`${failures.length} finding(s):\n`);
  for (const [rule, entries] of byRule) {
    console.log(`${rule} (${entries.length})`);
    const seen = new Set();
    for (const entry of entries) {
      const line = `  ${entry.element} — ${entry.detail}`;
      if (seen.has(line)) continue;
      seen.add(line);
      console.log(`${line}\n    first seen on ${entry.where}`);
    }
    console.log("");
  }
  return 1;
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
