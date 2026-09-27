/**
 * One requirement and its evidence.
 *
 * The order is the argument: the requirement, then the quote from the posting
 * it came from, then the CV line that backs it. A user should be able to
 * disagree with any step by looking at it.
 */

import { MarkerHighlight } from "./MarkerHighlight";
import { SourceChip } from "./SourceChip";
import { StatusLabel } from "./StatusLabel";
import { t } from "../i18n";
import type { Assertion, Evidence, LineId, Requirement } from "../lib/types";
import "./RequirementItem.css";

interface RequirementItemProps {
  requirement: Requirement;
  evidence: Evidence;
  animate?: boolean;
  sweepIndex?: number;
  onSelectLine?: (line: LineId) => void;
  /** What the user said covers this, when they disagreed with the verdict. */
  assertion?: Assertion | null;
  /** Start picking CV lines for this requirement. Absent = not offered. */
  onDispute?: () => void;
  onWithdraw?: () => void;
  /** True while this is the requirement being picked for. */
  disputing?: boolean;
}

export function RequirementItem({
  requirement,
  evidence,
  animate,
  sweepIndex,
  onSelectLine,
  assertion,
  onDispute,
  onWithdraw,
  disputing,
}: RequirementItemProps) {
  const { status } = evidence;
  const unshown = evidence.unshown ?? [];
  return (
    <li class="req">
      <div class="req__head">
        <h3 class="req__text">
          {status === "missing" ? (
            <MarkerHighlight status="missing">{requirement.text}</MarkerHighlight>
          ) : (
            requirement.text
          )}
        </h3>
        <StatusLabel status={status} />
      </div>

      {requirement.source_quote && (
        <p class="req__quote">“{requirement.source_quote}”</p>
      )}

      {evidence.why && status !== "missing" && (
        <p class="req__why">
          <MarkerHighlight
            status={status}
            animate={animate ?? false}
            sweepIndex={sweepIndex ?? 0}
          >
            {evidence.why}
          </MarkerHighlight>
        </p>
      )}

      {/* Why this is "Related" and not "Evidenced": the posting named a thing
          and the line under it does not contain that thing. Said in the same
          quiet voice as everything else — the verdict got smaller, nobody is
          being accused of anything. */}
      {unshown.length > 0 && (
        <p class="req__guard">
          {unshown.length === 1
            ? t("map.unshownOne", { term: unshown[0]! })
            : t("map.unshownMany", { terms: unshown.join(", ") })}
        </p>
      )}

      {evidence.line_ids.length > 0 && (
        <div class="row req__chips">
          {evidence.line_ids.map((line) => (
            <SourceChip key={line} line={line} {...(onSelectLine ? { onSelect: onSelectLine } : {})} />
          ))}
        </div>
      )}

      {status === "missing" && requirement.kind === "must" && !assertion && (
        <p class="req__note small muted">{t("map.missingNote")}</p>
      )}

      {/* The correction, shown beside the verdict rather than replacing it.
          Both readings stay on screen because they are two different facts:
          what the app could find, and what the person says is there. */}
      {assertion && (
        <div class="stack stack--tight req__asserted">
          <p class="req__assertedNote">{t("map.assertedNote")}</p>
          <div class="row req__chips">
            {assertion.line_ids.map((line) => (
              <SourceChip
                key={line}
                line={line}
                {...(onSelectLine ? { onSelect: onSelectLine } : {})}
              />
            ))}
          </div>
          {onWithdraw && (
            <div class="row">
              <button type="button" class="button button--quiet req__dispute" onClick={onWithdraw}>
                {t("map.assertUndo")}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Offered only where the app came up short. Arguing the other way —
          "that line does not prove it" — is a different feature and would
          need the app to agree it was wrong about something it did find. */}
      {onDispute && !assertion && status !== "strong" && (
        <div class="row">
          <button
            type="button"
            class="button button--quiet req__dispute"
            aria-pressed={disputing ?? false}
            onClick={onDispute}
          >
            {disputing ? t("map.assertPicking") : t("map.assertStart")}
          </button>
        </div>
      )}
    </li>
  );
}
