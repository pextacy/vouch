/**
 * Which CV is open, and the way to add another.
 *
 * A career switcher sends two different documents to two different kinds of
 * role, and the app held one until v1.2 — which was inconvenient for tailoring
 * and quietly wrong for the screens that read across applications, because a
 * report drawn from both careers names a gap half of them never asked about.
 *
 * The switch is deliberately plain and deliberately loud about what it does:
 * changing the CV changes the applications on screen too, so the sentence
 * under the tabs is part of the control, not decoration around it. Nothing
 * appears at all for someone who has one CV and has never asked for another —
 * the row is one quiet button until it has something to switch between.
 */

import { t } from "../i18n";
import { activeCvId, canAddCv, cvProfiles, startAnotherCv, useCv } from "../state";
import "./CvSwitch.css";

export function CvSwitch() {
  const profiles = cvProfiles.value;
  const several = profiles.length > 1;
  if (!several && !canAddCv.value) return null;

  return (
    <div class="cvswitch">
      <div class="cvswitch__row">
        {several && (
          <nav class="cvswitch__list" aria-label={t("cv.profiles.label")}>
            {profiles.map((profile) => {
              const current = profile.id === activeCvId.value;
              return (
                <button
                  key={profile.id}
                  type="button"
                  class={`tab${current ? " tab--current" : ""}`}
                  aria-current={current ? "true" : undefined}
                  onClick={() => void useCv(profile.id)}
                >
                  {profile.name}
                </button>
              );
            })}
          </nav>
        )}
        {canAddCv.value && (
          <button type="button" class="button button--quiet" onClick={startAnotherCv}>
            {t("cv.profiles.add")}
          </button>
        )}
      </div>
      <p class="small muted cvswitch__note">
        {several ? t("cv.profiles.note") : t("cv.profiles.why")}
      </p>
    </div>
  );
}
