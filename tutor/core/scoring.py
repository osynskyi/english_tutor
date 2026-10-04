"""Checking answers: quiz questions, dictation / pronunciation, dialogue replies."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .text import normalize, normalize_words, split_words, words_match

# ---------------------------------------------------------------- quiz questions


@dataclass
class CheckResult:
    correct: bool
    correct_answer: str
    explanation: str = ""
    given: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def correct_answer_text(question: dict[str, Any]) -> str:
    if question["type"] == "choice":
        return question["options"][question["answer"]]
    return question["answers"][0]


def check_answer(question: dict[str, Any], answer: Any) -> CheckResult:
    """Check a learner's answer to a "choice" or "input" question.

    For "choice" the answer is an option index (or the option text);
    for "input" it is free text compared against all accepted answers
    after normalization ("doesn't" == "does not", case/punctuation ignored).
    """
    expected = correct_answer_text(question)
    explanation = question.get("explanation", "")
    if question["type"] == "choice":
        options = question["options"]
        index: int | None = None
        if isinstance(answer, bool):
            index = None
        elif isinstance(answer, int):
            index = answer
        elif isinstance(answer, str):
            if answer.strip().isdigit():
                index = int(answer.strip())
            else:
                wanted = normalize(answer)
                index = next((i for i, o in enumerate(options) if normalize(o) == wanted), None)
        given = options[index] if index is not None and 0 <= index < len(options) else str(answer)
        return CheckResult(index == question["answer"], expected, explanation, given)

    given = str(answer or "").strip()
    accepted = {normalize(a) for a in question["answers"]}
    return CheckResult(normalize(given) in accepted and given != "", expected, explanation, given)


# ------------------------------------------------- dictation / pronunciation


@dataclass
class WordMark:
    word: str  # word as written in the expected text (with punctuation)
    ok: bool


@dataclass
class Comparison:
    score: int  # 0..100
    verdict: str
    marks: list[WordMark] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    heard: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verdict_for(score: int) -> str:
    if score >= 95:
        return "Отлично! 🎉"
    if score >= 80:
        return "Очень хорошо! 👍"
    if score >= 60:
        return "Неплохо, но есть ошибки."
    if score >= 30:
        return "Попробуйте ещё раз."
    return "Почти ничего не совпало — попробуйте ещё раз."


def compare_texts(expected: str, actual: str) -> Comparison:
    """Word-level comparison of a reference sentence with what was typed / said.

    Returns a 0..100 similarity score and, for every word of the reference
    text, whether it was reproduced correctly.
    """
    display = expected.split()
    flat: list[str] = []
    owner: list[int] = []
    for i, token in enumerate(display):
        for word in normalize_words(token):
            flat.append(word)
            owner.append(i)

    heard = normalize_words(actual)
    matcher = SequenceMatcher(a=flat, b=heard, autojunk=False)
    matched = [False] * len(flat)
    extra: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                matched[k] = True
        elif tag in ("insert", "replace"):
            extra.extend(heard[j1:j2])

    total = len(flat) + len(heard)
    score = round(200 * sum(matched) / total) if total else 0

    marks: list[WordMark] = []
    missing: list[str] = []
    for i, token in enumerate(display):
        parts = [matched[k] for k, o in enumerate(owner) if o == i]
        ok = all(parts) if parts else True
        marks.append(WordMark(token, ok))
        if not ok:
            missing.append(token.strip(".,!?;:\"()«»"))
    return Comparison(score, verdict_for(score), marks, missing, extra, actual.strip())


# ------------------------------------------------------------ dialogue replies


def match_reply(expect: list[str], reply: str) -> tuple[bool, str | None]:
    """Is the reply acceptable for a dialogue turn?

    `expect` lists alternatives; each alternative is a set of words that must
    all appear in the reply ("coffee", "two tickets"). An empty list accepts
    any non-empty reply.
    """
    words = normalize_words(reply)
    if not words:
        return False, None
    if not expect:
        return True, None
    for alternative in expect:
        required = normalize_words(alternative)
        if all(any(words_match(r, w) for w in words) for r in required):
            return True, alternative
    return False, None


def count_words(text: str) -> int:
    return len(split_words(text))


def keyword_hits(keywords: list[str], text: str) -> list[str]:
    words = normalize_words(text)
    return [k for k in keywords if all(any(words_match(r, w) for w in words) for r in normalize_words(k))]


@dataclass
class TurnResult:
    accepted: bool
    feedback: str
    hint: str
    words: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_turn(turn: dict[str, Any], reply: str) -> TurnResult:
    """Check a reply in a role-play dialogue (keywords and/or minimal length)."""
    words = count_words(reply)
    hint = turn["hint"]
    if words == 0:
        return TurnResult(False, "Я ничего не услышал. Попробуйте ещё раз.", hint, 0)
    min_words = turn.get("min_words", 0)
    if words < min_words:
        return TurnResult(False, f"Ответьте подробнее — хотя бы {min_words} слов.", hint, words)
    accepted, _ = match_reply(turn.get("expect", []), reply)
    if accepted:
        return TurnResult(True, "Отлично, вас поняли! 👍", hint, words)
    return TurnResult(False, "Хм, ответ не совсем подходит к вопросу. Попробуйте ещё раз или посмотрите подсказку.", hint, words)


@dataclass
class FreeAnswerResult:
    words: int
    min_words: int
    enough: bool
    feedback: str
    sample: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_free_answer(question: dict[str, Any], transcript: str) -> FreeAnswerResult:
    """Feedback for an open speaking question: we can only judge the length."""
    words = count_words(transcript)
    min_words = question.get("min_words", 5)
    if words == 0:
        feedback = "Я ничего не услышал. Попробуйте ещё раз."
    elif words < min_words:
        feedback = f"Хорошее начало! Попробуйте ответить подробнее — хотя бы {min_words} слов."
    else:
        feedback = "Отличный развёрнутый ответ! 👏 Сравните его с примером."
    return FreeAnswerResult(words, min_words, words >= min_words, feedback, question["sample"])
