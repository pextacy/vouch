/**
 * Drive the built bundle through one real match, in preview mode.
 *
 * `#/match/example` is the recorded example, and the example is deliberately
 * read-only: it never calls a model and it never pretends the user can accept
 * a bullet it did not generate. That makes it the wrong surface to audit or to
 * photograph, because the controls the product is *about* — Accept, Skip,
 * Edit, the tone switch, the tracker's status select — only exist on a match
 * the user owns. A screen shot of the example shows the output and none of the
 * verbs.
 *
 * So both `a11y.mjs` and `screenshots.mjs` walk the actual flow first: add a
 * CV, paste a posting, run the match. There is no host, so the stub answers
 * (`ui/src/lib/stub.ts`) — no model call, no network, same components, and the
 * resulting match is the user's, with every control rendered.
 *
 * The CV arrives as a file rather than pasted text on purpose: the stub's file
 * path hands back the example CV, so the line ids the match cites are the line
 * ids the CV actually has.
 */

/** Long enough to clear the 120-character floor on "Run match". */
const POSTING = `Senior Backend Engineer — Northwind Ledger (Remote, EU)

Requirements
- 5+ years of backend engineering experience
- Strong production experience with Go
- Experience running services on Kubernetes
- Working knowledge of PostgreSQL and schema migrations
- Experience leading a small team

Nice to have
- Payments or fintech domain experience
- Familiarity with Kafka`;

/**
 * Leaves the page on the match map of a freshly run match.
 *
 * Returns its route (`/match/<id>`) so a caller can come back to it after
 * visiting another screen.
 */
export async function runLiveMatch(page, base) {
  // A `goto` that only changes the fragment is a same-document navigation, so
  // the app keeps whatever state the previous screen left behind — including
  // `showingExample`, which makes every later screen read-only and silently
  // empty. Reload, and the flow starts from `boot()` like a real open does.
  await page.goto(`${base}/index.html#/cv/add`, { waitUntil: "networkidle" });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(".screen");

  await page.setInputFiles('input[type="file"]', {
    name: "cv.pdf",
    mimeType: "application/pdf",
    // The stub does not read the bytes; it returns the example CV. A real
    // parse of a real PDF is what `tests/parse/` is for.
    buffer: Buffer.from("%PDF-1.4 receipts preview fixture"),
  });

  await page.waitForFunction(() => window.location.hash.startsWith("#/cv/preview"), null, {
    timeout: 15_000,
  });
  await page.getByRole("button", { name: "Looks right", exact: true }).click();

  await page.waitForFunction(() => window.location.hash.startsWith("#/new"), null, {
    timeout: 15_000,
  });
  await page.fill("#posting", POSTING);
  await page.getByRole("button", { name: "Run match", exact: true }).click();

  // The stub replays the progress ledger stage by stage before it answers, so
  // this waits out a real run rather than a fixed guess at one.
  await page.waitForFunction(
    () => /^#\/match\/(?!example)/.test(window.location.hash),
    null,
    { timeout: 30_000 },
  );
  await page.waitForSelector(".map", { timeout: 15_000 });

  return page.evaluate(() => window.location.hash.slice(1));
}

/** Navigate within the running app, the way a tap on a link would. */
export async function goTo(page, route, selector) {
  await page.evaluate((next) => {
    window.location.hash = next;
  }, route);
  if (selector) await page.waitForSelector(selector, { timeout: 15_000 });
  await page.waitForTimeout(300);
}
