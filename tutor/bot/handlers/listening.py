"""🎧 Listening: dictation and texts with questions."""

from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...content import LEVELS, Content
from ...core.scoring import compare_texts
from ...core.speech import SpeechService
from ..callbacks import DictCb, ListenCb
from ..common import DictationState, back_button, esc, format_comparison, send_speech
from ..storage import Storage
from .quiz import start_quiz

router = Router(name="listening")


async def show_listening(message: Message, content: Content, db: Storage) -> None:
    best = db.best(message.chat.id, "listening")
    builder = InlineKeyboardBuilder()
    for level in LEVELS:
        builder.button(text=f"✍️ Диктант {level}", callback_data=DictCb(action="new", ref=level))
    for item in content.comprehension:
        mark = f" · {best[item['id']]}%" if item["id"] in best else ""
        builder.button(
            text=f"🎧 {item['level']} · {item['title']}{mark}",
            callback_data=ListenCb(action="text", ref=item["id"]),
        )
    builder.adjust(2, 2, *([1] * len(content.comprehension)))
    await message.answer(
        "🎧 <b>Аудирование</b>\n\n"
        "✍️ <b>Диктант</b> — бот присылает голосовое, вы пишете услышанную фразу.\n"
        "🎧 <b>Тексты</b> — прослушайте рассказ и ответьте на вопросы.",
        reply_markup=builder.as_markup(),
    )


# ------------------------------------------------------------------ dictation


def _dictation_markup(item: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🐢 Медленнее", callback_data=DictCb(action="slow", ref=item["id"]).pack()),
            InlineKeyboardButton(text="🙈 Показать ответ", callback_data=DictCb(action="show", ref=item["id"]).pack()),
        ],
        [InlineKeyboardButton(text="⏭ Другая фраза", callback_data=DictCb(action="new", ref=item["level"]).pack())],
    ])


@router.callback_query(DictCb.filter(F.action == "new"))
async def on_new_dictation(
    callback: CallbackQuery, callback_data: DictCb, state: FSMContext, content: Content, speech: SpeechService
) -> None:
    await callback.answer()
    level = callback_data.ref if callback_data.ref in LEVELS else LEVELS[0]
    last = (await state.get_data()).get("last_dictation")
    items = content.dictation_by_level(level)
    item = random.choice([i for i in items if i["id"] != last] or items)
    await state.set_state(DictationState.waiting)
    await state.update_data(dictation=item["id"], last_dictation=item["id"])
    await send_speech(
        callback.message, speech, item["text"],
        caption=f"✍️ <b>Диктант {level}</b>\nПрослушайте и напишите фразу по-английски.",
        reply_markup=_dictation_markup(item),
    )


@router.callback_query(DictCb.filter(F.action == "slow"))
async def on_slow_dictation(callback: CallbackQuery, callback_data: DictCb, content: Content, speech: SpeechService) -> None:
    await callback.answer()
    item = content.dictation_item(callback_data.ref)
    await send_speech(callback.message, speech, item["text"], slow=True, caption="🐢 Медленно")


@router.callback_query(DictCb.filter(F.action == "show"))
async def on_show_dictation(callback: CallbackQuery, callback_data: DictCb, state: FSMContext, content: Content) -> None:
    await callback.answer()
    item = content.dictation_item(callback_data.ref)
    if (await state.get_data()).get("dictation") == item["id"]:
        await state.set_state(None)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Следующая фраза", callback_data=DictCb(action="new", ref=item["level"]).pack())]
    ])
    await callback.message.answer(
        f"📖 <b>{esc(item['text'])}</b>\n🇷🇺 <i>{esc(item['ru'])}</i>", reply_markup=markup
    )


@router.message(DictationState.waiting, F.text)
async def on_dictation_answer(message: Message, state: FSMContext, content: Content, db: Storage) -> None:
    item = content.dictation_item((await state.get_data())["dictation"])
    result = compare_texts(item["text"], message.text)
    db.add_result(message.chat.id, "dictation", item["id"], result.score, 100)
    await state.set_state(None)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Следующая фраза", callback_data=DictCb(action="new", ref=item["level"]).pack())],
        [back_button("listening", "⬅️ Аудирование")],
    ])
    await message.answer(
        f"{format_comparison(result, '✍️ Вы написали')}\n🇷🇺 <i>{esc(item['ru'])}</i>", reply_markup=markup
    )


@router.message(DictationState.waiting, F.voice)
async def on_dictation_voice(message: Message) -> None:
    await message.answer("В диктанте нужно <b>написать</b> услышанную фразу текстом ✍️")


# ---------------------------------------------------------- texts + questions


@router.callback_query(ListenCb.filter(F.action == "text"))
async def on_text(
    callback: CallbackQuery, callback_data: ListenCb, state: FSMContext, content: Content, speech: SpeechService
) -> None:
    await callback.answer()
    item = content.comprehension_item(callback_data.ref)
    await send_speech(
        callback.message, speech, item["text"],
        caption=f"🎧 <b>{esc(item['title'])}</b> · {item['level']}\n<i>{esc(item['title_ru'])}</i>\n\n"
                "Прослушайте текст и ответьте на вопросы. Кнопка «🔊 Ещё раз» есть под каждым вопросом.",
    )
    await start_quiz(callback.message, state, content, "listening", item["id"])


@router.callback_query(ListenCb.filter(F.action.in_({"play", "slow"})))
async def on_replay(callback: CallbackQuery, callback_data: ListenCb, content: Content, speech: SpeechService) -> None:
    await callback.answer()
    item = content.comprehension_item(callback_data.ref)
    slow = callback_data.action == "slow"
    await send_speech(callback.message, speech, item["text"], slow=slow, caption="🐢 Медленно" if slow else "🔊 Ещё раз")
