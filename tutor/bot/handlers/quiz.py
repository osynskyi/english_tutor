"""Quiz engine shared by tests, grammar practice and listening comprehension."""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...content import Content
from ...core.scoring import CheckResult, check_answer
from ..callbacks import AnswerCb, ListenCb, QuizCb
from ..common import QuizState, back_button, esc, percent
from ..storage import PASS_PERCENT, Storage

router = Router(name="quiz")

LETTERS = "ABCDEF"
BACK = {
    "test": ("tests", "⬅️ К тестам"),
    "grammar": ("grammar", "⬅️ К темам"),
    "listening": ("listening", "⬅️ К аудированию"),
}


async def start_quiz(message: Message, state: FSMContext, content: Content, kind: str, ref: str) -> None:
    await state.set_state(QuizState.active)
    await state.update_data(quiz={"kind": kind, "ref": ref, "index": 0, "correct": 0, "mistakes": []})
    await send_question(message, state, content)


def _question_markup(quiz: dict[str, Any], question: dict[str, Any], short: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if question["type"] == "choice":
        for i, option in enumerate(question["options"]):
            text = option if short else LETTERS[i]
            builder.button(text=text, callback_data=AnswerCb(q=quiz["index"], o=i))
        builder.adjust(1 if short else len(question["options"]))
    extra = []
    if quiz["kind"] == "listening":
        extra.append(InlineKeyboardButton(text="🔊 Ещё раз", callback_data=ListenCb(action="play", ref=quiz["ref"]).pack()))
        extra.append(InlineKeyboardButton(text="🐢 Медленно", callback_data=ListenCb(action="slow", ref=quiz["ref"]).pack()))
    extra.append(InlineKeyboardButton(text="✖️ Выйти", callback_data=QuizCb(action="quit").pack()))
    builder.row(*extra)
    return builder.as_markup()


def _question_text(quiz: dict[str, Any], question: dict[str, Any], total: int, short: bool) -> str:
    text = f"<b>Вопрос {quiz['index'] + 1}/{total}</b>\n\n{esc(question['question'])}"
    if question["type"] == "choice" and not short:
        text += "\n\n" + "\n".join(f"<b>{LETTERS[i]}.</b> {esc(o)}" for i, o in enumerate(question["options"]))
    if question["type"] == "input":
        text += "\n\n✍️ <i>Напишите ответ сообщением.</i>"
    return text


async def send_question(message: Message, state: FSMContext, content: Content) -> None:
    quiz = (await state.get_data())["quiz"]
    questions = content.questions(quiz["kind"], quiz["ref"])
    question = questions[quiz["index"]]
    short = question["type"] == "choice" and all(len(o) <= 30 for o in question["options"])
    await message.answer(
        _question_text(quiz, question, len(questions), short),
        reply_markup=_question_markup(quiz, question, short),
    )


def _feedback(result: CheckResult) -> str:
    if result.correct:
        text = "✅ <b>Верно!</b>"
    else:
        text = f"❌ <b>Неверно.</b> Правильный ответ: <b>{esc(result.correct_answer)}</b>"
    if result.explanation:
        text += f"\n💡 {esc(result.explanation)}"
    return text


async def _advance(message: Message, state: FSMContext, content: Content, db: Storage, result: CheckResult) -> None:
    data = await state.get_data()
    quiz = data["quiz"]
    questions = content.questions(quiz["kind"], quiz["ref"])
    if result.correct:
        quiz["correct"] += 1
    else:
        quiz["mistakes"].append(
            {"question": questions[quiz["index"]]["question"], "given": result.given, "correct": result.correct_answer}
        )
    quiz["index"] += 1
    await state.update_data(quiz=quiz)
    if quiz["index"] < len(questions):
        await send_question(message, state, content)
    else:
        await _finish(message, state, content, db, quiz, len(questions))


async def _finish(message: Message, state: FSMContext, content: Content, db: Storage, quiz: dict, total: int) -> None:
    await state.clear()
    kind, ref, correct = quiz["kind"], quiz["ref"], quiz["correct"]
    user_id = message.chat.id
    db.add_result(user_id, kind, ref, correct, total)
    score = percent(correct, total)
    emoji = "🏆" if score >= 90 else "🎉" if score >= 70 else "👍" if score >= 50 else "💪"
    lines = [f"{emoji} <b>{esc(content.quiz_title(kind, ref))}: {correct} из {total} ({score}%)</b>"]
    if kind == "test":
        level = content.estimate_level(content.test(ref), correct)
        if level:
            lines.append(f"\n🎯 Ваш примерный уровень: <b>{level}</b>")
    if kind == "grammar":
        lines.append("\n✅ Тема изучена!" if score >= PASS_PERCENT else f"\nДля зачёта нужно от {PASS_PERCENT}%. Перечитайте теорию и попробуйте снова.")
    if quiz["mistakes"]:
        lines.append("\n<b>Работа над ошибками:</b>")
        for m in quiz["mistakes"][:10]:
            lines.append(f"• {esc(m['question'])}\n   <s>{esc(m['given'] or '—')}</s> → <b>{esc(m['correct'])}</b>")
    to, label = BACK[kind]
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔁 Ещё раз", callback_data=QuizCb(action="start", kind=kind, ref=ref).pack()),
        back_button(to, label),
    ]])
    await message.answer("\n".join(lines), reply_markup=markup)


@router.callback_query(QuizCb.filter(F.action == "start"))
async def on_start(callback: CallbackQuery, callback_data: QuizCb, state: FSMContext, content: Content) -> None:
    await callback.answer()
    await start_quiz(callback.message, state, content, callback_data.kind, callback_data.ref)


@router.callback_query(QuizCb.filter(F.action == "quit"))
async def on_quit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Тест прерван")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Хорошо, остановились. Выберите раздел в меню 👇")


@router.callback_query(QuizState.active, AnswerCb.filter())
async def on_answer(
    callback: CallbackQuery, callback_data: AnswerCb, state: FSMContext, content: Content, db: Storage
) -> None:
    quiz = (await state.get_data()).get("quiz")
    if not quiz or callback_data.q != quiz["index"]:
        await callback.answer("Этот вопрос уже закрыт")
        return
    question = content.questions(quiz["kind"], quiz["ref"])[quiz["index"]]
    result = check_answer(question, callback_data.o)
    await callback.answer("✅ Верно!" if result.correct else "❌ Неверно")
    original = callback.message.html_text or ""
    await callback.message.edit_text(
        f"{original}\n\nВаш ответ: <b>{esc(result.given)}</b>\n{_feedback(result)}", reply_markup=None
    )
    await _advance(callback.message, state, content, db, result)


@router.callback_query(AnswerCb.filter())
async def on_stale_answer(callback: CallbackQuery) -> None:
    await callback.answer("Этот тест уже завершён")


@router.message(QuizState.active, F.text)
async def on_text_answer(message: Message, state: FSMContext, content: Content, db: Storage) -> None:
    quiz = (await state.get_data())["quiz"]
    question = content.questions(quiz["kind"], quiz["ref"])[quiz["index"]]
    if question["type"] == "choice":
        await message.answer("Выберите вариант ответа кнопкой под вопросом 👆")
        return
    result = check_answer(question, message.text)
    await message.answer(_feedback(result))
    await _advance(message, state, content, db, result)
