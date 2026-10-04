"""Messages outside of any exercise: free speaking practice and hints."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from ...core.scoring import count_words
from ...core.speech import SpeechService
from ..common import esc, main_menu, plural, transcribe
from ..storage import Storage

router = Router(name="fallback")


@router.message(F.voice | F.audio)
async def free_speech(message: Message, bot: Bot, speech: SpeechService, db: Storage) -> None:
    said = await transcribe(message, bot, speech)
    if said is None:
        return
    if not said:
        await message.answer("🤷 Не удалось разобрать речь. Попробуйте говорить чуть громче и чётче.")
        return
    words = count_words(said)
    db.add_result(message.chat.id, "free", "voice", 1, 1)
    await message.answer(
        f"🎙 Я услышал:\n<i>{esc(said)}</i>\n\n"
        f"{words} {plural(words, 'слово', 'слова', 'слов')}. Если текст совпадает с тем, что вы хотели сказать, — "
        "вас хорошо понятно! 👍\nДля упражнений выберите раздел 🗣 Говорение или 💬 Диалоги."
    )


@router.message()
async def unknown(message: Message) -> None:
    await message.answer(
        "Выберите раздел в меню 👇 или отправьте голосовое сообщение на английском — я покажу, что услышал.",
        reply_markup=main_menu(),
    )


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer("Эта кнопка больше не активна")
