/**
 * Changing the CV document without breaking what cites it.
 *
 * Two kinds of change reach the stored CV: the user fixes a misread line, and
 * the user answers a gap question so their own sentence becomes a new line.
 * Both move the hash, and the hash is the only thing tying a saved match to
 * the CV it was made against — leaving it alone would let a match go on citing
 * a line whose text has since changed.
 *
 * Pure functions, no signals and no storage, so the rules can be tested
 * without a host (`tests/ui/cv.spec.ts`).
 */

import type { Category, CVDoc, CvLine, LineId, Section } from "./types";

/**
 * Mark a hash as edited.
 *
 * The engine's hash covers the parsed text and cannot be recomputed here
 * without re-parsing, which would renumber the lines every citation points at.
 * A counted suffix keeps the one property that matters: two different CV
 * contents never share a hash.
 */
export function markEdited(hash: string): string {
  const counted = /^(.*)~e(\d+)$/.exec(hash);
  if (!counted?.[1]) return `${hash}~e1`;
  return `${counted[1]}~e${Number(counted[2]) + 1}`;
}

/** Replace one line's text, keeping its id and section. */
export function editLine(doc: CVDoc, id: LineId, text: string): CVDoc {
  const lines = doc.lines.map((line) => (line.id === id ? { ...line, text } : line));
  return { ...doc, lines, hash: markEdited(doc.hash) };
}

/**
 * The next free line id.
 *
 * Counted from the highest id in use rather than from the line count: a CV
 * whose lines were renumbered by an earlier edit must never mint an id that
 * already points at something, because every citation in every saved match is
 * one of these strings.
 */
export function nextLineId(doc: CVDoc): LineId {
  const highest = doc.lines.reduce((top, line) => {
    const number = Number(line.id.slice(1));
    return Number.isFinite(number) && number > top ? number : top;
  }, 0);
  return `L${highest + 1}`;
}

/**
 * Append a line the user wrote themselves.
 *
 * `added_at` is what separates it from the parsed document, and the CV sheet
 * says so: a line that becomes evidence should carry where it came from. The
 * text is stored exactly as typed — nothing here rewrites, tightens or
 * "improves" it, because the moment this app edits the user's own account of
 * their work is the moment it starts inventing.
 */
export function appendLine(
  doc: CVDoc,
  text: string,
  section: Section,
  now: Date = new Date(),
): CVDoc {
  const line: CvLine = {
    id: nextLineId(doc),
    text: text.trim(),
    section,
    added_at: now.toISOString(),
  };
  return { ...doc, lines: [...doc.lines, line], hash: markEdited(doc.hash) };
}

/**
 * Where an answer belongs in the document.
 *
 * A gap question is about a requirement, and the requirement's category is the
 * closest thing to a section the app has. Getting this roughly right matters
 * because the section is what the next parse-free render groups by; getting it
 * exactly right does not, because the user can see the line and fix it.
 */
export function sectionForCategory(category: Category): Section {
  switch (category) {
    case "education":
      return "education";
    case "skill":
      return "skills";
    case "experience":
    case "domain":
    case "soft":
      return "experience";
    case "logistics":
      return "other";
  }
}
