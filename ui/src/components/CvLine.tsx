/**
 * One numbered CV line.
 *
 * The id is the citable handle the model returns and the user clicks, so it
 * is always visible — not a tooltip, not a hover state.
 */

import { MarkerHighlight } from "./MarkerHighlight";
import type { CvLine as CvLineModel, Status } from "../lib/types";
import "./CvLine.css";

interface CvLineProps {
  line: CvLineModel;
  status?: Status;
  highlighted?: boolean;
  animate?: boolean;
  sweepIndex?: number;
}

export function CvLine({ line, status, highlighted, animate, sweepIndex }: CvLineProps) {
  return (
    <p
      class={`cvline${highlighted ? " cvline--current" : ""}`}
      id={`cv-${line.id}`}
      data-line={line.id}
    >
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
      </span>
    </p>
  );
}
