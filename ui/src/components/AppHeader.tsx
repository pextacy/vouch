/**
 * The app chrome: identity on the left, navigation in the middle, the one
 * primary action on the right.
 *
 * At phone width the navigation collapses to the tabs and the primary action
 * keeps its place, because "New match" is the thing a returning user opens the
 * app to press.
 */

import { t } from "../i18n";
import { navigate, route } from "../router";
import { hasCv } from "../state";
import "./AppHeader.css";

export function AppHeader() {
  const current = route.value.name;
  const onTracker = current === "tracker";
  const onCv = current === "cv-add" || current === "cv-preview";

  return (
    <header class="appbar">
      <a class="appbar__brand" href="#/" aria-label={t("app.name")}>
        <span class="appbar__mark" aria-hidden="true" />
        <span class="appbar__name">{t("app.name")}</span>
      </a>

      <nav class="appbar__nav" aria-label={t("app.name")}>
        <a class={`tab${onTracker ? " tab--current" : ""}`} href="#/matches">
          {t("nav.matches")}
        </a>
        <a class={`tab${onCv ? " tab--current" : ""}`} href={hasCv.value ? "#/cv/preview" : "#/cv/add"}>
          {t("nav.cv")}
        </a>
        <a class={`tab${current === "settings" ? " tab--current" : ""}`} href="#/data">
          {t("nav.data")}
        </a>
      </nav>

      <button
        type="button"
        class="button appbar__action"
        onClick={() => navigate(hasCv.value ? "/new" : "/cv/add")}
      >
        {t("nav.newMatch")}
      </button>
    </header>
  );
}
