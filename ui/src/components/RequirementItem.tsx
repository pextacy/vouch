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
import type { Evidence, LineId, Requirement } from "../lib/types";
import "./RequirementItem.css";

interface RequirementItemProps {
  requirement: Requirement;
  evidence: Evidence;
  animate?: boolean;
  sweepIndex?: number;
  onSelectLine?: (line: LineId) => void;
}

export function RequirementItem({
  requirement,
  evidence,
  animate,
  sweepIndex,
  onSelectLine,
}: RequirementItemProps) {
  const { status } = evidence;
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

      {evidence.line_ids.length > 0 && (
        <div class="row req__chips">
          {evidence.line_ids.map((line) => (
            <SourceChip key={line} line={line} {...(onSelectLine ? { onSelect: onSelectLine } : {})} />
          ))}
        </div>
      )}

      {status === "missing" && requirement.kind === "must" && (
        <p class="req__note small muted">{t("map.missingNote")}</p>
      )}
    </li>
  );
}
