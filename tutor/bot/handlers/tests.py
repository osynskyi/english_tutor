"""📝 Tests."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...content import Content
from ..callbacks import QuizCb
from ..common import esc, plural
from ..storage import Storage
from .quiz import start_quiz

router = Router(name="tests")


async def show_tests(message: Message, content: Content, db: Storage) -> None:
    best = db.best(message.chat.id, "test")
    builder = InlineKeyboardBuilder()
    for test in content.tests:
        mark = f" · {best[test['id']]}%" if test["id"] in best else ""
        builder.button(
            text=f"{test['title']} ({test['level']}){mark}",
            callback_data=QuizCb(action="intro", kind="test", ref=test["id"]),
        )
    builder.adjust(1)
    await message.answer(
        "📝 <b>Тесты</b>\n\nНачните с теста на уровень — он покажет, какие темы стоит повторить. "
        "Ответ выбирайте кнопкой или пишите сообщением.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(QuizCb.filter(F.action == "intro"))
async def on_intro(callback: CallbackQuery, callback_data: QuizCb, state: FSMContext, content: Content) -> None:
    await callback.answer()
    test = content.test(callback_data.ref)
    n = len(test["questions"])
    await callback.message.answer(
        f"📝 <b>{esc(test['title'])}</b> · {test['level']}\n{esc(test['description'])}\n\n"
        f"{n} {plural(n, 'вопрос', 'вопроса', 'вопросов')}. Поехали!"
    )
    await start_quiz(callback.message, state, content, "test", test["id"])
