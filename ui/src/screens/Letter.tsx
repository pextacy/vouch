/**
 * The cover letter.
 *
 * Citations are visible by default and the placeholder warning is loud,
 * because "[Company]" reaching a recruiter is the one embarrassing failure
 * this screen can cause.
 */

import { useEffect, useState } from "preact/hooks";

import { DocumentSheet } from "../components/DocumentSheet";
import { ErrorNotice } from "../components/ErrorNotice";
import { LetterParagraph } from "../components/LetterParagraph";
import { Screen } from "../components/Screen";
import { ToneSwitch } from "../components/ToneSwitch";
import { DownloadIcon } from "../components/Icons";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  currentMatch,
  dismissError,
  error,
  exportDocument,
  exportPhase,
  letterLength,
  letterPhase,
  letterResult,
  letterTone,
  runLetter,
  showingExample,
} from "../state";
import "./Letter.css";

export function Letter() {
  const [showCitations, setShowCitations] = useState(true);
  const [copied, setCopied] = useState(false);

  const match = currentMatch.value;
  const result = letterResult.value;
  const phase = letterPhase.value;
  const busy = phase === "running";

  useEffect(() => {
    if (match && !result && phase === "idle" && !showingExample.value) {
      void runLetter();
    }
  }, [match?.id, result, phase]);

  if (!match) {
    navigate("/matches");
    return null;
  }

  async function copy(): Promise<void> {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.paragraphs.map((p) => p.text).join("\n\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // The letter is on screen and selectable either way.
    }
  }

  return (
    <Screen heading={t("letter.heading")} lede={t("letter.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runLetter()} onDismiss={dismissError} />
      )}

      <ToneSwitch
        tone={letterTone.value}
        length={letterLength.value}
        disabled={busy || showingExample.value}
        onTone={(tone) => {
          letterTone.value = tone;
          if (!showingExample.value) void runLetter();
        }}
        onLength={(length) => {
          letterLength.value = length;
          if (!showingExample.value) void runLetter();
        }}
      />

      {busy && <p class="muted" aria-live="polite">{t("letter.running")}</p>}

      {result && (
        <>
          {result.placeholders.length > 0 && (
            <p class="letter__warning">
              {t("letter.placeholderWarning", { items: result.placeholders.join(", ") })}
            </p>
          )}

          <DocumentSheet
            title={t("letter.heading")}
            actions={
              <button
                type="button"
                class="button button--quiet"
                onClick={() => setShowCitations(!showCitations)}
              >
                {showCitations ? t("letter.hideCitations") : t("letter.showCitations")}
              </button>
            }
          >
            {result.paragraphs.map((paragraph, index) => (
              <LetterParagraph key={index} paragraph={paragraph} showCitations={showCitations} />
            ))}
          </DocumentSheet>
        </>
      )}

      <div class="row">
        <button type="button" class="button button--secondary" onClick={() => void copy()}>
          {copied ? t("letter.copied") : t("letter.copy")}
        </button>
        <button
          type="button"
          class="button"
          disabled={exportPhase.value === "running" || showingExample.value}
          onClick={() => void exportDocument()}
        >
          <DownloadIcon size={16} />
          {exportPhase.value === "running" ? t("export.preparing") : t("export.download")}
        </button>
        <button
          type="button"
          class="button button--quiet"
          onClick={() => navigate(`/match/${match.id}`)}
        >
          {t("nav.back")}
        </button>
      </div>
    </Screen>
  );
}
