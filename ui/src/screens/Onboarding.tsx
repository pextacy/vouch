/**
 * First run.
 *
 * One promise, three claims that back it, and two ways forward: add a CV, or
 * see what the output looks like first. The example is a recorded fixture and
 * never calls the model, so curiosity costs nothing and counts as nothing.
 */

import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { navigate } from "../router";
import { showExample } from "../state";
import "./Onboarding.css";

export function Onboarding() {
  return (
    <Screen heading={t("onboarding.heading")} lede={t("onboarding.body")}>
      <ul class="promises">
        <li class="promises__item">{t("onboarding.point1")}</li>
        <li class="promises__item">{t("onboarding.point2")}</li>
        <li class="promises__item">{t("onboarding.point3")}</li>
      </ul>

      <div class="row">
        <button type="button" class="button" onClick={() => navigate("/cv/add")}>
          {t("onboarding.primary")}
        </button>
        <button type="button" class="button button--secondary" onClick={showExample}>
          {t("onboarding.secondary")}
        </button>
      </div>
    </Screen>
  );
}
