/**
 * The one sentence a user screenshots.
 *
 * Composed from the counts in the UI language rather than read from the
 * stored string, so an old match still reads correctly after the interface
 * language changes.
 */

import { summarySentence } from "../i18n";
import type { MatchSummary } from "../lib/types";
import "./SummarySentence.css";

export function SummarySentence({ summary }: { summary: MatchSummary }) {
  const evidenced = summary.strong + summary.partial;
  return (
    <p class="summary">{summarySentence(summary.total, evidenced, summary.must_missing)}</p>
  );
}
