/**
 * The shell: header, preview banner, and whichever screen the route names.
 */

import { useEffect } from "preact/hooks";

import { AppHeader } from "./components/AppHeader";
import { PreviewBanner } from "./components/PreviewBanner";
import { AddCv } from "./screens/AddCv";
import { CvPreview } from "./screens/CvPreview";
import { Letter } from "./screens/Letter";
import { MatchMap } from "./screens/MatchMap";
import { NewMatch } from "./screens/NewMatch";
import { Onboarding } from "./screens/Onboarding";
import { Progress } from "./screens/Progress";
import { Settings } from "./screens/Settings";
import { Tailor } from "./screens/Tailor";
import { Tracker } from "./screens/Tracker";
import { t } from "./i18n";
import { route, startRouter } from "./router";
import { currentMatch, hasCv, openMatch, preview, ready } from "./state";
import { runtime } from "./lib/anna";

export function App() {
  useEffect(startRouter, []);

  const current = route.value;

  // Reopening a saved match by URL (a reload, or a second window) has to load
  // it from storage before the map can render.
  useEffect(() => {
    if (current.name === "match" && currentMatch.value?.id !== current.id) {
      void openMatch(current.id);
    }
  }, [current.name === "match" ? current.id : null]);

  // The window chrome should say what is on screen, not just the app name.
  useEffect(() => {
    if (!ready.value) return;
    const title =
      current.name === "match" && currentMatch.value?.posting.title
        ? `${t("app.name")} — ${currentMatch.value.posting.title}`
        : t("app.name");
    void runtime().window.set_title({ title });
  }, [current.name, currentMatch.value?.id, ready.value]);

  if (!ready.value) {
    return (
      <div class="boot" role="status">
        {t("common.loading")}
      </div>
    );
  }

  return (
    <>
      {preview.value && <PreviewBanner />}
      <AppHeader />
      {renderScreen(current.name)}
    </>
  );
}

function renderScreen(name: string) {
  switch (name) {
    case "cv-add":
      return <AddCv />;
    case "cv-preview":
      return <CvPreview />;
    case "new-match":
      return <NewMatch />;
    case "progress":
      return <Progress />;
    case "match":
      return <MatchMap />;
    case "tailor":
      return <Tailor />;
    case "letter":
      return <Letter />;
    case "tracker":
      return <Tracker />;
    case "settings":
      return <Settings />;
    default:
      // A returning user with a CV lands on their matches, not the pitch.
      return hasCv.value ? <Tracker /> : <Onboarding />;
  }
}
