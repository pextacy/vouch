/**
 * Paste a job posting and run the match.
 *
 * The URL field sits under the paste box, not above it: `web.fetch` is gated
 * by a per-app grant that is off by default, so pasting is the path that
 * always works and the link is the convenience.
 */

import { useState } from "preact/hooks";

import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { t } from "../i18n";
import { navigate } from "../router";
import {
  dismissError,
  error,
  fetchPosting,
  hasCv,
  postingText,
  postingUrl,
  startMatch,
  urlPhase,
} from "../state";
import "./NewMatch.css";

export function NewMatch() {
  const [url, setUrl] = useState(postingUrl.value);
  const fetching = urlPhase.value === "running";
  const ready = postingText.value.trim().length > 120;

  if (!hasCv.value) {
    return (
      <Screen heading={t("match.new.heading")}>
        <p class="lede">{t("match.new.needCv")}</p>
        <div class="row">
          <button type="button" class="button" onClick={() => navigate("/cv/add")}>
            {t("onboarding.primary")}
          </button>
        </div>
      </Screen>
    );
  }

  return (
    <Screen heading={t("match.new.heading")} lede={t("match.new.body")}>
      {error.value && <ErrorNotice error={error.value} onDismiss={dismissError} />}

      <div class="field">
        <label class="visually-hidden" for="posting">
          {t("match.new.heading")}
        </label>
        <textarea
          id="posting"
          class="textarea posting"
          placeholder={t("match.new.placeholder")}
          value={postingText.value}
          onInput={(event) => (postingText.value = (event.target as HTMLTextAreaElement).value)}
        />
      </div>

      <div class="field">
        <label class="field__label" for="posting-url">
          {t("match.new.urlLabel")}
        </label>
        <div class="row">
          <input
            id="posting-url"
            class="input posting__url"
            type="url"
            inputMode="url"
            placeholder={t("match.new.urlPlaceholder")}
            value={url}
            onInput={(event) => setUrl((event.target as HTMLInputElement).value)}
          />
          <button
            type="button"
            class="button button--secondary"
            disabled={fetching || !url.trim()}
            onClick={() => void fetchPosting(url.trim())}
          >
            {fetching ? t("match.new.fetching") : t("match.new.fetch")}
          </button>
        </div>
      </div>

      <div class="row">
        <button type="button" class="button" disabled={!ready} onClick={() => void startMatch()}>
          {t("match.new.run")}
        </button>
      </div>
    </Screen>
  );
}
