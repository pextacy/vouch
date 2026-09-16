/**
 * The match map — the screen the whole product exists to show.
 *
 * Requirements on the left in reading order, the CV sheet on the right, and a
 * click on any citation scrolls the sheet to that line. Below 900px the two
 * become tabs rather than stacking, so the CV is one tap away instead of a
 * long scroll away.
 */

import { useRef, useState } from "preact/hooks";

import { CvLine } from "../components/CvLine";
import { DocumentSheet } from "../components/DocumentSheet";
import { EmptyState } from "../components/EmptyState";
import { RequirementItem } from "../components/RequirementItem";
import { Screen } from "../components/Screen";
import { SummarySentence } from "../components/SummarySentence";
import { summarySentence, t } from "../i18n";
import { navigate } from "../router";
import {
  activeCv,
  arrivedEvidence,
  currentMatch,
  showingExample,
} from "../state";
import type { LineId, Status } from "../lib/types";
import "./MatchMap.css";

type Pane = "requirements" | "cv";

export function MatchMap() {
  const [pane, setPane] = useState<Pane>("requirements");
  const [selected, setSelected] = useState<LineId | null>(null);
  const [copied, setCopied] = useState(false);
  const sheetRef = useRef<HTMLDivElement | null>(null);

  const match = currentMatch.value;
  const doc = activeCv();

  if (!match || !doc) {
    return (
      <Screen heading={t("tracker.heading")}>
        <EmptyState
          text={t("tracker.empty")}
          action={
            <button type="button" class="button" onClick={() => navigate("/new")}>
              {t("nav.newMatch")}
            </button>
          }
        />
      </Screen>
    );
  }

  const evidenceFor = new Map(match.evidence.map((item) => [item.requirement_id, item]));
  const statusByLine = new Map<string, Status>();
  for (const item of match.evidence) {
    for (const line of item.line_ids) {
      // A line cited as strong evidence anywhere is shown fully marked; the
      // strongest claim wins so one partial mention cannot dim it.
      if (item.status === "strong" || !statusByLine.has(line)) {
        statusByLine.set(line, item.status);
      }
    }
  }

  const musts = match.requirements.filter((requirement) => requirement.kind === "must");
  const nices = match.requirements.filter((requirement) => requirement.kind === "nice");

  function selectLine(line: LineId): void {
    setSelected(line);
    setPane("cv");
    // Let the pane switch paint before scrolling to the line inside it.
    requestAnimationFrame(() => {
      const target = sheetRef.current?.querySelector(`#cv-${line}`);
      target?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  }

  async function copySummary(): Promise<void> {
    const text = `${summarySentence(
      match!.summary.total,
      match!.summary.strong + match!.summary.partial,
      match!.summary.must_missing,
    )} — ${t("app.name")}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard permission can be refused; the sentence is on screen anyway.
    }
  }

  const role = match.posting.title ?? t("tracker.untitledRole");
  const company = match.posting.company;

  return (
    <Screen wide>
      <div class="stack stack--tight map__head">
        <h1>{role}</h1>
        {company ? <p class="lede">{company}</p> : <p class="lede">{t("map.noPosting")}</p>}
        <SummarySentence summary={match.summary} />
        {showingExample.value && <p class="small muted">{t("common.exampleNote")}</p>}
      </div>

      <div class="map__tabs" role="tablist" aria-label={t("map.requirements")}>
        <button
          type="button"
          role="tab"
          aria-selected={pane === "requirements"}
          class={`tab${pane === "requirements" ? " tab--current" : ""}`}
          onClick={() => setPane("requirements")}
        >
          {t("map.requirements")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={pane === "cv"}
          class={`tab${pane === "cv" ? " tab--current" : ""}`}
          onClick={() => setPane("cv")}
        >
          {t("map.yourCv")}
        </button>
      </div>

      <div class="map" data-pane={pane}>
        <div class="map__requirements">
          {musts.length > 0 && (
            <section class="stack stack--tight">
              <h2 class="map__group">{t("map.mustHave")}</h2>
              <ul class="list">
                {musts.map((requirement, index) => (
                  <RequirementItem
                    key={requirement.id}
                    requirement={requirement}
                    evidence={evidenceFor.get(requirement.id)!}
                    animate={arrivedEvidence.value.has(requirement.id)}
                    sweepIndex={index}
                    onSelectLine={selectLine}
                  />
                ))}
              </ul>
            </section>
          )}

          {nices.length > 0 && (
            <section class="stack stack--tight map__nice">
              <h2 class="map__group">{t("map.niceToHave")}</h2>
              <ul class="list">
                {nices.map((requirement, index) => (
                  <RequirementItem
                    key={requirement.id}
                    requirement={requirement}
                    evidence={evidenceFor.get(requirement.id)!}
                    animate={arrivedEvidence.value.has(requirement.id)}
                    sweepIndex={musts.length + index}
                    onSelectLine={selectLine}
                  />
                ))}
              </ul>
            </section>
          )}
        </div>

        <div class="map__cv">
          <DocumentSheet title={t("map.yourCv")} scrollRef={(element) => (sheetRef.current = element)}>
            {doc.lines.map((line) => (
              <CvLine
                key={line.id}
                line={line}
                {...(statusByLine.get(line.id) ? { status: statusByLine.get(line.id)! } : {})}
                highlighted={selected === line.id}
              />
            ))}
          </DocumentSheet>
        </div>
      </div>

      <div class="row map__actions">
        <button type="button" class="button" onClick={() => navigate("/tailor")}>
          {t("map.tailor")}
        </button>
        <button type="button" class="button button--secondary" onClick={() => navigate("/letter")}>
          {t("map.letter")}
        </button>
        <button type="button" class="button button--quiet" onClick={() => void copySummary()}>
          {copied ? t("map.copied") : t("map.copySummary")}
        </button>
      </div>
    </Screen>
  );
}
