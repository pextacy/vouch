/**
 * Reading a pasted application form as a list of questions.
 *
 * People do not type questions one at a time. They select the four boxes on a
 * Greenhouse form, or the paragraph a recruiter emailed, and paste the lot —
 * so the screen has to make sense of a block and then *show what it made of
 * it*, because a wrong split is the difference between answering the question
 * and answering half of two.
 *
 * Deterministic on purpose: this runs before any model call, the user sees the
 * result and can drop a line before spending anything, and the same paste
 * always splits the same way. The rules are only these:
 *
 * * a line break ends a question — a form's boxes arrive one per line;
 * * inside a line, a question mark ends one, because a recruiter's paragraph
 *   is where several of them run together;
 * * a leading "1.", "2)" or a bullet is the form's own numbering, not part of
 *   what was asked, so it is dropped from the display;
 * * a line counts as asking something when it carries a question mark or runs
 *   long enough to be a prompt. That is what separates "Why us?" — seven
 *   characters and a real question — from the "Questions" heading sitting
 *   above it, which a length rule alone would keep and a punctuation rule
 *   alone would throw "Describe your Go experience." out with.
 *
 * What it deliberately does not do is split on full stops. "Tell us about a
 * time you owned an incident. Include what you changed." is one question with
 * two sentences, and treating it as two would answer neither.
 */

/** Matches the engine's `MAX_QUESTIONS`: past this it is a questionnaire. */
export const MAX_QUESTIONS = 5;

/** Long enough to be a prompt even without a question mark. */
const MIN_PROMPT_CHARS = 20;

/** The form's own numbering: "1.", "2)", "-", "•". */
const ENUMERATOR = /^\s*(?:\(?\d{1,2}[.)]|[-–—•*])\s+/;

/** A question mark ends a question, even mid-line. */
const AFTER_QUESTION_MARK = /(?<=\?)\s+/;

export function splitQuestions(text: string): string[] {
  const found: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    for (const piece of line.split(AFTER_QUESTION_MARK)) {
      const question = piece.replace(ENUMERATOR, "").trim();
      if (!question.includes("?") && question.length < MIN_PROMPT_CHARS) continue;
      if (found.includes(question)) continue;
      found.push(question.slice(0, 300));
      if (found.length === MAX_QUESTIONS) return found;
    }
  }
  return found;
}
