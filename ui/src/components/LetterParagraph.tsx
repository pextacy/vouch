/**
 * A paragraph of the letter with its citations.
 *
 * Citations are on by default. Hiding them is a reading convenience the user
 * chooses; showing them is the product.
 */

import { SourceChip } from "./SourceChip";
import type { LetterParagraph as LetterParagraphModel } from "../lib/types";
import "./LetterParagraph.css";

interface LetterParagraphProps {
  paragraph: LetterParagraphModel;
  showCitations: boolean;
}

export function LetterParagraph({ paragraph, showCitations }: LetterParagraphProps) {
  return (
    <div class="letterpara">
      <p class="letterpara__text">{paragraph.text}</p>
      {showCitations && paragraph.line_ids.length > 0 && (
        <div class="row letterpara__chips">
          {paragraph.line_ids.map((line) => (
            <SourceChip key={line} line={line} />
          ))}
        </div>
      )}
    </div>
  );
}
