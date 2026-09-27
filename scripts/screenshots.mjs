#!/usr/bin/env node
/**
 * Screenshot the built bundle at phone and desktop width.
 *
 *     pnpm build && node scripts/screenshots.mjs
 *     node scripts/screenshots.mjs --dark
 *
 * `docs/CLAUDE.md` asks for 360 px and 1280 px captures after every UI change,
 * and the anti-vibe-code audit is a looking exercise — neither is satisfied by
 * "it compiled".
 *
 * The bundle is served as static files, so `AnnaAppRuntime.connect()` finds no
 * host and the app falls back to preview mode. That is the point: the shots
 * show real components with real copy and no model call. Pass `--no-banner` to
 * hide the preview strip for store assets.
 *
 * Tailor, the cover letter and the tracker are shot on a match run through the
 * flow (`preview-flow.mjs`) rather than on `#/match/example`, because the
 * example is read-only: shooting it gives a store listing that shows the
 * output and none of the verbs — no Accept, no Skip, no Edit, no tone switch,
 * no tracker row.
 *
 * Uses `playwright-core` against a Chromium already on the machine — it is a
 * tooling dependency, never bundled (see docs/plan.md §6).
 */

import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
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
const OUT = join(ROOT, "listing", "screenshots");

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

/** A document with a sentence the saved CV can back and one it cannot. */
const CHECK_DOCUMENT = [
  "Built payment reconciliation services in Go.",
  "Cut checkout latency by 40% and led a team of 12 at Globex.",
].join("\n");

const FORM_QUESTIONS = [
  "Describe your experience with payment reconciliation.",
  "Why do you want to work here?",
  "Describe your Kubernetes work.",
].join("\n");

/**
 * `--only=name,name` re-takes a subset.
 *
 * The walk is the slow part — every `live` shot replays a real run — and
 * fixing one frame should not cost a re-shoot of the whole listing, which
 * also rewrites twenty files a reviewer may already have looked at. Mirrors
 * the same flag on `a11y.mjs`.
 */
const ONLY = (process.argv.find((arg) => arg.startsWith("--only=")) ?? "")
  .slice("--only=".length)
  .split(",")
  .map((name) => name.trim())
  .filter(Boolean);

/**
 * Each shot: where to go, and what to do once there.
 *
 * **The number is the listing's reading order; the array is the walk order.**
 * They are not the same thing and cannot be: a `live` shot stands on the
 * state the shots before it left behind — a real CV, three applications, an
 * answered gap — while the listing wants the product's story, from an empty
 * app to a set of applications being read across. So the numbers run
 * CV → posting → tailoring → interview → tracking → the cross-application
 * screens → data, and the array runs in whatever order the flow allows.
 */
const SHOTS = [
  { name: "01-onboarding", hash: "#/" },
  { name: "02-add-cv", hash: "#/cv/add" },
  { name: "04-cv-audit", live: "/cv/audit" },
  { name: "07-new-match", hash: "#/new" },
  { name: "08-match-map", hash: "#/match/example" },
  { name: "10-tailor", live: "/tailor" },
  { name: "11-letter", live: "/letter" },
  { name: "12-gaps", live: "/gaps" },
  // Shot after the letter on purpose: the brief quotes what was sent, and
  // the letter is what has been sent by this point in the walk.
  { name: "14-interview", live: "/brief" },
  // Three rows rather than one: the tracker only shows what it is for —
  // the readings grouped under the list — once there is a shelf to read.
  { name: "16-tracker", live: "/matches", extraMatches: 2 },
  { name: "21-recurring", live: "/recurring", extraMatches: 2 },
  { name: "22-compare", live: "/compare", extraMatches: 2 },
  { name: "23-ledger", live: "/cv/ledger", extraMatches: 2 },
  { name: "18-since", live: "/since", answerGap: true },
  { name: "19-followup", live: "/followup", answerGap: true },
  { name: "17-worth", live: "/worth", answerGap: true },
  // Two runs of one posting with an answered gap between them: the only
  // state where this screen shows what it is for, and the frame worth
  // putting in the listing — a gap closed by the user's own sentence.
  { name: "20-changed", live: "/changed", answerGap: true, sameAgain: true },
  { name: "09-match-picking", live: "@match", open: ".req__dispute" },
  // The only artefact built to leave the account. Numbered last because the
  // listing order above is already set; move it beside the match map when
  // that order is next revised — it is the picture the growth plan asks for.
  { name: "15-share", live: "/share" },
  {
    name: "13-answers",
    live: "/answers",
    fill: { selector: "#answers-input", text: FORM_QUESTIONS },
    open: ".answers__run",
  },
  // The check has to be photographed with something on it: the paste form is
  // an empty textarea, and the screen only says what it is once it has read a
  // document and has sentences to quote back.
  {
    name: "06-check",
    live: "/check",
    fill: { selector: "#check-document", text: CHECK_DOCUMENT },
    open: ".check__run",
  },
  { name: "24-your-data", hash: "#/data" },
  // Third in the listing, walked near the end: it needs a real CV, and a
  // `live` shot before the example-hash shots above would leave every later
  // screen showing the read-only example.
  { name: "03-cv-preview", live: "/cv/preview" },
  { name: "05-profile", live: "/cv/profile" },
  // Last of all: adding a second CV switches the workspace, so every shot
  // that needs the first CV's applications has already been taken.
  { name: "25-cv-profiles", live: "/data", extraCv: true },
  { name: "26-cv-switch", live: "/cv/preview" },
];

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
  const { port } = server.address();
  return { server, base: `http://127.0.0.1:${port}` };
}

async function main() {
  const dark = process.argv.includes("--dark");
  const hideBanner = process.argv.includes("--no-banner");
  const { server, base } = await serveBundle();
  await mkdir(OUT, { recursive: true });

  const browser = await chromium.launch();
  try {
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: 2,
        colorScheme: dark ? "dark" : "light",
        // The sweep is a one-shot entrance; freezing it mid-flight would
        // photograph a half-drawn highlighter.
        reducedMotion: "reduce",
      });
      const page = await context.newPage();

      let liveMatch = null;
      let extraMatches = null;
      let extraCv = null;
      let gapAnswered = false;
      let secondRun = null;
      for (const shot of SHOTS) {
        // Skipped rather than filtered out of `SHOTS`: the walk is
        // sequential and a later shot depends on the state the earlier
        // ones left behind, so the steps still run, only the capture is
        // skipped.
        const wanted = ONLY.length === 0 || ONLY.includes(shot.name);
        if (shot.live) {
          liveMatch ??= await runLiveMatch(page, base);
            // A screen that compares applications needs several of them. The
            // recurring report says nothing below three, on purpose.
            if (shot.extraMatches && !extraMatches) {
              extraMatches = await runExtraMatches(page, base, shot.extraMatches);
            }
            if (shot.extraCv && !extraCv) {
              extraCv = await runExtraCv(page, base);
            }
            // A sentence the user wrote after applying, and the same posting
            // run again — the pair of steps "what changed" is about.
            if (shot.answerGap && !gapAnswered) {
              gapAnswered = await answerAGap(page, base);
            }
            if (shot.sameAgain && !secondRun) {
              secondRun = await runSamePostingAgain(page, base);
            }
          // "@match" is the live match's own map — the one screen that needs
          // a real, writable application under it, because the read-only
          // example never offers a correction.
          await goTo(page, shot.live === "@match" ? liveMatch : shot.live, ".screen");
          // Some screens have nothing to photograph until they are given
          // something to work on.
          if (shot.fill) {
            await page.fill(shot.fill.selector, shot.fill.text);
          }
          if (shot.open) {
            await page.locator(shot.open).first().click({ timeout: 15_000 });
            await page.waitForTimeout(300);
          }
        } else {
          await page.goto(`${base}/index.html${shot.hash}`, { waitUntil: "networkidle" });
          await page.waitForSelector(".appbar, .screen", { timeout: 10_000 });
          if (shot.then) {
            await page.evaluate((next) => {
              window.location.hash = next;
            }, shot.then);
            await page.waitForTimeout(400);
          }
        }
        if (hideBanner) {
          await page.addStyleTag({ content: ".preview { display: none }" });
        }
        if (viewport.name === "mobile") {
          // A sticky bar in a full-page capture paints where the viewport was,
          // which lands it on top of the list. Relative puts it back in the
          // flow, at the end of the page, which is where it sits when you
          // actually scroll there.
          await page.addStyleTag({
            content: ".map__actions { position: relative; border-top: 0 }",
          });
        }
        await page.waitForTimeout(250);

        if (!wanted) continue;
        const suffix = dark ? "-dark" : "";
        const file = join(OUT, `${shot.name}-${viewport.name}${suffix}.png`);
        await page.screenshot({ path: file, fullPage: viewport.name === "mobile" });
        console.log(`  ${file.replace(ROOT + "/", "")}`);
      }

      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
