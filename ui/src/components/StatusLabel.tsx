/**
 * Status expressed three ways at once: colour, shape and words.
 *
 * A reviewer looking at a greyscale screenshot, and a user who cannot
 * distinguish the yellow, both still read the status — which is the reason
 * there is no coloured badge anywhere in this app.
 */

import { BracketIcon, MarkerIcon, UnderlineIcon } from "./Icons";
import { t } from "../i18n";
import type { Status } from "../lib/types";

const GLYPHS = {
  strong: MarkerIcon,
  partial: UnderlineIcon,
  missing: BracketIcon,
} as const;

export function StatusLabel({ status }: { status: Status }) {
  const Glyph = GLYPHS[status];
  const label = t(`status.${status}`);
  return (
    <span class={`status status--${status}`}>
      <Glyph size={16} />
      {label}
    </span>
  );
}
