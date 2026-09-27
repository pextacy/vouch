/**
 * Your profile, from your CV.
 *
 * Everything else this app writes is written *at* an employer. A profile is
 * the opposite shape: nobody commissions it, it has to be true of you on any
 * day to any reader, and it is the text a recruiter searches before you have
 * applied to anything.
 *
 * Which is why the category fills it with invention — "passionate engineer
 * with a proven track record of driving impact" is written by a model that
 * was given a job title and nothing else. Here there is no posting at all,
 * so there is nothing to lend the text a word: every term has to come from a
 * CV line, and the screen shows which one.
 *
 * The headline is the part that fails most often, and failing is visible: an
 * empty headline says so out loud rather than printing something the CV
 * cannot back. A profile with an invented headline is worse than a profile
 * without one.
 */

import { useEffect, useState } from "preact/hooks";

import { DocumentSheet } from "../components/DocumentSheet";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { LetterParagraph } from "../components/LetterParagraph";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { navigate } from "../router";
import { activeCv, dismissError, error, hasCv, profilePhase, profileResult, runProfile } from "../state";
import "./Profile.css";

export function Profile() {
  const result = profileResult.value;
  const phase = profilePhase.value;
  const doc = activeCv();
  const [copied, setCopied] = useState<"headline" | "about" | null>(null);

  useEffect(() => {
    if (doc && phase === "idle") void runProfile();
  }, [doc?.hash, phase]);

  if (!hasCv.value || !doc) {
    navigate("/cv/add");
    return null;
  }

  const about = result?.about.map((paragraph) => paragraph.text).join("\n\n") ?? "";

  async function copy(what: "headline" | "about", text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // Both halves are on screen and selectable either way.
    }
  }

  return (
    <Screen heading={t("profile.heading")} lede={t("profile.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runProfile()} onDismiss={dismissError} />
      )}

      {phase === "running" && !result && (
        <p class="muted" aria-live="polite">
          {t("profile.running")}
        </p>
      )}

      {result && (
        <>
          <section class="stack stack--tight profile__section">
            <h2>{t("profile.headlineHeading")}</h2>
            {result.headline ? (
              <>
                <p class="profile__headline">{result.headline}</p>
                <div class="row profile__chips">
                  {result.headline_line_ids.map((id) => (
                    <SourceChip key={id} line={id} />
                  ))}
                  <button
                    type="button"
                    class="button button--quiet"
                    onClick={() => void copy("headline", result.headline)}
                  >
                    {copied === "headline" ? t("letter.copied") : t("profile.copyHeadline")}
                  </button>
                </div>
              </>
            ) : (
              /* Saying so is the point: the line a recruiter reads first is
                 the one nobody should let a model invent. */
              <EmptyState text={t("profile.noHeadline")} />
            )}
          </section>

          {/* The sheet's own title is the section heading here — a second
              "About" ten pixels above it was the same word doing one job
              twice, which is what the cover letter avoids too. */}
          <section class="stack stack--tight profile__section">
            <DocumentSheet
              title={t("profile.aboutHeading")}
              actions={
                <button
                  type="button"
                  class="button button--quiet"
                  onClick={() => void copy("about", about)}
                >
                  {copied === "about" ? t("letter.copied") : t("profile.copyAbout")}
                </button>
              }
            >
              {result.about.map((paragraph, index) => (
                <LetterParagraph key={index} paragraph={paragraph} showCitations />
              ))}
            </DocumentSheet>
          </section>
        </>
      )}

      <div class="row profile__actions">
        <button
          type="button"
          class="button button--secondary"
          onClick={() => navigate("/cv/preview")}
        >
          {t("profile.backToCv")}
        </button>
      </div>
    </Screen>
  );
}
