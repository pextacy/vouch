/**
 * The receipt, as a picture.
 *
 * `plan.md §9` names anonymised match-map visuals as the growth engine and the
 * hook as "Show your receipts". Until now the only way to make one was to
 * photograph your own screen, which carries your employers, your job titles
 * and the sentences of your CV — the one image a job seeker cannot post. So
 * the mechanic the plan rests on had nothing behind it.
 *
 * What is on screen here is the file: the same SVG string is drawn into the
 * page and written to disk, so nobody has to trust that the preview matches
 * what gets saved.
 *
 * The role title is the only thing on the card that could say which job
 * somebody is applying for, and it is off until they ask for it. Everything
 * else reaching the renderer is a number or an enum (`lib/share.ts`), which is
 * why the card cannot leak a CV line rather than merely being careful not to.
 */

import { useState } from "preact/hooks";

import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { cardFor, renderCard } from "../lib/share";
import { navigate } from "../router";
import {
  currentMatch,
  dismissError,
  error,
  saveCard,
  sharePhase,
  shareWithRole,
} from "../state";
import { currentLocale } from "../state";
import "./Share.css";

export function Share() {
  const [copied, setCopied] = useState(false);
  const match = currentMatch.value;

  if (!match) {
    navigate("/matches");
    return null;
  }

  const withRole = shareWithRole.value;
  const card = cardFor(match, { withRole, locale: currentLocale() });
  const role = match.posting.title;

  const evidenced = card.evidenced + card.related;
  const headline = [
    t("share.sentence", { evidenced, total: card.total }),
    card.mustMissing === 1
      ? t("share.mustMissing.one")
      : card.mustMissing > 1
        ? t("share.mustMissing.many", { count: card.mustMissing })
        : "",
  ]
    .filter(Boolean)
    .join(" ");

  const svg = renderCard(card, {
    headline,
    must: t("map.mustHave"),
    nice: t("map.niceToHave"),
    evidenced: t("status.strong"),
    related: t("status.partial"),
    missing: t("status.missing"),
    tagline: t("share.tagline"),
  });

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(headline);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // The sentence is on the card either way.
    }
  }

  return (
    <Screen heading={t("share.heading")} lede={t("share.body")}>
      {error.value && <ErrorNotice error={error.value} onDismiss={dismissError} />}

      {/* The file, drawn in the page. One renderer, so the preview cannot
          drift from what gets saved. */}
      <div class="share__card" role="img" aria-label={headline} dangerouslySetInnerHTML={{ __html: svg }} />

      <p class="small muted share__contains">
        {t("share.contains", { count: card.marks.length })}
      </p>

      {role && (
        <div class="stack stack--tight share__role">
          <p class="share__roleState">
            {withRole ? t("share.withRole") : t("share.withoutRole")}
          </p>
          <p class="small muted">{t("share.roleNote")}</p>
          <div class="row">
            <button
              type="button"
              class="button button--quiet share__roleToggle"
              onClick={() => {
                shareWithRole.value = !withRole;
              }}
            >
              {withRole ? t("share.roleToggleOff") : t("share.roleToggleOn", { role })}
            </button>
          </div>
        </div>
      )}

      <div class="row">
        <button
          type="button"
          class="button share__save"
          disabled={sharePhase.value === "running"}
          onClick={() => void saveCard(svg)}
        >
          {sharePhase.value === "running" ? t("share.saving") : t("share.save")}
        </button>
        <button type="button" class="button button--secondary" onClick={() => void copy()}>
          {copied ? t("map.copied") : t("map.copySummary")}
        </button>
        <button
          type="button"
          class="button button--quiet"
          onClick={() => navigate(`/match/${match.id}`)}
        >
          {t("nav.back")}
        </button>
      </div>

      {sharePhase.value === "done" && (
        <p class="small muted" aria-live="polite">
          {t("share.saved")}
        </p>
      )}
    </Screen>
  );
}
