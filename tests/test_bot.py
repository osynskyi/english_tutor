"""End-to-end bot tests: updates go through the real dispatcher, Telegram API calls are mocked."""

from aiogram.methods import EditMessageText, SendVoice
from aiogram.types import ReplyKeyboardMarkup

from tutor.bot.callbacks import AnswerCb, DictCb, DlgCb, LessonCb, ListenCb, NavCb, ProgressCb, QuizCb, SpeakCb

from .conftest import buttons, joined, texts


async def answer_quiz(tg, questions, wrong=(), start=0):
    """Answer questions from `start` on (correctly unless the index is in `wrong`); return the last replies."""
    replies = []
    for i, q in list(enumerate(questions))[start:]:
        if q["type"] == "choice":
            option = q["answer"] if i not in wrong else (q["answer"] + 1) % len(q["options"])
            replies = await tg.click(AnswerCb(q=i, o=option))
        else:
            replies = await tg.send(q["answers"][0] if i not in wrong else "wrong answer")
    return replies


async def test_start_shows_menu(tg):
    replies = await tg.send("/start")
    assert "Hello, Anna!" in texts(replies)[0]
    assert isinstance(replies[0].reply_markup, ReplyKeyboardMarkup)
    assert "Открыть сайт" in [b[0] for b in buttons(replies)]


async def test_help_and_unknown_text(tg):
    assert "English Tutor" in joined(await tg.send("/help"))
    assert "Выберите раздел" in joined(await tg.send("hello?"))


async def test_full_test_with_level(tg, content, db):
    replies = await tg.send("📝 Тесты")
    assert QuizCb(action="intro", kind="test", ref="placement").pack() in [b[1] for b in buttons(replies)]

    replies = await tg.click(QuizCb(action="intro", kind="test", ref="placement"))
    assert "Тест на уровень" in texts(replies)[0]
    assert "Вопрос 1/20" in texts(replies)[1]

    questions = content.test("placement")["questions"]
    replies = await answer_quiz(tg, questions)
    final = joined(replies)
    assert "20 из 20 (100%)" in final
    assert "уровень: <b>B2</b>" in final
    assert db.best(tg.chat_id, "test") == {"placement": 100}


async def test_quiz_feedback_and_mistakes(tg, content):
    await tg.click(QuizCb(action="intro", kind="test", ref="vocab-a1"))
    questions = content.test("vocab-a1")["questions"]

    replies = await tg.click(AnswerCb(q=0, o=0))  # wrong: "warm"
    edit = next(r for r in replies if isinstance(r, EditMessageText))
    assert "Неверно" in edit.text and "cold" in edit.text
    assert "Вопрос 2/" in texts(replies)[-1]

    stale = await tg.click(AnswerCb(q=0, o=1))
    assert stale[0].text == "Этот вопрос уже закрыт"

    replies = await answer_quiz(tg, questions, start=1)
    final = joined(replies)
    assert f"{len(questions) - 1} из {len(questions)}" in final
    assert "Работа над ошибками" in final and "<s>warm</s> → <b>cold</b>" in final


async def test_input_question_and_choice_reminder(tg, content):
    await tg.click(QuizCb(action="start", kind="grammar", ref="present-simple"))
    reminder = await tg.send("goes")  # question 1 is a choice question
    assert "кнопкой" in joined(reminder)

    questions = content.lesson("present-simple")["exercises"]
    for i in range(5):
        await tg.click(AnswerCb(q=i, o=questions[i]["answer"]))
    replies = await tg.send("Studies")
    assert "Верно" in texts(replies)[0]
    assert "Вопрос 7/8" in texts(replies)[1]
    replies = await tg.send("hass")
    assert "Неверно" in texts(replies)[0] and "has" in texts(replies)[0]
    replies = await tg.send("doesn't like")
    final = joined(replies)
    assert "7 из 8" in final and "Тема изучена" in final and "hass" in final


async def test_menu_button_interrupts_quiz(tg):
    await tg.click(QuizCb(action="start", kind="grammar", ref="to-be"))
    replies = await tg.send("📘 Грамматика")
    assert "Грамматика" in joined(replies)
    replies = await tg.send("is")  # no longer an answer
    assert "Выберите раздел" in joined(replies)


async def test_quit_quiz(tg):
    await tg.click(QuizCb(action="start", kind="test", ref="tenses"))
    replies = await tg.click(QuizCb(action="quit"))
    assert "остановились" in joined(replies)


async def test_grammar_lesson(tg, content, fake_speech):
    replies = await tg.send("/grammar")
    assert LessonCb(action="open", id="articles").pack() in [b[1] for b in buttons(replies)]

    replies = await tg.click(LessonCb(action="open", id="articles"))
    text = joined(replies)
    assert "Articles" in text and "Примеры" in text and "an hour" in text
    assert QuizCb(action="start", kind="grammar", ref="articles").pack() in [b[1] for b in buttons(replies)]

    replies = await tg.click(LessonCb(action="voice", id="articles"))
    assert any(isinstance(r, SendVoice) for r in replies)
    assert fake_speech.synthesized[-1][0].startswith(content.lesson("articles")["examples"][0]["en"])


async def test_dictation(tg, content, db, fake_speech):
    replies = await tg.click(DictCb(action="new", ref="A2"))
    voice = next(r for r in replies if isinstance(r, SendVoice))
    assert "Диктант A2" in voice.caption
    item = next(i for i in content.dictation if i["text"] == fake_speech.synthesized[-1][0])
    assert item["level"] == "A2"

    replies = await tg.send(item["text"])
    assert "100%" in joined(replies)
    assert db.best(tg.chat_id, "dictation") == {item["id"]: 100}

    # After checking, plain text is not treated as a dictation answer anymore
    assert "Выберите раздел" in joined(await tg.send("something"))


async def test_dictation_slow_and_show(tg, content, fake_speech):
    item = content.dictation[0]
    await tg.click(DictCb(action="slow", ref=item["id"]))
    assert fake_speech.synthesized[-1] == (item["text"], True)
    replies = await tg.click(DictCb(action="show", ref=item["id"]))
    assert item["text"] in joined(replies)


async def test_listening_text_quiz(tg, content):
    item = content.comprehension[0]
    replies = await tg.click(ListenCb(action="text", ref=item["id"]))
    assert isinstance(replies[1], SendVoice)
    assert ListenCb(action="play", ref=item["id"]).pack() in [b[1] for b in buttons(replies)]
    replies = await answer_quiz(tg, item["questions"])
    assert "3 из 3" in joined(replies)


async def test_speaking_repeat(tg, content, fake_speech, db):
    replies = await tg.click(SpeakCb(action="topic", ref="food"))
    phrase_text = fake_speech.synthesized[-1][0]
    phrase = next(p for p in content.phrases if p["text"] == phrase_text)
    assert phrase["topic"] == "food"
    assert phrase_text in joined(replies)

    assert "голосовое" in joined(await tg.send("typing instead"))

    fake_speech.transcript = phrase_text.lower().rstrip("!?.")
    replies = await tg.send_voice()
    assert "100%" in joined(replies)
    assert db.best(tg.chat_id, "speaking") == {phrase["id"]: 100}

    fake_speech.transcript = "something else entirely"
    replies = await tg.send_voice()
    assert "Ошибки или пропуски" in joined(replies)


async def test_speaking_question(tg, content, fake_speech):
    await tg.click(SpeakCb(action="question", ref="A1"))
    asked = fake_speech.synthesized[-1][0]
    question = next(q for q in content.speaking_questions if q["question"] == asked)
    assert question["level"] == "A1"
    fake_speech.transcript = "I get up at seven and drink some coffee with milk"
    replies = await tg.send_voice()
    text = joined(replies)
    assert "Вы сказали" in text and "Пример ответа" in text
    assert SpeakCb(action="sample", ref=question["id"]).pack() in [b[1] for b in buttons(replies)]


async def test_dialogue_flow(tg, content, fake_speech, db):
    dialogue = content.dialogue("cafe")
    replies = await tg.click(DlgCb(action="start", id="cafe"))
    assert dialogue["turns"][0]["line"] in joined(replies)
    assert "<tg-spoiler>" in joined(replies)

    replies = await tg.send("What time is it?")
    assert "не совсем" in joined(replies)

    fake_speech.transcript = "I'd like a latte please"
    replies = await tg.send_voice()
    text = joined(replies)
    assert "Вы: <i>I'd like a latte please</i>" in text
    assert dialogue["turns"][1]["line"] in text

    hint = await tg.click(DlgCb(action="hint", id="cafe", turn=1))
    assert dialogue["turns"][1]["hint"] in joined(hint)
    stale = await tg.click(DlgCb(action="hint", id="cafe", turn=0))
    assert stale[0].text == "Эта реплика уже пройдена"

    await tg.click(DlgCb(action="skip", id="cafe", turn=1))
    await tg.send("No, thanks")
    await tg.send("For here")
    replies = await tg.send("By card")
    text = joined(replies)
    assert dialogue["final"] in text and "Диалог завершён" in text
    assert "С первой попытки: 3 из 5" in text
    assert db.best(tg.chat_id, "dialogue") == {"cafe": 60}


async def test_dialogue_stop(tg):
    await tg.click(DlgCb(action="start", id="hotel"))
    replies = await tg.click(DlgCb(action="stop", id="hotel"))
    assert "остановлен" in joined(replies)


async def test_free_voice(tg, fake_speech):
    fake_speech.transcript = "Hello, I live in a big city"
    replies = await tg.send_voice()
    assert "Я услышал" in joined(replies) and "7 слов" in joined(replies)
    fake_speech.transcript = ""
    assert "Не удалось разобрать" in joined(await tg.send_voice())


async def test_too_long_voice(tg):
    replies = await tg.send_voice(duration=600)
    assert "слишком длинное" in joined(replies)


async def test_speech_services_down(tg, fake_speech):
    fake_speech.fail_tts = True
    replies = await tg.click(DictCb(action="new", ref="A1"))
    assert not any(isinstance(r, SendVoice) for r in replies)
    assert "Озвучка сейчас недоступна" in joined(replies)

    await tg.send("/cancel")  # leave the dictation: voice outside exercises = free speech
    fake_speech.fail_stt = True
    replies = await tg.send_voice()
    assert "Распознавание речи сейчас недоступно" in joined(replies)


async def test_progress_and_reset(tg, content, db):
    assert "Вы ещё не занимались" in joined(await tg.send("📊 Прогресс"))
    await tg.click(QuizCb(action="intro", kind="test", ref="placement"))
    await answer_quiz(tg, content.test("placement")["questions"], wrong=set(range(8)))
    replies = await tg.send("/progress")
    text = joined(replies)
    assert "Тесты: пройдено 1 из" in text
    assert "Уровень по тесту: <b>B1</b>" in text  # 12 of 20

    await tg.click(ProgressCb(action="reset"))
    replies = await tg.click(ProgressCb(action="confirm"))
    assert "Прогресс удалён" in joined(replies)
    assert db.stats(tg.chat_id)["kinds"] == {}


async def test_navigation_buttons(tg):
    for section, marker in [("tests", "Тесты"), ("listening", "Аудирование"), ("speaking", "Говорение"),
                            ("dialogues", "Диалоги"), ("progress", "прогресс"), ("menu", "Главное меню")]:
        assert marker in joined(await tg.click(NavCb(to=section))), section


async def test_stale_buttons(tg):
    replies = await tg.click(AnswerCb(q=3, o=1))
    assert replies[0].text == "Этот тест уже завершён"
    replies = await tg.click("unknown:data")
    assert replies[0].text == "Эта кнопка больше не активна"
