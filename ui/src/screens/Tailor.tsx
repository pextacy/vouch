/**
 * Suggested bullets.
 *
 * A dropped suggestion is shown, not hidden. "We couldn't strengthen this line
 * without adding facts that aren't in your CV" is the product working — hiding
 * it would leave the user wondering why a line they expected never appeared.
 */

import { useEffect } from "preact/hooks";

import { BulletDiff } from "../components/BulletDiff";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  acceptBullet,
  acceptedBullets,
  currentMatch,
  dismissError,
  error,
  runTailor,
  showingExample,
  skipBullet,
  tailorPhase,
  tailorResult,
} from "../state";
import "./Tailor.css";

export function Tailor() {
  const match = currentMatch.value;
  const result = tailorResult.value;
  const phase = tailorPhase.value;

  useEffect(() => {
    if (match && !result && phase === "idle" && !showingExample.value) {
      void runTailor();
    }
  }, [match?.id, result, phase]);

  if (!match) {
    navigate("/matches");
    return null;
  }

  return (
    <Screen heading={t("tailor.heading")} lede={t("tailor.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runTailor()} onDismiss={dismissError} />
      )}

      {phase === "running" && <p class="muted" aria-live="polite">{t("tailor.running")}</p>}

      {result && result.bullets.length === 0 && <EmptyState text={t("tailor.empty")} />}

      {result && result.bullets.length > 0 && (
        <ul class="list">
          {result.bullets.map((bullet) => {
            const key = bullet.source_line_ids[0] ?? bullet.original.slice(0, 24);
            return (
              <BulletDiff
                key={key}
                bullet={bullet}
                accepted={acceptedBullets.value[key]}
                readOnly={showingExample.value}
                onAccept={(text) => acceptBullet(key, text)}
                onSkip={() => skipBullet(key)}
              />
            );
          })}
        </ul>
      )}

      <div class="row">
        <button type="button" class="button" onClick={() => navigate("/letter")}>
          {t("map.letter")}
        </button>
        <button
          type="button"
          class="button button--secondary"
          onClick={() => navigate(`/match/${match.id}`)}
        >
          {t("nav.back")}
        </button>
      </div>
    </Screen>
  );
}
