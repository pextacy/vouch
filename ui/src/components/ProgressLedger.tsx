/**
 * What the engine is doing, stage by stage.
 *
 * No percentage and no bar: the honest information is which step is running,
 * and a number that jumps from 30 to 70 invites the user to feel lied to. The
 * requirements appear as they are extracted, so the wait shows real work.
 */

import { t } from "../i18n";
import type { ProgressEvent, Stage } from "../lib/types";
import "./ProgressLedger.css";

const STAGES: Stage[] = ["normalize", "extract", "match", "guard", "summarize"];

export function ProgressLedger({ progress }: { progress: ProgressEvent | null }) {
  const current = progress?.stage ?? "normalize";
  const index = STAGES.indexOf(current === "done" ? "summarize" : current);

  return (
    <ol class="ledger" aria-live="polite">
      {STAGES.map((stage, position) => {
        const state =
          current === "done" || position < index ? "done" : position === index ? "current" : "waiting";
        return (
          <li key={stage} class={`ledger__row ledger__row--${state}`}>
            <span class="ledger__dot" aria-hidden="true" />
            <span class="ledger__label">{t(`progress.stage.${stage}`)}</span>
          </li>
        );
      })}
    </ol>
  );
}
