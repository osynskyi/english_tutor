"""Learning content (grammar, tests, listening, speaking, dialogues) stored as JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
LEVELS = ["A1", "A2", "B1", "B2"]

Item = dict[str, Any]


class NotFound(KeyError):
    pass


def _index(items: list[Item]) -> dict[str, Item]:
    return {item["id"]: item for item in items}


@dataclass
class Content:
    grammar: list[Item]
    tests: list[Item]
    dictation: list[Item]
    comprehension: list[Item]
    phrases: list[Item]
    speaking_topics: dict[str, str]
    speaking_questions: list[Item]
    dialogues: list[Item]

    def __post_init__(self) -> None:
        self._grammar = _index(self.grammar)
        self._tests = _index(self.tests)
        self._dictation = _index(self.dictation)
        self._comprehension = _index(self.comprehension)
        self._phrases = _index(self.phrases)
        self._questions = _index(self.speaking_questions)
        self._dialogues = _index(self.dialogues)

    @staticmethod
    def _get(index: dict[str, Item], key: str, what: str) -> Item:
        try:
            return index[key]
        except KeyError:
            raise NotFound(f"{what} '{key}' not found") from None

    def lesson(self, lesson_id: str) -> Item:
        return self._get(self._grammar, lesson_id, "Lesson")

    def test(self, test_id: str) -> Item:
        return self._get(self._tests, test_id, "Test")

    def dictation_item(self, item_id: str) -> Item:
        return self._get(self._dictation, item_id, "Dictation")

    def comprehension_item(self, item_id: str) -> Item:
        return self._get(self._comprehension, item_id, "Listening text")

    def phrase(self, phrase_id: str) -> Item:
        return self._get(self._phrases, phrase_id, "Phrase")

    def speaking_question(self, question_id: str) -> Item:
        return self._get(self._questions, question_id, "Question")

    def dialogue(self, dialogue_id: str) -> Item:
        return self._get(self._dialogues, dialogue_id, "Dialogue")

    def questions(self, kind: str, ref: str) -> list[Item]:
        """Questions of a quiz: kind is "test", "grammar" or "listening"."""
        if kind == "test":
            return self.test(ref)["questions"]
        if kind == "grammar":
            return self.lesson(ref)["exercises"]
        if kind == "listening":
            return self.comprehension_item(ref)["questions"]
        raise NotFound(f"Unknown quiz kind '{kind}'")

    def quiz_title(self, kind: str, ref: str) -> str:
        if kind == "test":
            return self.test(ref)["title"]
        if kind == "grammar":
            return self.lesson(ref)["title"]
        return self.comprehension_item(ref)["title"]

    @staticmethod
    def estimate_level(test: Item, correct: int) -> str | None:
        """Level by a test score, for tests that define "grading" [[min_correct, level], ...]."""
        level = None
        for minimum, name in test.get("grading", []):
            if correct >= minimum:
                level = name
        return level

    def dictation_by_level(self, level: str) -> list[Item]:
        return [d for d in self.dictation if d["level"] == level]

    def phrases_by_topic(self, topic: str) -> list[Item]:
        return [p for p in self.phrases if p["topic"] == topic]


def _read(name: str, data_dir: Path) -> Any:
    return json.loads((data_dir / name).read_text(encoding="utf-8"))


def load_content(data_dir: Path = DATA_DIR) -> Content:
    listening = _read("listening.json", data_dir)
    speaking = _read("speaking.json", data_dir)
    return Content(
        grammar=_read("grammar.json", data_dir),
        tests=_read("tests.json", data_dir),
        dictation=listening["dictation"],
        comprehension=listening["comprehension"],
        phrases=speaking["phrases"],
        speaking_topics=speaking["topics"],
        speaking_questions=speaking["questions"],
        dialogues=_read("dialogues.json", data_dir),
    )


@lru_cache(maxsize=1)
def get_content() -> Content:
    return load_content()


def public_question(question: Item) -> Item:
    """Question without the answer (for the website)."""
    hidden = {"answer", "answers", "explanation"}
    return {k: v for k, v in question.items() if k not in hidden}


def validate(content: Content) -> list[str]:
    """Return a list of problems in the content (empty list == valid)."""
    errors: list[str] = []

    def check_ids(items: list[Item], what: str) -> None:
        seen: set[str] = set()
        for item in items:
            if item["id"] in seen:
                errors.append(f"duplicate {what} id {item['id']}")
            seen.add(item["id"])
            if len(item["id"]) > 24:
                errors.append(f"{what} id too long for Telegram callbacks: {item['id']}")

    def check_questions(questions: list[Item], where: str) -> None:
        check_ids(questions, f"question in {where}")
        if not questions:
            errors.append(f"{where}: no questions")
        for q in questions:
            label = f"{where}/{q['id']}"
            if not q.get("question"):
                errors.append(f"{label}: empty question")
            if q["type"] == "choice":
                opts = q.get("options", [])
                if len(opts) < 2 or len(opts) > 6:
                    errors.append(f"{label}: needs 2..6 options")
                if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(opts):
                    errors.append(f"{label}: bad answer index")
                if len(set(opts)) != len(opts):
                    errors.append(f"{label}: duplicate options")
            elif q["type"] == "input":
                if not q.get("answers"):
                    errors.append(f"{label}: no accepted answers")
            else:
                errors.append(f"{label}: unknown type {q['type']}")

    check_ids(content.grammar, "lesson")
    for lesson in content.grammar:
        if lesson["level"] not in LEVELS:
            errors.append(f"lesson {lesson['id']}: bad level")
        if not lesson.get("theory") or not lesson.get("examples"):
            errors.append(f"lesson {lesson['id']}: theory/examples missing")
        check_questions(lesson["exercises"], f"lesson {lesson['id']}")

    check_ids(content.tests, "test")
    for test in content.tests:
        check_questions(test["questions"], f"test {test['id']}")

    check_ids(content.dictation, "dictation")
    for item in content.dictation:
        if item["level"] not in LEVELS:
            errors.append(f"dictation {item['id']}: bad level")
    for level in LEVELS:
        if not content.dictation_by_level(level):
            errors.append(f"no dictation for level {level}")

    check_ids(content.comprehension, "listening text")
    for item in content.comprehension:
        check_questions(item["questions"], f"listening {item['id']}")

    check_ids(content.phrases, "phrase")
    for phrase in content.phrases:
        if phrase["topic"] not in content.speaking_topics:
            errors.append(f"phrase {phrase['id']}: unknown topic {phrase['topic']}")
    for topic in content.speaking_topics:
        if not content.phrases_by_topic(topic):
            errors.append(f"topic {topic} has no phrases")

    check_ids(content.speaking_questions, "speaking question")
    check_ids(content.dialogues, "dialogue")
    for dialogue in content.dialogues:
        if not dialogue.get("turns"):
            errors.append(f"dialogue {dialogue['id']}: no turns")
        for i, turn in enumerate(dialogue["turns"]):
            for key in ("line", "ru", "hint"):
                if not turn.get(key):
                    errors.append(f"dialogue {dialogue['id']} turn {i}: missing {key}")
    return errors
