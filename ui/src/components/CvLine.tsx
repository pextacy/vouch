/**
 * One numbered CV line.
 *
 * The id is the citable handle the model returns and the user clicks, so it
 * is always visible — not a tooltip, not a hover state.
 */

import { MarkerHighlight } from "./MarkerHighlight";
import { t } from "../i18n";
import type { CvLine as CvLineModel, LineId, Status } from "../lib/types";
import "./CvLine.css";

interface CvLineProps {
  line: CvLineModel;
  status?: Status;
  highlighted?: boolean;
  animate?: boolean;
  sweepIndex?: number;
  /** Present while the user is choosing the lines that cover a requirement. */
  onPick?: (line: LineId) => void;
  picked?: boolean;
}

export function CvLine({
  line,
  status,
  highlighted,
  animate,
  sweepIndex,
  onPick,
  picked,
}: CvLineProps) {
  const classes = [
    "cvline",
    highlighted ? "cvline--current" : "",
    onPick ? "cvline--pickable" : "",
    picked ? "cvline--picked" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // A real button while picking, rather than a paragraph with a click
  // handler: the whole sheet has to stay reachable from the keyboard, and
  // `aria-pressed` is what tells a screen reader which lines are chosen.
  if (onPick) {
    return (
      <button
        type="button"
        class={classes}
        id={`cv-${line.id}`}
        data-line={line.id}
        aria-pressed={picked ?? false}
        onClick={() => onPick(line.id)}
      >
        <Body line={line} status={status} animate={animate} sweepIndex={sweepIndex} />
      </button>
    );
  }

  return (
    <p class={classes} id={`cv-${line.id}`} data-line={line.id}>
      <Body line={line} status={status} animate={animate} sweepIndex={sweepIndex} />
    </p>
  );
}

function Body({
  line,
  status,
  animate,
  sweepIndex,
}: Pick<CvLineProps, "line" | "status" | "animate" | "sweepIndex">) {
  return (
    <>
      <span class="cvline__id numeric" aria-hidden="true">
        {line.id}
      </span>
      <span class="cvline__text">
        {status && status !== "missing" ? (
          <MarkerHighlight status={status} animate={animate ?? false} sweepIndex={sweepIndex ?? 0}>
            {line.text}
          </MarkerHighlight>
        ) : (
          line.text
        )}
        {/* A line the user typed answering a gap question is evidence like any
            other, and it should say where it came from — the app's whole claim
            is that you can see the provenance of everything. */}
        {line.added_at && <span class="cvline__added">{t("cv.preview.addedByYou")}</span>}
      </span>
    </>
  );
}
