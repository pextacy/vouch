/**
 * Before the interview.
 *
 * The app was honest right up to the moment the application was sent, and
 * then it went quiet. Someone could mark a tracker row *Interview* and
 * nothing followed — yet that room is where this product's promise is
 * actually tested, out loud, by a person whose job is to find the seam
 * between what a CV says and what happened.
 *
 * So this screen is the receipts, in the order they will be asked for. It is
 * the one thing only this app can build: it already knows which CV line was
 * accepted as evidence for which requirement, and which of its own sentences
 * the user accepted and sent. Both halves, one document.
 *
 * **Nothing here is written.** Every sentence is either a line from the CV or
 * a sentence the verifier already passed and the user already chose to send.
 * Generating an answer would invent the one thing that has to be the person's
 * own — and at the moment it costs the most.
 *
 * No model, no tokens: rebuilt on open rather than stored, so it cannot go
 * quietly out of date when the CV moves underneath it.
 */

import { useEffect } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { MarkerHighlight } from "../components/MarkerHighlight";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  activeCv,
  briefPhase,
  briefResult,
  currentMatch,
  dismissError,
  error,
  runBrief,
} from "../state";
import type { BriefClaim, BriefItem, CvLine, LineId, Requirement } from "../lib/types";
import "./Interview.css";

export function Interview() {
  const brief = briefResult.value;
  const phase = briefPhase.value;
  const match = currentMatch.value;
  const doc = activeCv();

  useEffect(() => {
    if (match && doc && phase === "idle") void runBrief();
  }, [match?.id, doc?.hash, phase]);

  if (!match || !doc) {
    return (
      <Screen heading={t("brief.heading")}>
        <EmptyState
          text={t("brief.noMatch")}
          action={
            <button type="button" class="button" onClick={() => navigate("/matches")}>
              {t("nav.matches")}
            </button>
          }
        />
      </Screen>
    );
  }

  const requirements = new Map(match.requirements.map((item) => [item.id, item]));
  const lines = new Map(doc.lines.map((line) => [line.id, line]));
  const role = match.posting.title ?? t("tracker.untitledRole");

  return (
    <Screen heading={t("brief.heading")} lede={t("brief.body", { role })}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runBrief()} onDismiss={dismissError} />
      )}

      {phase === "running" && !brief && (
        <p class="muted" aria-live="polite">
          {t("brief.running")}
        </p>
      )}

      {/* The interviewer is holding the CV as it was when it was sent. A line
          added since then is worth walking in knowing about, not a detail. */}
      {brief?.cv_changed && <p class="brief__notice">{t("brief.cvChanged")}</p>}

      {brief && brief.risks.length === 0 && brief.proved.length === 0 && (
        <EmptyState
          text={t("brief.empty")}
          action={
            <button type="button" class="button" onClick={() => navigate(`/match/${match.id}`)}>
              {t("brief.backToMatch")}
            </button>
          }
        />
      )}

      {brief && brief.risks.length > 0 && (
        <section class="stack stack--tight brief__section">
          <h2>{t("brief.risksHeading")}</h2>
          <p class="muted brief__count" aria-live="polite">
            {brief.risks.length === 1
              ? t("brief.riskCountOne")
              : t("brief.riskCountMany", { count: brief.risks.length })}
          </p>
          <ul class="list">
            {brief.risks.map((item) => (
              <BriefEntry
                key={item.requirement_id}
                item={item}
                requirement={requirements.get(item.requirement_id)}
                lines={lines}
              />
            ))}
          </ul>
          {/* "They have not read it" is only half an answer. The other half
              is the CV screen, where the document with that line in it can
              be downloaded and sent. */}
          {brief.risks.some((item) => item.risk === "self_added") && (
            <div class="row">
              <button
                type="button"
                class="button button--quiet"
                onClick={() => navigate("/cv/preview")}
              >
                {t("brief.takeCv")}
              </button>
            </div>
          )}
        </section>
      )}

      {/* A brief that is only a list of weaknesses is not preparation, and it
          stops being opened — the same reason the recurring report closes on
          what the user keeps proving. */}
      {brief && brief.proved.length > 0 && (
        <section class="stack stack--tight brief__section">
          <h2>{t("brief.provedHeading")}</h2>
          <p class="muted brief__count">{t("brief.provedBody")}</p>
          <ul class="list">
            {brief.proved.map((item) => (
              <BriefEntry
                key={item.requirement_id}
                item={item}
                requirement={requirements.get(item.requirement_id)}
                lines={lines}
              />
            ))}
          </ul>
        </section>
      )}

      {brief && brief.loose_claims.length > 0 && (
        <section class="stack stack--tight brief__section">
          <h2>{t("brief.looseHeading")}</h2>
          <p class="muted brief__count">{t("brief.looseBody")}</p>
          <ul class="list">
            {brief.loose_claims.map((claim) => (
              <li key={claim.text} class="brief__loose">
                <Claim claim={claim} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <div class="row brief__actions">
        <button
          type="button"
          class="button button--secondary"
          onClick={() => navigate(`/match/${match.id}`)}
        >
          {t("brief.backToMatch")}
        </button>
      </div>
    </Screen>
  );
}

interface BriefEntryProps {
  item: BriefItem;
  requirement: Requirement | undefined;
  lines: Map<LineId, CvLine>;
}

function BriefEntry({ item, requirement, lines }: BriefEntryProps) {
  // A record written by an older version can name a requirement this match no
  // longer carries. The id is the honest fallback; inventing a heading here
  // would be the app describing something it cannot see.
  const heading = requirement?.text ?? item.requirement_id;
  const cited = item.line_ids.map((id) => lines.get(id)).filter(isLine);

  return (
    <li class="brief">
      <div class="brief__head">
        <h3 class="brief__requirement">
          {item.risk === "no_evidence" ? (
            <MarkerHighlight status="missing">{heading}</MarkerHighlight>
          ) : (
            heading
          )}
        </h3>
        {item.kind === "must" && <span class="brief__must small">{t("map.mustHave")}</span>}
      </div>

      {/* Only the risks get a sentence. Repeating "a line from your CV backs
          this" under every receipt is noise the heading already said, and the
          mark under it says it better. */}
      {item.risk !== "proved" && (
        <p class="brief__verdict">{t(`brief.risk.${item.risk}`)}</p>
      )}

      {cited.length > 0 && (
        <ul class="stack stack--tight brief__lines">
          {cited.map((line) => (
            <li key={line.id} class="brief__line">
              {/* The full mark means one thing in this app: a receipt. A line
                  that only lists the skill does not get it, whatever the
                  match called the requirement. */}
              <p class="brief__quote">
                {item.risk === "proved" ? (
                  <MarkerHighlight status="strong">{line.text}</MarkerHighlight>
                ) : (
                  line.text
                )}
              </p>
              <div class="row brief__chips">
                <SourceChip line={line.id} />
                {line.added_at && <span class="small muted">{t("cv.preview.addedByYou")}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}

      {item.claims.length > 0 && (
        <div class="stack stack--tight brief__claims">
          <p class="small muted">{t("brief.claimsLabel")}</p>
          {item.claims.map((claim) => (
            <Claim key={`${claim.source}-${claim.text}`} claim={claim} />
          ))}
        </div>
      )}
    </li>
  );
}

/**
 * A sentence the user already sent.
 *
 * Quoted exactly, because the wording is the point: this is what the person
 * across the table is reading back.
 */
function Claim({ claim }: { claim: BriefClaim }) {
  return (
    <div class="brief__claim">
      <p class="brief__quote">{claim.text}</p>
      <div class="row brief__chips">
        <span class="small muted">{t(`brief.source.${claim.source}`)}</span>
        {claim.line_ids.map((line) => (
          <SourceChip key={line} line={line} />
        ))}
      </div>
    </div>
  );
}

function isLine(line: CvLine | undefined): line is CvLine {
  return line !== undefined;
}
