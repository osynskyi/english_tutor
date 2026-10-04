"""Shared bot helpers: menu, states, speech I/O and message formatting."""

from __future__ import annotations

import html
import logging

from aiogram import Bot
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from ..core.scoring import Comparison
from ..core.speech import MAX_AUDIO_SECONDS, SpeechError, SpeechService
from .callbacks import NavCb

log = logging.getLogger(__name__)


def esc(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return html.escape(text, quote=False)


MENU = {
    "tests": "📝 Тесты",
    "grammar": "📘 Грамматика",
    "listening": "🎧 Аудирование",
    "speaking": "🗣 Говорение",
    "dialogues": "💬 Диалоги",
    "progress": "📊 Прогресс",
    "help": "❓ Помощь",
}


class QuizState(StatesGroup):
    active = State()


class DictationState(StatesGroup):
    waiting = State()


class SpeakingState(StatesGroup):
    repeat = State()
    answer = State()


class DialogueState(StatesGroup):
    active = State()


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [MENU["tests"], MENU["grammar"]],
        [MENU["listening"], MENU["speaking"]],
        [MENU["dialogues"], MENU["progress"]],
        [MENU["help"]],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел или отправьте голосовое 🎤",
    )


def back_button(to: str, text: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=NavCb(to=to).pack())


# --------------------------------------------------------------------- speech

# Telegram file_id of already uploaded voices: re-sending by id is instant.
_voice_ids: dict[tuple[str, bool], str] = {}


async def send_speech(
    message: Message,
    speech: SpeechService,
    text: str,
    *,
    slow: bool = False,
    caption: str | None = None,
    reply_markup=None,
) -> Message | None:
    """Send `text` read aloud as a voice message (to the chat of `message`)."""
    key = (text, slow)
    if key in _voice_ids:
        try:
            return await message.answer_voice(_voice_ids[key], caption=caption, reply_markup=reply_markup)
        except Exception:  # file_id expired or belongs to another bot
            _voice_ids.pop(key, None)
    try:
        audio, filename = await speech.asynthesize_voice(text, slow)
    except (SpeechError, ValueError) as exc:
        log.warning("TTS failed: %s", exc)
        note = "🔇 <i>Озвучка сейчас недоступна, прочитайте текст.</i>"
        await message.answer(f"{caption}\n\n{note}" if caption else note, reply_markup=reply_markup)
        return None
    sent = await message.answer_voice(BufferedInputFile(audio, filename), caption=caption, reply_markup=reply_markup)
    if sent.voice:
        _voice_ids[key] = sent.voice.file_id
    return sent


async def transcribe(message: Message, bot: Bot, speech: SpeechService) -> str | None:
    """Recognize the voice/audio message. Returns None (after telling the user) on failure."""
    media = message.voice or message.audio
    if media is None:
        return None
    if media.duration and media.duration > MAX_AUDIO_SECONDS:
        await message.answer(f"Сообщение слишком длинное — запишите до {MAX_AUDIO_SECONDS} секунд.")
        return None
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        buffer = await bot.download(media)
        suffix = ".ogg" if message.voice else "." + (getattr(media, "file_name", "") or "audio.mp3").rsplit(".", 1)[-1]
        return await speech.atranscribe(buffer.read(), suffix)
    except SpeechError as exc:
        log.warning("STT failed: %s", exc)
        await message.answer("⚠️ Распознавание речи сейчас недоступно. Попробуйте чуть позже.")
    except ValueError as exc:
        log.warning("Bad audio: %s", exc)
        await message.answer("Не удалось обработать аудио. Попробуйте записать ещё раз.")
    return None


# ----------------------------------------------------------------- formatting


def score_bar(score: int) -> str:
    filled = round(score / 20)
    return "🟩" * filled + "⬜" * (5 - filled)


def format_comparison(result: Comparison, heard_label: str) -> str:
    marked = " ".join(esc(m.word) if m.ok else f"<u><b>{esc(m.word)}</b></u>" for m in result.marks)
    lines = [
        f"{score_bar(result.score)} <b>{result.score}%</b> — {result.verdict}",
        "",
        f"📖 Эталон: {marked}",
        f"{heard_label}: <i>{esc(result.heard) or '—'}</i>",
    ]
    if result.missing:
        lines.append(f"❗ Ошибки или пропуски: {esc(', '.join(result.missing))}")
    return "\n".join(lines)


def percent(correct: int, total: int) -> int:
    return round(100 * correct / total) if total else 0


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
