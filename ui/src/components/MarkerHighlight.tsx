/**
 * The highlighter mark.
 *
 * `sweepIndex` staggers the animation across a list so evidence appears to be
 * found one requirement after another, which is what is actually happening.
 * Passing `animate={false}` renders the finished mark — used when a saved
 * match is reopened, where nothing is being discovered.
 */

import type { ComponentChildren } from "preact";

import type { Status } from "../lib/types";

/** Stagger steps defined in `styles/marks.css`; later items share the last. */
const SWEEP_STEPS = 12;

interface MarkerHighlightProps {
  status: Status;
  children: ComponentChildren;
  animate?: boolean;
  sweepIndex?: number;
}

export function MarkerHighlight({
  status,
  children,
  animate = false,
  sweepIndex = 0,
}: MarkerHighlightProps) {
  const classes = ["mark", `mark--${status}`];
  if (animate && status !== "missing") {
    classes.push("mark--sweep");
    // The delay rides on a class: `style-src 'self'` drops a style attribute,
    // and a dropped stagger would sweep the whole list at once.
    const step = Math.min(Math.max(sweepIndex, 0), SWEEP_STEPS);
    if (step > 0) classes.push(`mark--sweep-${step}`);
  }
  return <span class={classes.join(" ")}>{children}</span>;
}
