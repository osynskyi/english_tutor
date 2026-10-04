"""🗣 Speaking: repeat after me, answer questions."""

from __future__ import annotations

import random

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...content import LEVELS, Content
from ...core.scoring import check_free_answer, compare_texts
from ...core.speech import SpeechService
from ..callbacks import SpeakCb
from ..common import SpeakingState, back_button, esc, format_comparison, send_speech, transcribe
from ..storage import Storage

router = Router(name="speaking")


async def show_speaking(message: Message) -> None:
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Повторяй за мной", callback_data=SpeakCb(action="topics").pack())],
        [InlineKeyboardButton(text="❓ Ответь на вопрос", callback_data=SpeakCb(action="questions").pack())],
    ])
    await message.answer(
        "🗣 <b>Говорение</b>\n\n"
        "🔁 <b>Повторяй за мной</b> — бот присылает фразу, вы повторяете её голосовым сообщением, "
        "бот распознаёт речь и оценивает произношение.\n"
        "❓ <b>Ответь на вопрос</b> — отвечайте голосом на вопросы, сравните ответ с примером.\n"
        "🎙 <b>Свободная речь</b> — просто отправьте голосовое в любой момент, и я покажу, что услышал.",
        reply_markup=markup,
    )


# ----------------------------------------------------------- repeat after me


@router.callback_query(SpeakCb.filter(F.action == "topics"))
async def on_topics(callback: CallbackQuery, content: Content) -> None:
    await callback.answer()
    builder = InlineKeyboardBuilder()
    for key, title in content.speaking_topics.items():
        builder.button(text=title, callback_data=SpeakCb(action="topic", ref=key))
    builder.adjust(2)
    builder.row(back_button("speaking", "⬅️ Назад"))
    await callback.message.answer("Выберите тему:", reply_markup=builder.as_markup())


def _phrase_markup(phrase: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🐢 Медленно", callback_data=SpeakCb(action="slow", ref=phrase["id"]).pack()),
            InlineKeyboardButton(text="⏭ Другая фраза", callback_data=SpeakCb(action="topic", ref=phrase["topic"]).pack()),
        ],
        [back_button("speaking", "⬅️ Говорение")],
    ])


@router.callback_query(SpeakCb.filter(F.action == "topic"))
async def on_topic(
    callback: CallbackQuery, callback_data: SpeakCb, state: FSMContext, content: Content, speech: SpeechService
) -> None:
    await callback.answer()
    phrases = content.phrases_by_topic(callback_data.ref) or content.phrases
    last = (await state.get_data()).get("phrase")
    phrase = random.choice([p for p in phrases if p["id"] != last] or phrases)
    await state.set_state(SpeakingState.repeat)
    await state.update_data(phrase=phrase["id"])
    await callback.message.answer(
        f"🔁 <b>{esc(phrase['text'])}</b>\n<i>{esc(phrase['ru'])}</i>\n\n"
        "🎤 Послушайте и <b>запишите голосовое сообщение</b> с этой фразой."
    )
    await send_speech(callback.message, speech, phrase["text"], reply_markup=_phrase_markup(phrase))


@router.callback_query(SpeakCb.filter(F.action == "slow"))
async def on_slow(callback: CallbackQuery, callback_data: SpeakCb, content: Content, speech: SpeechService) -> None:
    await callback.answer()
    phrase = content.phrase(callback_data.ref)
    await send_speech(callback.message, speech, phrase["text"], slow=True, caption="🐢 Медленно")


@router.message(SpeakingState.repeat, F.voice | F.audio)
async def on_repeat_voice(
    message: Message, bot: Bot, state: FSMContext, content: Content, speech: SpeechService, db: Storage
) -> None:
    phrase = content.phrase((await state.get_data())["phrase"])
    said = await transcribe(message, bot, speech)
    if said is None:
        return
    result = compare_texts(phrase["text"], said)
    db.add_result(message.chat.id, "speaking", phrase["id"], result.score, 100)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Следующая фраза", callback_data=SpeakCb(action="topic", ref=phrase["topic"]).pack())],
        [back_button("speaking", "⬅️ Говорение")],
    ])
    tip = "\n\n🎤 Можно записать ещё раз, чтобы улучшить результат." if result.score < 95 else ""
    await message.answer(format_comparison(result, "🗣 Распознано") + tip, reply_markup=markup)


@router.message(SpeakingState.repeat, F.text)
async def on_repeat_text(message: Message) -> None:
    await message.answer("Это задание на произношение — запишите <b>голосовое сообщение</b> 🎤 (значок микрофона справа от поля ввода).")


# ------------------------------------------------------------------ questions


@router.callback_query(SpeakCb.filter(F.action == "questions"))
async def on_questions(callback: CallbackQuery) -> None:
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.button(text="Все уровни", callback_data=SpeakCb(action="question", ref="all"))
    for level in LEVELS:
        builder.button(text=level, callback_data=SpeakCb(action="question", ref=level))
    builder.adjust(1, 4)
    builder.row(back_button("speaking", "⬅️ Назад"))
    await callback.message.answer("Выберите уровень вопросов:", reply_markup=builder.as_markup())


@router.callback_query(SpeakCb.filter(F.action == "question"))
async def on_question(
    callback: CallbackQuery, callback_data: SpeakCb, state: FSMContext, content: Content, speech: SpeechService
) -> None:
    await callback.answer()
    level = callback_data.ref
    pool = [q for q in content.speaking_questions if level == "all" or q["level"] == level] or content.speaking_questions
    last = (await state.get_data()).get("question")
    question = random.choice([q for q in pool if q["id"] != last] or pool)
    await state.set_state(SpeakingState.answer)
    await state.update_data(question=question["id"], question_level=level)
    await send_speech(
        callback.message, speech, question["question"],
        caption=f"❓ <b>{esc(question['question'])}</b>\n<i>{esc(question['ru'])}</i>\n\n"
                f"🎤 Ответьте голосовым сообщением (желательно от {question['min_words']} слов).",
    )


@router.message(SpeakingState.answer, F.voice | F.audio)
async def on_answer_voice(
    message: Message, bot: Bot, state: FSMContext, content: Content, speech: SpeechService, db: Storage
) -> None:
    data = await state.get_data()
    question = content.speaking_question(data["question"])
    said = await transcribe(message, bot, speech)
    if said is None:
        return
    result = check_free_answer(question, said)
    db.add_result(message.chat.id, "answer", question["id"], min(result.words, result.min_words), result.min_words)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔊 Пример ответа", callback_data=SpeakCb(action="sample", ref=question["id"]).pack())],
        [InlineKeyboardButton(
            text="▶️ Следующий вопрос",
            callback_data=SpeakCb(action="question", ref=data.get("question_level", "all")).pack(),
        )],
    ])
    await message.answer(
        f"🗣 Вы сказали: <i>{esc(said) or '—'}</i>\n"
        f"Слов: {result.words} (рекомендуется от {result.min_words})\n\n"
        f"{result.feedback}\n\n💡 <b>Пример ответа:</b> {esc(result.sample)}",
        reply_markup=markup,
    )


@router.message(SpeakingState.answer, F.text)
async def on_answer_text(message: Message) -> None:
    await message.answer("Ответьте, пожалуйста, <b>голосовым сообщением</b> 🎤 — это тренировка речи.")


@router.callback_query(SpeakCb.filter(F.action == "sample"))
async def on_sample(callback: CallbackQuery, callback_data: SpeakCb, content: Content, speech: SpeechService) -> None:
    await callback.answer()
    question = content.speaking_question(callback_data.ref)
    await send_speech(callback.message, speech, question["sample"], caption="💡 Пример ответа")
