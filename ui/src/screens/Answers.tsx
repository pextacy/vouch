/**
 * The questions on the form — answered, or honestly not.
 *
 * The CV is checked, the bullets are checked, the letter is checked. Then the
 * application form asks four more things in free text, a human reads every one
 * of them, and until now this app had nothing to say about that box. Every
 * other tool fills it with a confident paragraph whether or not the experience
 * exists, which is the harm this product was built against, one field lower
 * down the page.
 *
 * So each answer here is sentences the verifier passed, with the CV line under
 * every one. What the screen is actually *for*, though, is the two ways it
 * declines:
 *
 * * **no evidence** — the CV cannot answer it, so nothing is written around
 *   it. The user gets the question back and their own sentence becomes a CV
 *   line, which is the same loop the gap questions use, and the re-run then
 *   answers from a line that exists.
 * * **not about you** — the question asks what the person *wants*. A CV holds
 *   no evidence of wanting anything, so the app writes nothing and says so.
 *   This is the paragraph every competitor ships and this one will not.
 *
 * Copy sits beside each answer rather than at the end, because the destination
 * is four separate boxes in a browser tab, not a document.
 */

import { useState } from "preact/hooks";

import { DocumentSheet } from "../components/DocumentSheet";
import { ErrorNotice } from "../components/ErrorNotice";
import { Screen } from "../components/Screen";
import { SourceChip } from "../components/SourceChip";
import { t } from "../i18n";
import { MAX_QUESTIONS } from "../lib/questions";
import { navigate } from "../router";
import {
  activeCv,
  answerUnanswered,
  answeredQuestions,
  answersPhase,
  answersResult,
  clearAnswers,
  currentMatch,
  detectedQuestions,
  dismissError,
  error,
  questionDraft,
  runAnswers,
  showingExample,
  skipQuestion,
} from "../state";
import type { QuestionAnswer } from "../lib/types";
import "./Answers.css";

export function Answers() {
  const doc = activeCv();
  const result = answersResult.value;
  const phase = answersPhase.value;
  const questions = detectedQuestions.value;

  if (!doc) {
    navigate("/cv/add");
    return null;
  }

  return (
    <Screen heading={t("answers.heading")} lede={t("answers.body")}>
      {error.value && (
        <ErrorNotice error={error.value} onRetry={() => void runAnswers()} onDismiss={dismissError} />
      )}

      {!result && (
        <div class="stack answers__form">
          <label class="answers__label" for="answers-input">
            {t("answers.pasteLabel")}
          </label>
          <textarea
            id="answers-input"
            class="textarea answers__input"
            rows={8}
            value={questionDraft.value}
            placeholder={t("answers.pastePlaceholder")}
            onInput={(event) => {
              questionDraft.value = (event.target as HTMLTextAreaElement).value;
            }}
          />

          {/* What the paste was read as, before anything is spent on it. A
              wrong split is the difference between answering the question and
              answering half of two, so it is shown and it is editable. */}
          {questions.length > 0 && (
            <div class="stack stack--tight answers__read">
              <p class="small muted">
                {questions.length === 1
                  ? t("answers.readOne")
                  : t("answers.readMany", { count: questions.length })}
              </p>
              <ul class="list answers__questions">
                {questions.map((question) => (
                  <li key={question} class="answers__question">
                    <span class="answers__questionText">{question}</span>
                    <button
                      type="button"
                      class="button button--quiet answers__drop"
                      onClick={() => skipQuestion(question)}
                    >
                      {t("answers.drop")}
                    </button>
                  </li>
                ))}
              </ul>
              {questions.length === MAX_QUESTIONS && (
                <p class="small muted">{t("answers.capped", { count: MAX_QUESTIONS })}</p>
              )}
            </div>
          )}

          <div class="row">
            <button
              type="button"
              class="button answers__run"
              disabled={questions.length === 0 || phase === "running"}
              onClick={() => void runAnswers()}
            >
              {phase === "running" ? t("answers.running") : t("answers.run")}
            </button>
            <button
              type="button"
              class="button button--secondary"
              onClick={() => navigate(currentMatch.value ? `/match/${currentMatch.value.id}` : "/matches")}
            >
              {t("nav.back")}
            </button>
          </div>
          <p class="small muted answers__note">{t("answers.note")}</p>
        </div>
      )}

      {result && (
        <>
          <ul class="list">
            {result.items.map((item) => (
              <AnsweredQuestion
                key={item.question}
                item={item}
                answered={answeredQuestions.value.has(item.question)}
                readOnly={showingExample.value}
              />
            ))}
          </ul>

          <div class="row">
            <button type="button" class="button button--secondary" onClick={clearAnswers}>
              {t("answers.another")}
            </button>
            <button
              type="button"
              class="button button--quiet"
              onClick={() => navigate(currentMatch.value ? `/match/${currentMatch.value.id}` : "/matches")}
            >
              {t("nav.back")}
            </button>
          </div>
        </>
      )}
    </Screen>
  );
}

interface AnsweredQuestionProps {
  item: QuestionAnswer;
  answered: boolean;
  readOnly: boolean;
}

function AnsweredQuestion({ item, answered, readOnly }: AnsweredQuestionProps) {
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const inputId = `answer-${item.question.replace(/\W+/g, "-").slice(0, 40)}`;
  const text = item.sentences.map((sentence) => sentence.text).join(" ");

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // The answer is on screen and selectable either way.
    }
  }

  async function save(): Promise<void> {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      await answerUnanswered(item, draft);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li class="qa">
      <h2 class="qa__question">{item.question}</h2>

      {item.kind === "answered" && (
        <>
          <DocumentSheet>
            <div class="stack stack--tight">
              {item.sentences.map((sentence) => (
                <p key={sentence.text} class="qa__sentence">
                  {sentence.text}{" "}
                  {sentence.line_ids.map((line) => (
                    <SourceChip key={line} line={line} />
                  ))}
                </p>
              ))}
            </div>
          </DocumentSheet>
          {item.dropped > 0 && (
            <p class="small muted qa__dropped">
              {item.dropped === 1
                ? t("answers.droppedOne")
                : t("answers.droppedMany", { count: item.dropped })}
            </p>
          )}
          <div class="row">
            <button type="button" class="button button--secondary" onClick={() => void copy()}>
              {copied ? t("answers.copied") : t("answers.copy")}
            </button>
          </div>
        </>
      )}

      {/* The whole argument of the screen. Nothing is generated, nothing is
          suggested, and the reason is said out loud — a CV records what
          someone did, not what they want. */}
      {item.kind === "not_about_you" && (
        <p class="qa__refused">{t("answers.notAboutYou")}</p>
      )}

      {item.kind === "no_evidence" &&
        (answered ? (
          <p class="qa__saved">{t("answers.saved")}</p>
        ) : (
          <div class="stack stack--tight qa__answer">
            <p class="qa__noEvidence">{t("answers.noEvidence")}</p>
            <label class="answers__label" for={inputId}>
              {t("answers.answerLabel")}
            </label>
            <textarea
              id={inputId}
              class="textarea qa__input"
              rows={3}
              value={draft}
              disabled={readOnly}
              placeholder={t("answers.answerPlaceholder")}
              onInput={(event) => setDraft((event.target as HTMLTextAreaElement).value)}
            />
            <p class="small muted">{t("answers.answerNote")}</p>
            <div class="row">
              <button
                type="button"
                class="button"
                disabled={readOnly || saving || !draft.trim()}
                onClick={() => void save()}
              >
                {saving ? t("answers.adding") : t("answers.add")}
              </button>
            </div>
          </div>
        ))}
    </li>
  );
}
