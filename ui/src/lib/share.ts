/**
 * A receipt you can actually show.
 *
 * `plan.md §9` names the growth engine in one line — *anonymised match-map
 * visuals*, under the hook "Show your receipts" — and the app had no way to
 * make one. The only picture of a match a person could produce was a
 * screenshot of their own screen, which carries their employers, their job
 * titles and the sentences of their CV. That is the one image a job seeker
 * cannot post, so the mechanic the plan is built on had no product behind it.
 *
 * The card is that picture, and the interesting part is what it is made of.
 *
 * **The invariant.** :func:`cardFor` reduces a match to counts and enums —
 * numbers, `must`/`nice`, `strong`/`partial`/`missing` — and one optional
 * string the user has to switch on themselves. :func:`renderCard` can only
 * draw what it is handed. So the card cannot leak a CV line, an employer or a
 * requirement's wording *because those never reach the renderer*, not because
 * the renderer is careful with them. `tests/ui/share.spec.ts` is the proof:
 * it builds a card from a match stuffed with distinctive words and asserts
 * none of them appear in the output.
 *
 * **Why the colours are literals here and nowhere else.** Every other surface
 * in this app reads `--paper`, `--ink`, `--marker` from the token file
 * (`CLAUDE.md`, frontend rules). A card is the one artefact that *leaves* —
 * it is opened in a viewer that has never seen our stylesheet, so a custom
 * property would resolve to nothing and the card would render as black text on
 * white. The values below are `docs.md §8.2`, light theme, copied once and
 * named, because a shared image has no theme to follow.
 *
 * **No inline styles.** The bundle's CSP is `style-src 'self'`, so the SVG is
 * built from presentation attributes only — no `<style>` element, no `style=`
 * — which also means the same string can be dropped into the page and written
 * to a file. The font is named rather than embedded: a 46 KB woff2 would
 * double the file for a fallback nobody but a designer would notice.
 */

import type { Kind, Locale, MatchResult, Status } from "./types";

/** `docs.md §8.2`, light theme. The one place literals are allowed. */
const PAPER = "#F5F7FA";
const INK = "#1C2A44";
const GRAPHITE = "#5A6478";
const RULE = "#D8DEE8";
const MARKER = "#F4EA3A";

/** The social-card shape every platform crops to predictably. */
export const CARD_WIDTH = 1200;
export const CARD_HEIGHT = 630;

const MARGIN = 72;

/** Room for "Nice to have" beside the marks, so both rows line up. */
const LABEL_COLUMN = 210;

/** Roughly what fits on a line at the headline size, in Schibsted Grotesk. */
const HEADLINE_CHARS = 46;

/** Two, and the layout below is built on it: the sentence is bounded — two
 *  counts and a fixed phrase — so a third line would mean a broken string,
 *  not a long career. */
const HEADLINE_LINES = 2;

/** Past this the strip is a texture rather than a count, so it stops. */
const MAX_MARKS = 28;

/**
 * Everything the card is allowed to know.
 *
 * Counts and enums, plus `role` — which is the user's own decision and the
 * only free text that can reach the renderer. Nothing here can carry a CV
 * line, an employer or the wording of a requirement.
 */
export interface ShareCard {
  total: number;
  evidenced: number;
  related: number;
  missing: number;
  mustMissing: number;
  /** One entry per requirement, in the posting's order. Enums only. */
  marks: { kind: Kind; status: Status }[];
  /** Off unless the user turns it on. */
  role: string | null;
  locale: Locale;
}

/**
 * Reduce a match to the little the card may see.
 *
 * `withRole` is the whole consent model: the posting's title is the only
 * thing on this card that could say which job someone is applying for, and it
 * is off until they ask for it.
 */
export function cardFor(
  match: MatchResult,
  options: { withRole: boolean; locale: Locale },
): ShareCard {
  const statusOf = new Map(match.evidence.map((item) => [item.requirement_id, item.status]));
  const marks = match.requirements.slice(0, MAX_MARKS).map((requirement) => ({
    kind: requirement.kind,
    status: statusOf.get(requirement.id) ?? ("missing" as Status),
  }));

  return {
    total: match.summary.total,
    evidenced: match.summary.strong,
    related: match.summary.partial,
    missing: match.summary.missing,
    mustMissing: match.summary.must_missing,
    marks,
    role: options.withRole ? (match.posting.title?.slice(0, 60) ?? null) : null,
    locale: options.locale,
  };
}

/**
 * Draw the card.
 *
 * `strings` is passed in rather than read from the i18n module so the renderer
 * stays pure: the same card and the same strings always produce the same
 * bytes, which is what makes the leak test meaningful.
 */
export function renderCard(
  card: ShareCard,
  strings: {
    headline: string;
    must: string;
    nice: string;
    evidenced: string;
    related: string;
    missing: string;
    tagline: string;
  },
): string {
  const lines = wrap(strings.headline, HEADLINE_CHARS).slice(0, HEADLINE_LINES);
  const parts: string[] = [];

  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${CARD_WIDTH}" height="${CARD_HEIGHT}" ` +
      `viewBox="0 0 ${CARD_WIDTH} ${CARD_HEIGHT}" font-family="Schibsted Grotesk, Helvetica Neue, Arial, sans-serif">`,
  );
  parts.push(`<rect width="${CARD_WIDTH}" height="${CARD_HEIGHT}" fill="${PAPER}"/>`);

  // The wordmark: the highlighter square, then the name. The same pairing the
  // app header uses, and the only place yellow appears besides the marks.
  parts.push(`<rect x="${MARGIN}" y="66" width="34" height="22" rx="2" fill="${MARKER}"/>`);
  parts.push(
    text("Vouch", { x: MARGIN + 48, y: 86, size: 27, weight: 700, fill: INK }),
  );
  if (card.role) {
    parts.push(text(card.role, { x: MARGIN, y: 142, size: 21, fill: GRAPHITE }));
  }

  // The vertical budget is fixed and tight: the legend, the rule and the
  // tagline are pinned to the bottom, so the headline starts higher when the
  // role line pushes everything down.
  let y = card.role ? 214 : 190;
  for (const line of lines) {
    parts.push(text(line, { x: MARGIN, y, size: 44, weight: 500, fill: INK }));
    y += 56;
  }

  // Two labelled rows rather than one strip with a tick under the must-haves.
  // An unexplained glyph is worse than no glyph: `docs.md §8.3` says a status
  // is carried by shape *and* words, and "must have" is a status too.
  const musts = card.marks.filter((mark) => mark.kind === "must");
  const nices = card.marks.filter((mark) => mark.kind === "nice");
  let rowY = y + 30;
  if (musts.length > 0) {
    parts.push(marksRow(musts, strings.must, rowY));
    rowY += 70;
  }
  if (nices.length > 0) {
    parts.push(marksRow(nices, strings.nice, rowY));
  }

  // The legend, stacked rather than run together with separators: `docs.md
  // §8` rules out the "A · B · C" meta string, and each shape needs room to
  // be read as a shape.
  const legendY = CARD_HEIGHT - 130;
  parts.push(legendItem("strong", strings.evidenced, MARGIN, legendY));
  parts.push(legendItem("partial", strings.related, MARGIN + 340, legendY));
  parts.push(legendItem("missing", strings.missing, MARGIN + 660, legendY));

  parts.push(
    `<line x1="${MARGIN}" y1="${CARD_HEIGHT - 104}" x2="${CARD_WIDTH - MARGIN}" ` +
      `y2="${CARD_HEIGHT - 104}" stroke="${RULE}" stroke-width="1"/>`,
  );
  parts.push(
    text(strings.tagline, { x: MARGIN, y: CARD_HEIGHT - 58, size: 21, fill: GRAPHITE }),
  );

  parts.push("</svg>");
  return parts.join("");
}

/** The label, then one shape per requirement in the posting's order. */
function marksRow(marks: { kind: Kind; status: Status }[], label: string, y: number): string {
  const parts: string[] = [text(label, { x: MARGIN, y: y + 24, size: 19, fill: GRAPHITE })];

  const left = MARGIN + LABEL_COLUMN;
  const room = CARD_WIDTH - MARGIN - left;
  const gap = 12;
  const width = Math.max(
    14,
    Math.min(44, Math.floor((room - gap * (marks.length - 1)) / Math.max(marks.length, 1))),
  );

  marks.forEach((mark, index) => {
    const x = left + index * (width + gap);
    // Shape carries the meaning, the way it does on the map: a full mark, an
    // underline, an open bracket. The card survives being greyscaled, and so
    // does a reader who cannot tell the yellow from the grey.
    if (mark.status === "strong") {
      parts.push(`<rect x="${x}" y="${y}" width="${width}" height="34" rx="2" fill="${MARKER}"/>`);
    } else if (mark.status === "partial") {
      parts.push(
        `<rect x="${x}" y="${y + 28}" width="${width}" height="6" rx="1" fill="${MARKER}"/>`,
      );
    } else {
      parts.push(
        `<rect x="${x + 0.5}" y="${y + 0.5}" width="${width - 1}" height="33" rx="2" ` +
          `fill="none" stroke="${RULE}" stroke-width="1"/>`,
      );
    }
  });

  return parts.join("");
}


function legendItem(status: Status, label: string, x: number, y: number): string {
  const swatch =
    status === "strong"
      ? `<rect x="${x}" y="${y - 18}" width="26" height="24" rx="2" fill="${MARKER}"/>`
      : status === "partial"
        ? `<rect x="${x}" y="${y + 1}" width="26" height="6" rx="1" fill="${MARKER}"/>`
        : `<rect x="${x + 0.5}" y="${y - 17.5}" width="25" height="23" rx="2" fill="none" ` +
          `stroke="${RULE}" stroke-width="1"/>`;
  return swatch + text(label, { x: x + 40, y, size: 21, fill: GRAPHITE });
}

interface TextOptions {
  x: number;
  y: number;
  size: number;
  fill: string;
  weight?: number;
}

function text(value: string, options: TextOptions): string {
  const weight = options.weight ? ` font-weight="${options.weight}"` : "";
  return (
    `<text x="${options.x}" y="${options.y}" font-size="${options.size}"${weight} ` +
    `fill="${options.fill}">${escapeXml(value)}</text>`
  );
}

/**
 * Greedy wrap by character count.
 *
 * SVG has no text flow, and measuring a glyph needs a canvas the renderer
 * deliberately does not have — a pure function is what lets the leak test
 * compare bytes. A long word is left long rather than broken: a hyphen the
 * user did not write is a change to their own words.
 */
export function wrap(value: string, maxChars: number): string[] {
  const lines: string[] = [];
  let current = "";
  for (const word of value.split(/\s+/).filter(Boolean)) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines;
}

/** Everything that reaches the renderer is escaped; `role` comes from a posting. */
function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
