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
import { ErrorNotice } from "../components/ErrorNotice";
import { RequirementItem } from "../components/RequirementItem";
import { Screen } from "../components/Screen";
import { SummarySentence } from "../components/SummarySentence";
import { summarySentence, t } from "../i18n";
import { navigate } from "../router";
import {
  activeCv,
  arrivedEvidence,
  assertEvidence,
  asserting,
  assertions,
  currentMatch,
  dismissError,
  earlierRun,
  error,
  showingExample,
  startAsserting,
} from "../state";
import type { Evidence, LineId, RequirementId, Status } from "../lib/types";
import "./MatchMap.css";

type Pane = "requirements" | "cv";

export function MatchMap() {
  const [pane, setPane] = useState<Pane>("requirements");
  const [selected, setSelected] = useState<LineId | null>(null);
  const [copied, setCopied] = useState(false);
  const [picked, setPicked] = useState<LineId[]>([]);
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

  /**
   * Evidence for a requirement, or an honest "no evidence yet".
   *
   * `run_match` guarantees one entry per requirement, but this screen also
   * renders records written by earlier versions and read back from storage.
   * A missing entry means nothing was proven, which is exactly `missing`.
   */
  function evidenceOf(id: RequirementId): Evidence {
    return (
      evidenceFor.get(id) ?? { requirement_id: id, status: "missing", line_ids: [], why: "" }
    );
  }
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
      // The JS argument overrides `scroll-behavior` from CSS, so the reduced
      // motion preference has to be read here too.
      const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
      target?.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
    });
  }

  /**
   * Start disagreeing with a verdict: the sheet becomes the picker.
   *
   * The CV pane is already on screen with every line numbered, so there is no
   * separate chooser to build and nothing new for the user to learn — they
   * point at the lines they mean, in the document they are looking at.
   */
  function beginDispute(requirementId: string): void {
    setPicked(assertions.value[requirementId]?.line_ids ?? []);
    startAsserting(requirementId);
    setPane("cv");
  }

  function togglePick(line: LineId): void {
    setPicked((current) =>
      current.includes(line) ? current.filter((item) => item !== line) : [...current, line],
    );
  }

  function cancelDispute(): void {
    startAsserting(null);
    setPicked([]);
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

  const unproven = match.summary.missing + match.summary.partial;
  const disputed = match.requirements.find((item) => item.id === asserting.value) ?? null;
  const assertedCount = match.requirements.filter((item) => assertions.value[item.id]).length;
  const role = match.posting.title ?? t("tracker.untitledRole");
  const company = match.posting.company;

  return (
    <Screen wide>
      {/* `finishMatch` sets `save_failed` and lands the user here, so this
          is the screen that has to say it: the analysis is on screen and the
          record is not, and the copy tells them to take what they need
          before they close the window. */}
      {error.value && <ErrorNotice error={error.value} onDismiss={dismissError} />}

      <div class="stack stack--tight map__head">
        <h1>{role}</h1>
        {company ? <p class="lede">{company}</p> : <p class="lede">{t("map.noPosting")}</p>}
        <SummarySentence summary={match.summary} />
        {/* Never folded into the sentence above. That sentence is what the app
            found; this is what the person said, and the two counts stay
            separate for the same reason the record does. */}
        {assertedCount > 0 && (
          <p class="map__asserted small muted">
            {assertedCount === 1
              ? t("map.assertedCountOne")
              : t("map.assertedCountMany", { count: assertedCount })}
          </p>
        )}
        {/* Only on a second run of the same posting, which is rare and is
            exactly when the app finally has something to report about the
            sentences the user has been writing into their CV. */}
        {earlierRun.value && (
          <p class="map__again">
            {t("map.ranBefore")}{" "}
            <button
              type="button"
              class="button button--quiet map__againLink"
              onClick={() => navigate("/changed")}
            >
              {t("map.seeWhatChanged")}
            </button>
          </p>
        )}
        {showingExample.value && <p class="small muted">{t("common.exampleNote")}</p>}
      </div>

      <div class="map__tabs" role="tablist" aria-label={t("map.requirements")}>
        <button
          type="button"
          role="tab"
          aria-selected={pane === "requirements"}
          aria-controls="map-requirements"
          id="map-tab-requirements"
          class={`tab${pane === "requirements" ? " tab--current" : ""}`}
          onClick={() => setPane("requirements")}
        >
          {t("map.requirements")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={pane === "cv"}
          aria-controls="map-cv"
          id="map-tab-cv"
          class={`tab${pane === "cv" ? " tab--current" : ""}`}
          onClick={() => setPane("cv")}
        >
          {t("map.yourCv")}
        </button>
      </div>

      <div class="map" data-pane={pane}>
        <div class="map__requirements" id="map-requirements" role="tabpanel" aria-labelledby="map-tab-requirements">
          {musts.length > 0 && (
            <section class="stack stack--tight">
              <h2 class="map__group">{t("map.mustHave")}</h2>
              <ul class="list">
                {musts.map((requirement, index) => (
                  <RequirementItem
                    key={requirement.id}
                    requirement={requirement}
                    evidence={evidenceOf(requirement.id)}
                    animate={arrivedEvidence.value.has(requirement.id)}
                    sweepIndex={index}
                    onSelectLine={selectLine}
                    assertion={assertions.value[requirement.id] ?? null}
                    disputing={asserting.value === requirement.id}
                    {...(showingExample.value
                      ? {}
                      : {
                          onDispute: () => beginDispute(requirement.id),
                          onWithdraw: () => void assertEvidence(requirement.id, []),
                        })}
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
                    evidence={evidenceOf(requirement.id)}
                    animate={arrivedEvidence.value.has(requirement.id)}
                    sweepIndex={musts.length + index}
                    onSelectLine={selectLine}
                    assertion={assertions.value[requirement.id] ?? null}
                    disputing={asserting.value === requirement.id}
                    {...(showingExample.value
                      ? {}
                      : {
                          onDispute: () => beginDispute(requirement.id),
                          onWithdraw: () => void assertEvidence(requirement.id, []),
                        })}
                  />
                ))}
              </ul>
            </section>
          )}
        </div>

        <div class="map__cv" id="map-cv" role="tabpanel" aria-labelledby="map-tab-cv">
          {/* "No evidence yet" reads very differently when the evidence was
              cut off or scrambled on the way in. The warning belongs next to
              the verdicts, not only on the screen where the CV was added. */}
          {doc.warnings.length > 0 && (
            <ul class="stack stack--tight map__warnings">
              {doc.warnings.map((warning) => (
                <li key={warning} class="cvwarning">
                  {t(`cv.warning.${warning}`)}
                </li>
              ))}
            </ul>
          )}
          {/* The picker lives above the sheet rather than in a dialog: the
              thing being chosen from is the document underneath it, and a
              modal would cover the only thing the user needs to read. */}
          {disputed && (
            <div class="stack stack--tight map__picker" role="group" aria-label={t("map.assertHeading")}>
              <p class="map__pickerAsk">
                {t("map.assertAsk", { requirement: disputed.text })}
              </p>
              <p class="small muted">{t("map.assertNote")}</p>
              <div class="row">
                <button
                  type="button"
                  class="button map__assertSave"
                  disabled={picked.length === 0}
                  onClick={() => {
                    void assertEvidence(disputed.id, picked);
                    setPicked([]);
                    setPane("requirements");
                  }}
                >
                  {picked.length === 0
                    ? t("map.assertPickSome")
                    : picked.length === 1
                      ? t("map.assertSaveOne")
                      : t("map.assertSave", { count: picked.length })}
                </button>
                <button type="button" class="button button--quiet" onClick={cancelDispute}>
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          )}
          <DocumentSheet title={t("map.yourCv")} scrollRef={(element) => (sheetRef.current = element)}>
            {doc.lines.map((line) => (
              <CvLine
                key={line.id}
                line={line}
                {...(statusByLine.get(line.id) ? { status: statusByLine.get(line.id)! } : {})}
                highlighted={selected === line.id}
                {...(disputed
                  ? { onPick: togglePick, picked: picked.includes(line.id) }
                  : {})}
              />
            ))}
          </DocumentSheet>
        </div>
      </div>

      {/* Seven ways on is a row nobody reads, so weight does the grouping
          rather than a divider: what you write *now* (one primary, then the
          two that share its sitting — the letter box and the form's own
          questions are filled in together), then, quieter, what you prepare
          for later, and last the two things that take something out of the
          app. */}
      <div class="row map__actions">
        <button type="button" class="button" onClick={() => navigate("/tailor")}>
          {t("map.tailor")}
        </button>
        <button type="button" class="button button--secondary" onClick={() => navigate("/letter")}>
          {t("map.letter")}
        </button>
        <button type="button" class="button button--secondary" onClick={() => navigate("/answers")}>
          {t("map.answers")}
        </button>
        {/* Only when there is something to prepare for. On a match that proves
            everything, the button would promise a screen with nothing on it. */}
        {unproven > 0 && (
          <button type="button" class="button button--quiet" onClick={() => navigate("/gaps")}>
            {t("map.gaps")}
          </button>
        )}
        {/* The night before an interview is the one time someone opens a
            match they already sent, so the way in sits with the actions
            rather than behind the tracker's status dropdown alone. */}
        <button type="button" class="button button--quiet" onClick={() => navigate("/brief")}>
          {t("map.brief")}
        </button>
        {/* The picture the growth plan is built on (`plan.md §9`), and the
            only artefact in this app designed to leave the account — so it is
            built from counts and enums and cannot carry a CV line. */}
        {/* The two that take something out of the app travel together, so
            they move to the end of the bar as a pair — pushing one of them
            alone left the other stranded on a second line. */}
        <div class="row map__takeaways">
          <button type="button" class="button button--quiet" onClick={() => navigate("/share")}>
            {t("map.share")}
          </button>
          <button type="button" class="button button--quiet" onClick={() => void copySummary()}>
            {copied ? t("map.copied") : t("map.copySummary")}
          </button>
        </div>
      </div>
    </Screen>
  );
}
