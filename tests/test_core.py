import pytest

from tutor.content import validate
from tutor.core.render import inline, split_message, theory_to_html, theory_to_telegram
from tutor.core.scoring import (
    check_answer,
    check_free_answer,
    check_turn,
    compare_texts,
    match_reply,
)
from tutor.core.text import normalize, normalize_words, number_to_words, words_match

# ------------------------------------------------------------------ text


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("I'm fine.", "I am fine"),
        ("He doesn’t like it!", "he does not like it"),
        ("I can't swim", "I cannot swim"),
        ("at 7 o'clock", "at seven o'clock"),
        ("My favourite colour", "my favorite color"),
        ("twenty-five", "25"),
        ("OK, let's go", "okay let us go"),
        ("We're going to win", "we are gonna win"),
    ],
)
def test_normalize_equivalents(a, b):
    assert normalize(a) == normalize(b)


def test_number_to_words():
    assert number_to_words(0) == "zero"
    assert number_to_words(13) == "thirteen"
    assert number_to_words(40) == "forty"
    assert number_to_words(125) == "one hundred twenty five"
    assert number_to_words(2024) == "two thousand twenty four"


def test_time_and_ordinals():
    assert normalize_words("7:30") == ["seven", "thirty"]
    assert normalize_words("the 5th of May")[:3] == ["the", "five", "th"]


def test_words_match_plural():
    assert words_match("coffees", "coffee")
    assert words_match("strawberries", "strawberry")
    assert not words_match("tea", "coffee")


# --------------------------------------------------------------- answers

CHOICE = {"type": "choice", "options": ["go", "goes", "going"], "answer": 1, "explanation": "she → goes"}
INPUT = {"type": "input", "answers": ["doesn't like", "does not like"], "explanation": ""}


def test_check_choice_by_index_and_text():
    assert check_answer(CHOICE, 1).correct
    assert check_answer(CHOICE, "1").correct
    assert check_answer(CHOICE, "Goes").correct
    wrong = check_answer(CHOICE, 0)
    assert not wrong.correct
    assert wrong.correct_answer == "goes"
    assert wrong.given == "go"
    assert wrong.explanation == "she → goes"


def test_check_choice_bad_input():
    assert not check_answer(CHOICE, 7).correct
    assert not check_answer(CHOICE, True).correct
    assert not check_answer(CHOICE, "nonsense").correct


def test_check_input_normalized():
    assert check_answer(INPUT, "Doesn't like").correct
    assert check_answer(INPUT, "  does   not like. ").correct
    assert check_answer(INPUT, "doesn’t like").correct
    assert not check_answer(INPUT, "don't like").correct
    assert not check_answer(INPUT, "").correct


# ----------------------------------------------------- dictation / speech


def test_compare_perfect():
    result = compare_texts("I'm going home.", "I am going home")
    assert result.score == 100
    assert all(m.ok for m in result.marks)
    assert result.missing == []


def test_compare_missing_and_extra_words():
    result = compare_texts("She drinks tea every morning.", "she drinks coffee every morning")
    assert 0 < result.score < 100
    assert [m.word for m in result.marks if not m.ok] == ["tea"]
    assert result.missing == ["tea"]
    assert result.extra == ["coffee"]


def test_compare_empty_answer():
    result = compare_texts("Hello world", "")
    assert result.score == 0
    assert not any(m.ok for m in result.marks)


def test_compare_contraction_word_partially_matched():
    result = compare_texts("I'm happy", "I happy")
    assert result.marks[0].ok is False  # "I'm" = "I am", "am" missing
    assert result.marks[1].ok is True


# --------------------------------------------------------------- dialogues


def test_match_reply():
    assert match_reply(["coffee", "tea"], "Two coffees, please")[0]
    assert match_reply(["take away"], "Take away please") == (True, "take away")
    assert not match_reply(["take away"], "I will take it")[0]
    assert match_reply([], "anything")[0]
    assert not match_reply([], "")[0]


def test_check_turn():
    turn = {"hint": "Medium, please.", "expect": ["small", "medium", "large"]}
    assert check_turn(turn, "A medium one").accepted
    bad = check_turn(turn, "I don't know")
    assert not bad.accepted and bad.hint == "Medium, please."
    assert not check_turn(turn, "").accepted
    long_turn = {"hint": "...", "expect": [], "min_words": 5}
    assert not check_turn(long_turn, "I am good").accepted
    assert check_turn(long_turn, "I am a good team player").accepted


def test_check_free_answer():
    question = {"sample": "My name is Anna.", "min_words": 5}
    short = check_free_answer(question, "Anna")
    assert not short.enough and short.words == 1
    good = check_free_answer(question, "My name is Anna and I live in Kyiv")
    assert good.enough and good.sample == "My name is Anna."


# ----------------------------------------------------------------- render


BLOCKS = [
    {"type": "h", "text": "Title"},
    {"type": "p", "text": "Use **to be** & __not__ `code` <script>"},
    {"type": "rule", "text": "S + **V**"},
    {"type": "note", "text": "Tip"},
    {"type": "list", "items": ["one", "two"]},
    {"type": "table", "rows": [["A", "B"], ["1", "2"]]},
]


def test_inline_escapes_html():
    assert inline("<b>x</b> **y**") == "&lt;b&gt;x&lt;/b&gt; <b>y</b>"


def test_theory_to_html():
    html = theory_to_html(BLOCKS)
    assert "<h3>Title</h3>" in html
    assert "<b>to be</b> &amp; <i>not</i> <code>code</code> &lt;script&gt;" in html
    assert '<div class="rule">' in html and "<table>" in html and "<li>two</li>" in html


def test_theory_to_telegram_uses_supported_tags_only():
    text = theory_to_telegram(BLOCKS)
    assert "<blockquote>" in text and "• one" in text
    for tag in ("<h3>", "<p>", "<ul>", "<table>", "<div"):
        assert tag not in text


def test_theory_unknown_block():
    with pytest.raises(ValueError):
        theory_to_html([{"type": "video", "text": "x"}])


def test_split_message():
    text = "\n\n".join(["a" * 1500] * 5)
    chunks = split_message(text, limit=4000)
    assert len(chunks) == 3
    assert all(len(c) <= 4000 for c in chunks)
    assert split_message("short") == ["short"]


# ---------------------------------------------------------------- content


def test_content_is_valid(content):
    assert validate(content) == []


def test_content_volume(content):
    assert len(content.grammar) >= 12
    assert len(content.tests) >= 6
    assert len(content.dictation) >= 24
    assert len(content.dialogues) >= 5


def test_every_lesson_renders_for_telegram(content):
    for lesson in content.grammar:
        assert len(theory_to_telegram(lesson["theory"])) < 3500, lesson["id"]


def test_correct_answers_pass_their_own_check(content):
    for test in content.tests:
        for q in test["questions"]:
            answer = q["answer"] if q["type"] == "choice" else q["answers"][0]
            assert check_answer(q, answer).correct, (test["id"], q["id"])


def test_dialogue_hints_are_accepted(content):
    for dialogue in content.dialogues:
        for i, turn in enumerate(dialogue["turns"]):
            assert check_turn(turn, turn["hint"]).accepted, (dialogue["id"], i)


def test_speaking_samples_are_long_enough(content):
    for q in content.speaking_questions:
        assert check_free_answer(q, q["sample"]).enough, q["id"]


def test_estimate_level(content):
    test = content.test("placement")
    assert content.estimate_level(test, 0) == "A1"
    assert content.estimate_level(test, 8) == "A2"
    assert content.estimate_level(test, 20) == "B2"
    assert content.estimate_level(content.test("tenses"), 10) is None
