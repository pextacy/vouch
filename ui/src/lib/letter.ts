/**
 * Filling in the names the app already knows.
 *
 * A letter paragraph is stored exactly as the verifier approved it, which
 * means it still says `[Company]` and `[Role]` — the engine deliberately does
 * not substitute them, so that what was checked is what was saved and the eval
 * harness can re-check a stored letter against the CV without needing to know
 * anything else (`pipeline/letter.py`).
 *
 * The screen is a point of use, so it is where the posting's own names go in.
 * `LetterResult.placeholders` lists only what is *left* for the user to
 * replace by hand, so a resolved name never shows up in that warning.
 */

import type { LetterParagraph, MatchResult } from "./types";

export interface KnownNames {
  company?: string | null;
  role?: string | null;
}

export function resolvePlaceholders(text: string, known: KnownNames): string {
  let out = text;
  if (known.company) out = out.replaceAll("[Company]", known.company);
  if (known.role) out = out.replaceAll("[Role]", known.role);
  return out;
}

export function namesFromMatch(match: MatchResult): KnownNames {
  return { company: match.posting.company, role: match.posting.title };
}

/**
 * The paragraphs as a reader should see them.
 *
 * Takes the paragraphs rather than the letter: the follow-up carries the same
 * verified-text-with-citations shape and makes the same promise about the
 * same placeholder tokens, and a second copy of this function would be a
 * second thing to keep true.
 */
export function resolvedParagraphs(
  result: { paragraphs: LetterParagraph[] },
  known: KnownNames,
): LetterParagraph[] {
  return result.paragraphs.map((paragraph) => {
    const text = resolvePlaceholders(paragraph.text, known);
    return text === paragraph.text ? paragraph : { ...paragraph, text };
  });
}
