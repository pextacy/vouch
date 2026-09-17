#!/usr/bin/env python3
"""A scripted sampler for `eval_match.py` that fabricates on purpose.

    python scripts/eval_match.py fixtures/golden \
        --sampling-cmd python scripts/fabricating_sampler.py

`eval_match.py` needs something to answer `sampling/createMessage`. A real
model answers it honestly most of the time, which makes it a poor test of the
part of the pipeline that exists for the dishonest minority. This stub is the
adversary instead: every other tailored bullet and one letter paragraph per run
carry a number, a tool and an employer that appear nowhere in the source lines,
and the run is scored a failure unless **all** of them are caught.

What the numbers from such a run do and do not mean:

* **tailor leakage and letter leakage are real.** They measure the verifier and
  the drop path, which are deterministic Python — the same code that runs in
  production, fed worse input than a model would produce.
* **F1 and the false-strong rate are not.** They measure the crude keyword
  matching below, not a model. Report them from a `--sampling-cmd` run against
  a real host, never from this one.

The honest half matters as much as the fabricated half: a verifier that drops
everything would also show zero leakage. So every run also emits suggestions
and paragraphs built only from words in the source lines, and the summary
counts how many of those survived. If that count is zero, the run is telling
you the verifier has become a shredder.

Reads one `sampling/createMessage` params object on stdin, writes one
completion on stdout. No randomness: the same input always produces the same
output, so a diff in the eval table means a diff in the pipeline.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Final

# Fabrications. Each is a claim a recruiter would hold a candidate to, and none
# of them can come from a CV line, because no CV in the golden set contains
# them: a fresh proper noun, a percentage, a spelled-out number, a tool.
INVENTED_COMPANY: Final[str] = "Globex"
INVENTED_TOOL: Final[str] = "Kubernetes"
INVENTED_PERCENT: Final[str] = "47%"
INVENTED_WORDS: Final[str] = "forty percent"
INVENTED_TEAM: Final[str] = "a team of 30"

_LINE_RE: Final[re.Pattern[str]] = re.compile(r"^(L\d+):\s*(.+)$", re.MULTILINE)
_REQ_RE: Final[re.Pattern[str]] = re.compile(r"^(R\d+)\s*\[(must|nice)\]\s*(.+?)(?:\s+←.*)?$", re.MULTILINE)
_BULLET_RE: Final[re.Pattern[str]] = re.compile(r"^\s*[-•*·]\s*(.+?)\s*$", re.MULTILINE)

#: Headings that open the "nice to have" half of a posting, and the ones that
#: open a section whose bullets are not requirements at all.
_NICE_HEADINGS: Final[tuple[str, ...]] = (
    "nice to have", "nice-to-have", "preferred", "bonus", "plus",
    "tercihen", "artı", "arti olarak",
)
_SKIP_HEADINGS: Final[tuple[str, ...]] = (
    "benefit", "we offer", "perks", "about us", "what we offer", "eeo",
    "yan hak", "sunduklarımız", "hakkımızda",
)

_CATEGORY_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "education": ("degree", "bsc", "msc", "university", "lisans", "üniversite", "bölüm"),
    "experience": ("years", "year", "yıl", "experience", "deneyim", "leading", "led", "team"),
    "logistics": ("remote", "onsite", "hybrid", "visa", "relocat", "travel", "shift", "uzaktan"),
    "soft": ("communicat", "stakeholder", "collaborat", "mentor", "iletişim", "ekip çalışması"),
    "domain": ("fintech", "payments", "healthcare", "e-commerce", "banking", "ödeme", "sağlık"),
}

#: Words that carry no signal about *which* requirement or line this is.
_STOPWORD_TEXT: Final[str] = """
a an and or the with of in on for to at by from as is are be been experience
strong working knowledge years year using use used our your you we they this that
deneyim deneyimi ile ve bilgisi bilgi yıl için gibi olan
"""
_STOPWORDS: Final[frozenset[str]] = frozenset(_STOPWORD_TEXT.split())


# ─── Reading the request ──────────────────────────────────────────────


def user_text(params: dict[str, Any]) -> str:
    """The user turn, which is where every prompt puts its data."""
    parts: list[str] = []
    for message in params.get("messages", []):
        content = message.get("content")
        if isinstance(content, dict):
            parts.append(str(content.get("text", "")))
        elif isinstance(content, str):
            parts.append(content)
    return "\n".join(parts)


def numbered_lines(text: str) -> list[tuple[str, str]]:
    """Every ``L<n>: text`` pair in the prompt, in order."""
    return [(match.group(1), match.group(2).strip()) for match in _LINE_RE.finditer(text)]


def content_words(text: str) -> set[str]:
    words = re.findall(r"[0-9a-zçğıöşü.+#]+", text.casefold())
    return {word.strip(".") for word in words if len(word) > 1 and word not in _STOPWORDS}


# ─── extract ──────────────────────────────────────────────────────────


def answer_requirements(prompt: str) -> dict[str, Any]:
    """Pull bullets out of the posting the way a careless reader would."""
    body = prompt
    if "<<<POSTING" in prompt:
        body = prompt.split("<<<POSTING", 1)[1].split("POSTING>>>", 1)[0]

    kind = "must"
    skipping = False
    requirements: list[dict[str, Any]] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        heading = line.casefold()
        if not line.startswith(("-", "•", "*", "·")):
            # A heading switches which half of the posting we are in. Anything
            # under Benefits is not a requirement, and a model that lists it
            # would be marked down for it here too.
            if any(word in heading for word in _SKIP_HEADINGS):
                skipping = True
                continue
            if any(word in heading for word in _NICE_HEADINGS):
                kind, skipping = "nice", False
                continue
            if heading.rstrip(":") in {"requirements", "qualifications", "gereksinimler", "aranan nitelikler", "nitelikler"}:
                kind, skipping = "must", False
            continue
        if skipping:
            continue
        match = _BULLET_RE.match(raw)
        if match is None:
            continue
        text = match.group(1).strip()
        if len(text) < 3:
            continue
        requirements.append(
            {
                "id": f"R{len(requirements) + 1}",
                "text": text[:120],
                "kind": kind,
                "category": categorize(text),
                "source_quote": text[:200],
            }
        )
        if len(requirements) >= 25:
            break

    title, company = posting_header(body)
    return {"posting_title": title, "company": company, "requirements": requirements}


def categorize(text: str) -> str:
    lowered = text.casefold()
    for category, words in _CATEGORY_WORDS.items():
        if any(word in lowered for word in words):
            return category
    return "skill"


def posting_header(body: str) -> tuple[str, str]:
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = re.split(r"\s+[—–-]\s+", line, maxsplit=1)
        title = parts[0].strip()
        company = parts[1].strip() if len(parts) > 1 else ""
        company = re.sub(r"\s*\(.*?\)\s*$", "", company).strip()
        return title[:80], company[:80]
    return "", ""


# ─── match ────────────────────────────────────────────────────────────


def answer_evidence(prompt: str) -> dict[str, Any]:
    """Keyword overlap, plus one citation to a line that does not exist.

    The invented citation is the point: `pipeline/match.py` is supposed to
    downgrade a status whose only evidence is imaginary, and nothing else in
    the eval exercises that branch.
    """
    lines = numbered_lines(prompt)
    line_words = [(line_id, content_words(text)) for line_id, text in lines]

    evidence: list[dict[str, Any]] = []
    for index, (req_id, _kind, text) in enumerate(_REQ_RE.findall(prompt)):
        wanted = content_words(text)
        scored = sorted(
            ((len(wanted & words) / max(len(wanted), 1), line_id) for line_id, words in line_words),
            reverse=True,
        )
        best = scored[0] if scored else (0.0, "")
        cited = [line_id for ratio, line_id in scored[:2] if ratio >= 0.34]

        if best[0] >= 0.5:
            status = "strong"
        elif best[0] >= 0.25:
            status = "partial"
        else:
            status, cited = "missing", []

        # Every fourth answered requirement cites a line the CV does not have.
        if status != "missing" and index % 4 == 3:
            cited = [*cited, "L9001"]

        evidence.append(
            {
                "requirement_id": req_id,
                "status": status,
                "line_ids": cited,
                "why": (f"Line {cited[0]} covers this." if cited else "No line covers this.")[:160],
            }
        )
    return {"evidence": evidence}


# ─── tailor ───────────────────────────────────────────────────────────


def answer_bullets(prompt: str) -> dict[str, Any]:
    """Half honest rewrites, half rewrites that smuggle in facts.

    A repair prompt gets the honest half only for the lines it names — the
    stub "complies" the second time, which is what lets the eval tell a
    verifier that repairs from one that merely drops.
    """
    repairing = "not supported by the source lines" in prompt
    lines = numbered_lines(prompt)
    targets = sorted({match.group(1) for match in re.finditer(r"\b(R\d+)\b", prompt)})

    bullets: list[dict[str, Any]] = []
    for index, (line_id, text) in enumerate(lines):
        honest = index % 2 == 0 or repairing
        suggestion = honest_rewrite(text) if honest else fabricated_rewrite(text, index)
        bullets.append(
            {
                "source_line_ids": [line_id],
                "suggestion": suggestion[:220],
                "targets": targets[:2],
            }
        )
    return {"bullets": bullets}


def honest_rewrite(text: str) -> str:
    """Reword using only what the line already says.

    Leading with the verb and dropping a filler word is the whole of an honest
    rewrite, and it has to survive the verifier — a run where none of these
    pass means the verifier stopped distinguishing rewording from inventing.
    """
    stripped = text.strip().rstrip(".")
    stripped = re.sub(r"^(Responsible for|Worked on|Helped to|Helped)\s+", "", stripped, flags=re.IGNORECASE)
    return f"{stripped[:1].upper()}{stripped[1:]}."


def fabricated_rewrite(text: str, index: int) -> str:
    """Add a claim the source cannot support — a different class each time."""
    stripped = text.strip().rstrip(".")
    inventions = (
        f"{stripped}, cutting costs by {INVENTED_PERCENT}.",
        f"{stripped} at {INVENTED_COMPANY}.",
        f"{stripped}, scaling it on {INVENTED_TOOL}.",
        f"{stripped}, lifting conversion by {INVENTED_WORDS}.",
        f"{stripped} while leading {INVENTED_TEAM}.",
    )
    return inventions[(index // 2) % len(inventions)]


# ─── letter ───────────────────────────────────────────────────────────


def answer_letter(prompt: str) -> dict[str, Any]:
    """An opening, honest evidence paragraphs, and one that invents.

    The fabricated paragraph cites real line ids, so a verifier that trusted
    the citation list instead of reading the sentence would pass it.
    """
    lines = numbered_lines(prompt)
    role = header_value(prompt, "ROLE") or "[Role]"
    company = header_value(prompt, "COMPANY") or "[Company]"

    paragraphs: list[dict[str, Any]] = [
        {"text": f"I am writing about the {role} role at {company}.", "line_ids": []}
    ]
    for line_id, text in lines[:2]:
        paragraphs.append({"text": honest_rewrite(text), "line_ids": [line_id]})
    if lines:
        line_id, text = lines[0]
        paragraphs.append(
            {
                "text": (
                    f"At {INVENTED_COMPANY} I {text.strip().rstrip('.').casefold()} "
                    f"and grew revenue by {INVENTED_PERCENT} in six weeks."
                ),
                "line_ids": [line_id],
            }
        )
    paragraphs.append({"text": "I would welcome the chance to talk it through.", "line_ids": []})
    return {"paragraphs": paragraphs}


def header_value(prompt: str, key: str) -> str:
    match = re.search(rf"^{key}:\s*(.+)$", prompt, re.MULTILINE)
    return match.group(1).strip() if match else ""


# ─── Dispatch ─────────────────────────────────────────────────────────

_ANSWERS: Final[dict[str, Any]] = {
    "receipts_requirements": answer_requirements,
    "receipts_evidence": answer_evidence,
    "receipts_tailored_bullets": answer_bullets,
    "receipts_cover_letter": answer_letter,
}


def main() -> int:
    params = json.loads(sys.stdin.read())
    schema = params.get("responseFormat", {}).get("json_schema", {})
    name = schema.get("name", "")
    answer = _ANSWERS.get(name)
    if answer is None:
        print(f"fabricating_sampler: unknown schema {name!r}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(answer(user_text(params)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
