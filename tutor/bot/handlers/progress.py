"""📊 Progress."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ...content import Content
from ..callbacks import ProgressCb
from ..common import plural
from ..storage import Storage

router = Router(name="progress")


def progress_text(stats: dict, content: Content) -> str:
    kinds = stats["kinds"]

    def line(kind: str, label: str, unit: str = "точность") -> str:
        info = kinds.get(kind)
        if not info:
            return f"{label}: —"
        return f"{label}: {info['count']} · {unit} {info['avg']}%"

    streak = stats["streak"]
    lines = [
        "📊 <b>Ваш прогресс</b>",
        "",
        f"🔥 Серия: <b>{streak}</b> {plural(streak, 'день', 'дня', 'дней')} подряд · всего дней занятий: {stats['days']}",
        f"📝 Тесты: пройдено {len(stats['tests_best'])} из {len(content.tests)}"
        + (f" · средний результат {kinds['test']['avg']}%" if "test" in kinds else ""),
        f"📘 Грамматика: изучено тем {len(stats['grammar_passed'])} из {len(content.grammar)}",
        line("dictation", "✍️ Диктанты"),
        line("listening", "🎧 Тексты на слух", "верных ответов"),
        line("speaking", "🗣 Фразы вслух"),
        f"💬 Диалоги: пройдено {len(stats['dialogues_done'])} из {len(content.dialogues)}",
    ]
    placement = stats["tests_best"].get("placement")
    if placement is not None:
        test = content.test("placement")
        level = content.estimate_level(test, round(placement * len(test["questions"]) / 100))
        lines.append(f"\n🎯 Уровень по тесту: <b>{level}</b> (лучший результат {placement}%)")
    if not kinds:
        lines.append("\nВы ещё не занимались. Начните с теста на уровень: 📝 Тесты → «Тест на уровень».")
    return "\n".join(lines)


async def show_progress(message: Message, content: Content, db: Storage) -> None:
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Сбросить прогресс", callback_data=ProgressCb(action="reset").pack())
    ]])
    await message.answer(progress_text(db.stats(message.chat.id), content), reply_markup=markup)


@router.callback_query(ProgressCb.filter(F.action == "reset"))
async def on_reset(callback: CallbackQuery) -> None:
    await callback.answer()
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да, удалить всё", callback_data=ProgressCb(action="confirm").pack())
    ]])
    await callback.message.answer("Точно удалить весь прогресс? Это действие нельзя отменить.", reply_markup=markup)


@router.callback_query(ProgressCb.filter(F.action == "confirm"))
async def on_confirm(callback: CallbackQuery, db: Storage) -> None:
    db.reset(callback.message.chat.id)
    await callback.answer("Прогресс сброшен")
    await callback.message.edit_text("🗑 Прогресс удалён. Начнём сначала!")
