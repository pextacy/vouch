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
  if (animate && status !== "missing") classes.push("mark--sweep");
  return (
    <span
      class={classes.join(" ")}
      style={animate ? { "--sweep-index": String(Math.min(sweepIndex, 12)) } : undefined}
    >
      {children}
    </span>
  );
}
