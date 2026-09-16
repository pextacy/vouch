/**
 * The `L23` chip — a citation you can click.
 *
 * Tabular numerals keep a column of chips from jittering, and clicking one
 * scrolls the CV sheet to the line, which is the whole point of numbering the
 * lines in the first place.
 */

import { t } from "../i18n";
import type { LineId } from "../lib/types";
import "./SourceChip.css";

interface SourceChipProps {
  line: LineId;
  onSelect?: (line: LineId) => void;
}

export function SourceChip({ line, onSelect }: SourceChipProps) {
  if (!onSelect) {
    return <span class="chip numeric">{line}</span>;
  }
  return (
    <button
      type="button"
      class="chip chip--button numeric"
      onClick={() => onSelect(line)}
      aria-label={t("map.evidenceIn", { lines: line })}
    >
      {line}
    </button>
  );
}
