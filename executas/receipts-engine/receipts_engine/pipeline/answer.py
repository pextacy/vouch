"""The questions on the form — the last place the app was not looking.

Receipts checks the bullets it rewrites and the letter it writes. Then the
application form asks four more things in free text — *"Describe your
experience with Kubernetes." "Tell us about a time you owned an incident."
"Why do you want to work here?"* — a human reads every one of them, and until
now nothing in this product had anything to say about them. Every other tool
in the category fills that box with a confident paragraph whether or not the
candidate has the experience, which is the same harm `prd.md §2` names, moved
from the CV to the field underneath it.

So the answers are built the way every other sentence in this app is built:
from cited CV lines, through the verifier, dropped rather than softened when
they fail. What makes this screen different from the cover letter is what it
does when there is nothing to say, and there are two of those:

``no_evidence``
    The question asks about work the CV does not show. The app does not write
    around it — it hands the user the same question and takes their own
    sentence into the CV, which is the F9 loop and the only honest way to
    close a gap.

``not_about_you``
    The question asks what the candidate *wants*: why this company, what
    excites them, where they see themselves in five years. A CV records what
    someone did and contains no evidence of wanting anything, so there is
    nothing to retrieve and the app writes nothing at all. This is the case
    the feature exists for. It is also the one every competitor answers.

Two guards make those kinds mean something rather than being a label the model
picked:

* ``not_about_you`` is forced empty. If prose arrives through that door it is
  discarded, because the door is the promise.
* a claimed answer whose every sentence failed verification is **downgraded**
  to ``no_evidence``. An answer that grounded nothing is not a thin answer, it
  is an absent one, and reporting it as thin would be the app grading its own
  homework.

The question text is never a source. It arrives from an employer's form, which
makes it the one input here an attacker controls; letting it license a claim
would be the posting-vocabulary leak (`CLAUDE.md` rule 1) with a new front
door. When an application is open its *requirements* lend general concepts,
exactly as they do for a cover letter, and nothing else does.
"""

from __future__ import annotations

from typing import Final

from ..errors import EngineError
from ..host.frames import log
from ..llm import LlmClient
from ..schemas import (
    AnswerKind,
    AnswerOutput,
    AnswerResult,
    AnswerSentence,
    CVDoc,
    MatchResult,
    QuestionAnswer,
)
from ..text import clean
from ..verify import DEFAULT_LEXICON, verify
from .prompts import language_name, render

#: Application forms ask three or four. Past five this is a questionnaire, and
#: one model call would be answering each of them worse.
MAX_QUESTIONS: Final[int] = 5

#: A form answer is read in under a minute.
MAX_SENTENCES: Final[int] = 4

MAX_QUESTION_CHARS: Final[int] = 300


async def answer_questions(
    llm: LlmClient,
    *,
    cv: CVDoc,
    questions: list[str],
    match: MatchResult | None = None,
    locale: str = "en",
) -> AnswerResult:
    """Answer what the form asked, from the CV and nowhere else."""
    if not cv.lines:
        raise EngineError("cv_too_short", "there is no CV to answer these questions from")

    asked = _clean_questions(questions)
    if not asked:
        raise EngineError("invalid_args", "answer_question needs at least one question")

    output_locale = locale if locale in {"en", "tr"} else "en"
    line_text = cv.text_by_id()
    posting_vocab = [req.text for req in match.requirements] if match else []

    output = await _generate(
        llm, cv=cv, questions=asked, posting_vocab=posting_vocab, locale=output_locale
    )
    drafts = _by_index(output, len(asked))

    items: list[QuestionAnswer] = []
    failures: list[str] = []
    for index, question in enumerate(asked):
        item = _settle(drafts.get(index), question, line_text, posting_vocab)
        items.append(item)
        if item.dropped:
            failures.extend(_unsupported_tokens(drafts.get(index), line_text, posting_vocab))

    if failures:
        items = await _repair(
            llm,
            cv=cv,
            questions=asked,
            items=items,
            tokens=sorted(set(failures)),
            line_text=line_text,
            posting_vocab=posting_vocab,
            locale=output_locale,
        )

    return AnswerResult(match_id=match.id if match else None, items=items)


# ─── The questions ────────────────────────────────────────────────────


def _clean_questions(questions: list[str]) -> list[str]:
    """Tidy what the user pasted, without changing a word of it."""
    out: list[str] = []
    for raw in questions:
        question = clean(raw).replace("\n", " ").strip()
        if question and question not in out:
            out.append(question[:MAX_QUESTION_CHARS])
        if len(out) == MAX_QUESTIONS:
            break
    return out


# ─── Settling one question ────────────────────────────────────────────


def _settle(
    draft: _Draft | None,
    question: str,
    line_text: dict[str, str],
    posting_vocab: list[str],
) -> QuestionAnswer:
    """One question's verdict, after the verifier has had its say."""
    if draft is None:
        # The model skipped it. Not an error and not an empty answer dressed
        # up as one: the user still gets the question back, with the loop that
        # turns their own sentence into evidence.
        return QuestionAnswer(question=question, kind="no_evidence")

    if draft.kind == "not_about_you":
        # The door is the promise. Prose arriving through it is discarded
        # without being verified, because verifying it would imply it could
        # have been kept.
        return QuestionAnswer(question=question, kind="not_about_you")

    kept: list[AnswerSentence] = []
    dropped = 0
    for sentence in draft.sentences[: MAX_SENTENCES * 2]:
        text = sentence.text.strip()
        if not text:
            continue
        cited = [lid for lid in sentence.line_ids if lid in line_text]
        if not cited:
            # An uncited sentence is not checkable against anything narrower
            # than the whole CV, and "somewhere in this document" is not a
            # citation a reader can follow.
            dropped += 1
            continue
        verdict = verify(
            text,
            [line_text[lid] for lid in cited],
            lexicon=DEFAULT_LEXICON,
            posting_vocab=posting_vocab,
        )
        if verdict.ok:
            kept.append(AnswerSentence(text=text[:400], line_ids=cited[:4]))
        else:
            dropped += 1
        if len(kept) == MAX_SENTENCES:
            break

    if not kept:
        # Downgraded, not reported as a thin answer: an answer that grounded
        # nothing is an absent one, and the user needs the gap loop rather
        # than a note about sentences they never saw.
        return QuestionAnswer(question=question, kind="no_evidence", dropped=dropped)

    return QuestionAnswer(question=question, kind="answered", sentences=kept, dropped=dropped)


def _unsupported_tokens(
    draft: _Draft | None, line_text: dict[str, str], posting_vocab: list[str]
) -> list[str]:
    """The words that failed, for the repair instruction."""
    if draft is None:
        return []
    tokens: list[str] = []
    for sentence in draft.sentences:
        cited = [lid for lid in sentence.line_ids if lid in line_text]
        if not cited:
            continue
        verdict = verify(
            sentence.text,
            [line_text[lid] for lid in cited],
            lexicon=DEFAULT_LEXICON,
            posting_vocab=posting_vocab,
        )
        tokens.extend(verdict.tokens)
    return tokens


# ─── The model ────────────────────────────────────────────────────────


class _Draft:
    """What the model proposed for one question, before any of it is trusted."""

    __slots__ = ("kind", "sentences")

    def __init__(self, *, kind: AnswerKind, sentences: list[AnswerSentence]) -> None:
        self.kind = kind
        self.sentences = sentences


def _by_index(output: AnswerOutput, count: int) -> dict[int, _Draft]:
    """Rejoin the two flat lists into one draft per question."""
    kinds: dict[int, AnswerKind] = {}
    for verdict in output.verdicts:
        if 0 <= verdict.index < count and verdict.index not in kinds:
            kinds[verdict.index] = verdict.kind

    sentences: dict[int, list[AnswerSentence]] = {}
    for item in output.sentences:
        if not 0 <= item.index < count:
            continue
        text = item.text.strip()
        if text:
            sentences.setdefault(item.index, []).append(
                AnswerSentence(text=text[:400], line_ids=_ids(item.line_ids))
            )

    # A sentence with no verdict beside it is treated as a claimed answer: the
    # model wrote something, so the verifier gets to decide, rather than the
    # missing label deciding for it.
    return {
        index: _Draft(kind=kinds.get(index, "answered"), sentences=sentences.get(index, []))
        for index in kinds.keys() | sentences.keys()
    }


def _ids(raw: list[str]) -> list[str]:
    """Keep only things shaped like line ids; the caller checks they exist."""
    return [value for value in raw if value.startswith("L") and value[1:].isdigit()][:8]


async def _generate(
    llm: LlmClient,
    *,
    cv: CVDoc,
    questions: list[str],
    posting_vocab: list[str],
    locale: str,
    extra_instruction: str = "",
) -> AnswerOutput:
    system = render("answer.v1.md", output_language=language_name(locale))
    listing = "\n".join(f"[{index}] {text}" for index, text in enumerate(questions))
    context = (
        "WHAT THIS POSTING ASKS FOR\n"
        "--------------------------\n" + "\n".join(f"- {text}" for text in posting_vocab[:20])
        if posting_vocab
        else ""
    )
    user = (
        "QUESTIONS ON THE FORM\n"
        "---------------------\n"
        f"{listing}\n\n"
        f"{context}\n\n"
        "THE CANDIDATE'S CV LINES\n"
        "------------------------\n"
        f"{cv.numbered()}"
    )
    if extra_instruction:
        user = f"{extra_instruction}\n\n{user}"

    return await llm.structured(
        name="receipts_answers",
        model=AnswerOutput,
        system_prompt=system,
        user_prompt=user,
        max_tokens=1536,
    )


async def _repair(
    llm: LlmClient,
    *,
    cv: CVDoc,
    questions: list[str],
    items: list[QuestionAnswer],
    tokens: list[str],
    line_text: dict[str, str],
    posting_vocab: list[str],
    locale: str,
) -> list[QuestionAnswer]:
    """One more attempt, then the drop stands.

    A repaired answer replaces the first one only where the first one came back
    empty-handed. Somewhere between the two drafts is a temptation to keep
    whichever is longer; a sentence that survived the verifier the first time
    is not improved by a second draft written under a correction notice.
    """
    log(f"answers: repairing {len(tokens)} unsupported claim(s)")
    instruction = (
        "Your previous draft used facts the cited CV lines do not support: "
        f"{', '.join(tokens)}. Answer again without them. If a question cannot "
        "be answered from the lines at all, return no sentences for it and say "
        "so with the kind — that is a real answer, not a failure."
    )
    try:
        output = await _generate(
            llm,
            cv=cv,
            questions=questions,
            posting_vocab=posting_vocab,
            locale=locale,
            extra_instruction=instruction,
        )
    except Exception as exc:  # noqa: BLE001 — keep whatever already verified
        log(f"answers: repair call failed ({type(exc).__name__}) — keeping what passed")
        return items

    drafts = _by_index(output, len(questions))
    rebuilt: list[QuestionAnswer] = []
    for index, item in enumerate(items):
        if item.kind == "answered" or item.kind == "not_about_you":
            rebuilt.append(item)
            continue
        second = _settle(drafts.get(index), item.question, line_text, posting_vocab)
        # The repair only ever adds: a second empty answer leaves the first
        # one's `dropped` count intact, because that count is what tells the
        # user their answer lost sentences.
        if second.kind == "answered":
            rebuilt.append(second.model_copy(update={"dropped": item.dropped + second.dropped}))
        else:
            rebuilt.append(item)
    return rebuilt
