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
 * Further postings that want some of the same things.
 *
 * The recurring view refuses to say anything below three applications — a
 * pattern drawn from two would be a horoscope — so a screen shot of it needs
 * three. All three ask for Kafka and Terraform, which the example CV cannot
 * prove, and all three ask for Go and PostgreSQL, which it can: that is the
 * shape the screen exists to tell apart, a real gap from a real strength.
 */
const EXTRA_POSTINGS = [
  `Platform Engineer — Harborline (Hybrid, Amsterdam)

Requirements
- 4+ years building backend services
- Go or a similar compiled language in production
- Production experience with Kafka or a similar event bus
- Working knowledge of PostgreSQL and schema migrations

Nice to have
- Familiarity with Terraform
- Exposure to payments or settlement systems`,

  `Senior Backend Engineer — Vantage Clearing (Remote)

Requirements
- Backend engineering experience in Go
- Working knowledge of PostgreSQL and schema migrations
- Production experience with Kafka or a similar event bus
- Comfortable being on call for what you ship

Nice to have
- Familiarity with Terraform
- Settlement or reconciliation background`,
];

/**
 * Run more matches, so a cross-application screen has something to cross.
 *
 * Starts from the New match screen of an app that already has a CV, which is
 * where `runLiveMatch` leaves it. Returns the route of the last one run.
 */
export async function runExtraMatches(page, base, count) {
  let route = null;
  for (let index = 0; index < count && index < EXTRA_POSTINGS.length; index += 1) {
    await page.evaluate(() => {
      window.location.hash = "/new";
    });
    await page.waitForSelector("#posting", { timeout: 15_000 });
    await page.fill("#posting", EXTRA_POSTINGS[index]);
    await page.getByRole("button", { name: "Run match", exact: true }).click();
    await page.waitForFunction(
      () => /^#\/match\/(?!example)/.test(window.location.hash),
      null,
      { timeout: 30_000 },
    );
    await page.waitForSelector(".map", { timeout: 15_000 });
    route = await page.evaluate(() => window.location.hash.slice(1));
  }
  return route;
}

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

/**
 * Run the *same* posting a second time.
 *
 * The same text means the same posting hash, which is what pairs the two runs
 * in the tracker — so this is the only way to reach "what changed", and the
 * state the whole answer loop points at: a CV line written between two runs of
 * one job. Run it after `answerAGap` or the second run has nothing new to
 * stand on.
 */
export async function runSamePostingAgain(page, base) {
  await page.evaluate(() => {
    window.location.hash = "/new";
  });
  await page.waitForSelector("#posting", { timeout: 15_000 });
  await page.fill("#posting", POSTING);
  await page.getByRole("button", { name: "Run match", exact: true }).click();
  await page.waitForFunction(
    () => /^#\/match\/(?!example)/.test(window.location.hash),
    null,
    { timeout: 30_000 },
  );
  await page.waitForSelector(".map", { timeout: 15_000 });
  return page.evaluate(() => window.location.hash.slice(1));
}

/**
 * Answer one gap question, the way a user does a week after applying.
 *
 * It is the only way to reach the state "since you applied" exists for: a CV
 * line written *after* an application went out. Nothing else in this flow
 * produces one, so without it that screen can only ever be walked empty.
 *
 * The sentence names Kafka on purpose — the example posting asks for it and
 * the example CV cannot show it, which is exactly the shape the screen
 * reports.
 */
export async function answerAGap(page, base) {
  await goTo(page, "/gaps", ".screen");
  const box = page.locator(".gap__input").first();
  if ((await box.count()) === 0) return false;
  await box.fill("Owned the Kafka consumer rewrite at Acme Payments in 2023.");
  await page.locator(".gap__answer .button").first().click();
  await page.waitForSelector(".gap__saved", { timeout: 15_000 });
  return true;
}

/**
 * Add a second CV, so the screens that switch between them have something to
 * switch between.
 *
 * Pasted rather than uploaded: the stub hands back the example CV for any
 * file, and two CVs that are the same document tell a reviewer nothing about
 * whether the switch works. It also leaves the new CV unnamed, which is the
 * "CV 2" fallback a real user meets when they paste rather than upload.
 *
 * Note that this switches the workspace: the tracker is empty afterwards,
 * because the applications belong to the first CV. Run it after every screen
 * that needs those applications.
 */
export async function runExtraCv(page, base) {
  await goTo(page, "/cv/preview", ".screen");
  await page.getByRole("button", { name: "Add another CV", exact: true }).click();
  await page.waitForSelector("#cv-text", { timeout: 15_000 });
  await page.fill("#cv-text", SECOND_CV);
  await page.getByRole("button", { name: "Use this text", exact: true }).click();
  await page.waitForFunction(() => window.location.hash.startsWith("#/cv/preview"), null, {
    timeout: 15_000,
  });
  return "/cv/preview";
}

/** Long enough to clear the 200-character floor on "Use this text". */
const SECOND_CV = `Maya Collins — Data Engineer, Berlin

Experience
Acme Payments — Data Engineer, 2018-2024
Built the settlement reporting warehouse in Python and dbt.
Ran the nightly Airflow jobs that fed the finance team's dashboards.
Owned data quality checks across twelve upstream sources.

Education
MSc Computer Science, University of Edinburgh, 2016

Skills
Python, SQL, dbt, Airflow, PostgreSQL`;

/** Navigate within the running app, the way a tap on a link would. */
export async function goTo(page, route, selector) {
  await page.evaluate((next) => {
    window.location.hash = next;
  }, route);
  if (selector) await page.waitForSelector(selector, { timeout: 15_000 });
  await page.waitForTimeout(300);
}
