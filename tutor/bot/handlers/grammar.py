"""📘 Grammar lessons."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...content import Content
from ...core.render import split_message, theory_to_telegram
from ...core.speech import SpeechService
from ..callbacks import LessonCb, QuizCb
from ..common import back_button, esc, send_speech
from ..storage import PASS_PERCENT, Storage

router = Router(name="grammar")


async def show_grammar(message: Message, content: Content, db: Storage) -> None:
    best = db.best(message.chat.id, "grammar")
    builder = InlineKeyboardBuilder()
    for lesson in content.grammar:
        mark = " ✅" if best.get(lesson["id"], 0) >= PASS_PERCENT else ""
        builder.button(
            text=f"{lesson['level']} · {lesson['title']}{mark}",
            callback_data=LessonCb(action="open", id=lesson["id"]),
        )
    builder.adjust(1)
    await message.answer(
        "📘 <b>Грамматика</b>\n\nВыберите тему: объяснение на русском, примеры с озвучкой и упражнения. "
        f"Тема засчитывается при результате от {PASS_PERCENT}%.",
        reply_markup=builder.as_markup(),
    )


def lesson_text(lesson: dict) -> str:
    examples = "\n".join(f"• <b>{esc(e['en'])}</b> — <i>{esc(e['ru'])}</i>" for e in lesson["examples"])
    return (
        f"📘 <b>{esc(lesson['title'])}</b> · {lesson['level']}\n<i>{esc(lesson['title_ru'])}</i>\n\n"
        f"{theory_to_telegram(lesson['theory'])}\n\n<b>📌 Примеры</b>\n{examples}"
    )


@router.callback_query(LessonCb.filter(F.action == "open"))
async def on_open(callback: CallbackQuery, callback_data: LessonCb, content: Content) -> None:
    await callback.answer()
    lesson = content.lesson(callback_data.id)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✍️ Практика ({len(lesson['exercises'])})",
            callback_data=QuizCb(action="start", kind="grammar", ref=lesson["id"]).pack(),
        )],
        [InlineKeyboardButton(text="🔊 Озвучить примеры", callback_data=LessonCb(action="voice", id=lesson["id"]).pack())],
        [back_button("grammar", "⬅️ Все темы")],
    ])
    chunks = split_message(lesson_text(lesson))
    for i, chunk in enumerate(chunks):
        await callback.message.answer(chunk, reply_markup=markup if i == len(chunks) - 1 else None)


@router.callback_query(LessonCb.filter(F.action == "voice"))
async def on_voice(callback: CallbackQuery, callback_data: LessonCb, content: Content, speech: SpeechService) -> None:
    await callback.answer("Готовлю озвучку…")
    lesson = content.lesson(callback_data.id)
    text = " ".join(e["en"] for e in lesson["examples"])
    await send_speech(callback.message, speech, text, caption=f"🔊 Примеры: {esc(lesson['title'])}")
