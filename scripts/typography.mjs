/**
 * The type system, measured on the built bundle rather than trusted.
 *
 * `docs.md §8.4` states the rules — two families with separate jobs, a six-step
 * scale, tracking only on the large sizes, a fixed measure — and twenty screens
 * were written against it by hand. Every one of those screens is one copied
 * declaration away from a size that is not on the scale or a serif in the app
 * chrome, and nobody notices a 17 px heading by looking at it. This is the
 * ruler, and it is the same idea as `a11y.mjs`: read the computed styles the
 * browser actually applied, not the stylesheet anyone meant to write.
 *
 * Six rules, each of them something the design system says out loud:
 *
 * =============  ==========================================================
 * scale          every rendered size is one of 13 · 16 · 19 · 23 · 28 · 33
 * weight         400 running text, 500 labels and headings, 700 the page
 *                title — a fourth weight is a fourth voice
 * family         Schibsted Grotesk, or Source Serif 4 on a document surface
 * serif-scope    the serif never appears in UI chrome (§8.4: "no serif in
 *                UI chrome") — only in a quoted document, a CV line, a
 *                letter paragraph or a posting's own wording
 * tracking       -0.01em at 23 px and up, and nowhere below it
 * leading        1.5 for the grotesque, 1.6 for the serif
 * measure        no paragraph longer than the 68ch line length
 * =============  ==========================================================
 *
 * Usage: `node scripts/typography.mjs [--only=name,name] [--verbose]`.
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

import { answerAGap, goTo, runExtraCv, runExtraMatches, runLiveMatch, runSamePostingAgain } from "./preview-flow.mjs";

const ROOT = resolve(fileURLToPath(new URL("..", import.meta.url)));
const BUNDLE = join(ROOT, "bundle");

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".json": "application/json",
  ".png": "image/png",
};

/** Both widths, because the scale is the same on a phone and the measure is not. */
const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "mobile", width: 360, height: 780 },
];

/** §8.4, base 16 px, ratio 1.2. Nothing else is a size in this app. */
const SCALE = [13, 16, 19, 23, 28, 33];

/** Where a serif is the point rather than a mistake. */
const DOCUMENT_SURFACES = [
  ".sheet",
  ".cvline",
  ".cvedit",
  ".letterpara",
  ".bullet",
  ".bullet__original",
  ".req__quote",
  ".recur__texts",
  ".brief__quote",
  ".ledgerrow__quote",
  ".since__quote",
  ".change__quote",
  ".worth__texts",
  ".check__line",
  ".check__document",
  ".answer__quote",
  ".gap__angle",
  ".audit__line",
  ".compare__texts",
];

const SCREENS = [
  { name: "onboarding", hash: "#/" },
  { name: "add-cv", hash: "#/cv/add" },
  { name: "new-match", hash: "#/new" },
  { name: "match-map", hash: "#/match/example" },
  { name: "tailor", hash: "#/match/example", then: "#/tailor" },
  { name: "letter", hash: "#/match/example", then: "#/letter" },
  { name: "gaps", hash: "#/match/example", then: "#/gaps" },
  { name: "interview", hash: "#/match/example", then: "#/brief" },
  { name: "cv-audit", hash: "#/match/example", then: "#/cv/audit" },
  { name: "tracker", hash: "#/matches" },
  { name: "your-data", hash: "#/data" },
  { name: "cv-preview", live: "/cv/preview" },
  { name: "profile", live: "/cv/profile" },
  { name: "recurring", live: "/recurring", extraMatches: 2 },
  { name: "compare", live: "/compare", extraMatches: 2 },
  { name: "ledger", live: "/cv/ledger", extraMatches: 2 },
  { name: "check", live: "/check" },
  { name: "worth", live: "/worth", answerGap: true },
  { name: "since", live: "/since", answerGap: true },
  { name: "followup", live: "/followup", answerGap: true },
  { name: "changed", live: "/changed", answerGap: true, sameAgain: true },
];

const ONLY = (process.argv.find((arg) => arg.startsWith("--only=")) ?? "")
  .slice("--only=".length)
  .split(",")
  .map((name) => name.trim())
  .filter(Boolean);
const SELECTED = ONLY.length > 0 ? SCREENS.filter((screen) => ONLY.includes(screen.name)) : SCREENS;
const verbose = process.argv.includes("--verbose");

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
 * The measurement, run inside the page.
 *
 * One pass over every element that renders its own text, so the numbers come
 * from the browser's cascade rather than from a reading of the stylesheets.
 */
function measureInPage({ scale, surfaces }) {
  const findings = [];
  const seen = new Set();

  const describe = (element) => {
    const classes =
      typeof element.className === "string" && element.className
        ? `.${element.className.trim().split(/\s+/).slice(0, 2).join(".")}`
        : "";
    const text = (element.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 32);
    return `<${element.tagName.toLowerCase()}${classes}>${text ? ` “${text}”` : ""}`;
  };

  const report = (rule, element, detail) => {
    const line = `${rule}|${describe(element)}|${detail}`;
    if (seen.has(line)) return;
    seen.add(line);
    findings.push({ rule, element: describe(element), detail });
  };

  /**
   * The real width of a `ch` for one family at one size.
   *
   * `max-width: 68ch` is resolved by the browser against the font's own zero
   * advance, so a guess like "half the font size" reports every well-set
   * paragraph as too wide. Measured once per family and size, then cached.
   */
  const chCache = new Map();
  const probe = document.createElement("span");
  probe.textContent = "0".repeat(10);
  probe.setAttribute(
    "style",
    "position:absolute;visibility:hidden;white-space:pre;left:-9999px;top:0",
  );
  document.body.appendChild(probe);
  const chWidth = (family, size) => {
    const key = `${family}|${size}`;
    if (!chCache.has(key)) {
      probe.style.fontFamily = family;
      probe.style.fontSize = `${size}px`;
      chCache.set(key, probe.getBoundingClientRect().width / 10);
    }
    return chCache.get(key);
  };

  const visible = (element) => {
    const style = getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };

  /** Elements that render text of their own, not just wrap it. */
  const ownsText = (element) =>
    [...element.childNodes].some(
      (node) => node.nodeType === 3 && (node.textContent ?? "").trim().length > 0,
    );

  for (const element of document.querySelectorAll("body *")) {
    if (!ownsText(element) || !visible(element)) continue;
    const style = getComputedStyle(element);
    const size = Math.round(parseFloat(style.fontSize));
    const family = style.fontFamily;
    const serif = family.includes("Source Serif");
    const tracking = parseFloat(style.letterSpacing);
    const leading = parseFloat(style.lineHeight) / size;

    // 400 for running text, 500 for anything that labels or heads something,
    // 700 for the page's own title. A fourth weight is a fourth voice.
    const weight = Number(style.fontWeight);
    if (![400, 500, 700].includes(weight)) {
      report("weight", element, `${weight} is not one of 400 / 500 / 700`);
    }

    if (!scale.includes(size)) {
      report("scale", element, `${size}px is not on the 13/16/19/23/28/33 scale`);
    }

    if (!serif && !family.includes("Schibsted Grotesk")) {
      report("family", element, `set in ${family.split(",")[0]}`);
    }

    if (serif && !surfaces.some((surface) => element.closest(surface))) {
      report("serif-scope", element, "serif outside a document surface");
    }

    const wantsTracking = size >= 23;
    const hasTracking = Number.isFinite(tracking) && Math.abs(tracking) > 0.01;
    if (wantsTracking && !hasTracking) {
      report("tracking", element, `${size}px carries no -0.01em`);
    }
    if (!wantsTracking && hasTracking) {
      report("tracking", element, `${size}px carries ${style.letterSpacing}, which is for 23px and up`);
    }

    // Headings set their own tighter leading, and so does anything inside
    // one — a highlighter mark wrapping a heading's words is part of the
    // heading, not a paragraph. This rule is about running text.
    const heading = element.closest("h1, h2, h3, h4, h5, h6") !== null;
    if (!heading && Number.isFinite(leading)) {
      const wanted = serif ? 1.6 : 1.5;
      if (Math.abs(leading - wanted) > 0.06) {
        report("leading", element, `line-height ${leading.toFixed(2)}, wanted ${wanted}`);
      }
    }

    if (element.tagName === "P") {
      const ch = element.getBoundingClientRect().width / chWidth(family, size);
      // One character of slack: a paragraph capped at exactly 68ch rounds to
      // 69 often enough that a stricter bound would only report rounding.
      if (ch > 69) {
        report("measure", element, `${Math.round(ch)}ch of running text, over the 68ch measure`);
      }
    }
  }

  probe.remove();
  return findings;
}

async function main() {
  const { server, base } = await serveBundle();
  const browser = await chromium.launch();
  const failures = [];
  let checks = 0;

  try {
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
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
          if (screen.extraMatches && !extraMatches) {
            extraMatches = await runExtraMatches(page, base, screen.extraMatches);
          }
          if (screen.extraCv && !extraCv) extraCv = await runExtraCv(page, base);
          if (screen.answerGap && !gapAnswered) gapAnswered = await answerAGap(page, base);
          if (screen.sameAgain && !secondRun) secondRun = await runSamePostingAgain(page, base);
          await goTo(page, screen.live, ".screen");
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

        const findings = await page.evaluate(measureInPage, {
          scale: SCALE,
          surfaces: DOCUMENT_SURFACES,
        });
        checks += 1;
        const where = `${screen.name} · ${viewport.name}`;
        if (findings.length === 0) {
          if (verbose) console.log(`  ok    ${where}`);
          continue;
        }
        for (const finding of findings) failures.push({ where, ...finding });
      }

      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  console.log(`${checks} screen/viewport combinations measured`);
  if (failures.length === 0) {
    console.log("type system clean");
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
