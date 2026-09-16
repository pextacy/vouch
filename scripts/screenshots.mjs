#!/usr/bin/env node
/**
 * Screenshot the built bundle at phone and desktop width.
 *
 *     pnpm build && node scripts/screenshots.mjs
 *     node scripts/screenshots.mjs --dark
 *
 * `CLAUDE.md` asks for 360 px and 1280 px captures after every UI change, and
 * `phases.md` Phase 2 has an anti-vibe-code audit that is a looking exercise —
 * neither is satisfied by "it compiled".
 *
 * The bundle is served as static files, so `AnnaAppRuntime.connect()` finds no
 * host and the app falls back to preview mode on the recorded example. That is
 * the point: the screenshots show real components with real copy and no model
 * call. Pass `--no-banner` to hide the preview strip for store assets.
 *
 * Uses `playwright-core` against a Chromium already on the machine — it is a
 * tooling dependency, never bundled (see plan.md §6).
 */

import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

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

/** Each shot: where to go, and what to do once there. */
const SHOTS = [
  { name: "01-onboarding", hash: "#/" },
  { name: "02-add-cv", hash: "#/cv/add" },
  { name: "03-new-match", hash: "#/new" },
  { name: "04-match-map", hash: "#/match/example" },
  { name: "05-tailor", hash: "#/match/example", then: "#/tailor" },
  { name: "06-letter", hash: "#/match/example", then: "#/letter" },
  { name: "07-tracker", hash: "#/matches" },
  { name: "08-your-data", hash: "#/data" },
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

      for (const shot of SHOTS) {
        await page.goto(`${base}/index.html${shot.hash}`, { waitUntil: "networkidle" });
        await page.waitForSelector(".appbar, .screen", { timeout: 10_000 });
        if (shot.then) {
          await page.evaluate((next) => {
            window.location.hash = next;
          }, shot.then);
          await page.waitForTimeout(400);
        }
        if (hideBanner) {
          await page.addStyleTag({ content: ".preview { display: none }" });
        }
        if (viewport.name === "mobile") {
          // A full-page capture draws a sticky bar at its position in the
          // flow, which looks like a bar floating mid-list rather than one
          // pinned to the bottom of a real viewport.
          await page.addStyleTag({ content: ".map__actions { position: static }" });
        }
        await page.waitForTimeout(250);

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
