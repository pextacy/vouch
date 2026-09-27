/**
 * The shell: header, preview banner, and whichever screen the route names.
 */

import { useEffect } from "preact/hooks";

import { AppHeader } from "./components/AppHeader";
import { PreviewBanner } from "./components/PreviewBanner";
import { AddCv } from "./screens/AddCv";
import { Answers } from "./screens/Answers";
import { Changed } from "./screens/Changed";
import { Check } from "./screens/Check";
import { Compare } from "./screens/Compare";
import { CvAudit } from "./screens/CvAudit";
import { CvPreview } from "./screens/CvPreview";
import { Followup } from "./screens/Followup";
import { Gaps } from "./screens/Gaps";
import { Interview } from "./screens/Interview";
import { Ledger } from "./screens/Ledger";
import { Letter } from "./screens/Letter";
import { MatchMap } from "./screens/MatchMap";
import { NewMatch } from "./screens/NewMatch";
import { Onboarding } from "./screens/Onboarding";
import { Profile } from "./screens/Profile";
import { Progress } from "./screens/Progress";
import { Recurring } from "./screens/Recurring";
import { Settings } from "./screens/Settings";
import { Share } from "./screens/Share";
import { Since } from "./screens/Since";
import { Tailor } from "./screens/Tailor";
import { Tracker } from "./screens/Tracker";
import { Worth } from "./screens/Worth";
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
    case "cv-audit":
      return <CvAudit />;
    case "cv-ledger":
      return <Ledger />;
    case "cv-profile":
      return <Profile />;
    case "check":
      return <Check />;
    case "new-match":
      return <NewMatch />;
    case "progress":
      return <Progress />;
    case "match":
      return <MatchMap />;
    case "tailor":
      return <Tailor />;
    case "gaps":
      return <Gaps />;
    case "letter":
      return <Letter />;
    case "answers":
      return <Answers />;
    case "share":
      return <Share />;
    case "brief":
      return <Interview />;
    case "since":
      return <Since />;
    case "followup":
      return <Followup />;
    case "changed":
      return <Changed />;
    case "worth":
      return <Worth />;
    case "tracker":
      return <Tracker />;
    case "recurring":
      return <Recurring />;
    case "compare":
      return <Compare />;
    case "settings":
      return <Settings />;
    default:
      // A returning user with a CV lands on their matches, not the pitch.
      return hasCv.value ? <Tracker /> : <Onboarding />;
  }
}
