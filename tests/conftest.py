from __future__ import annotations

import itertools
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.filters.callback_data import CallbackData
from aiogram.methods import EditMessageText, GetFile, SendMessage, SendVoice, TelegramMethod
from aiogram.types import CallbackQuery, Chat, File, InlineKeyboardMarkup, Message, Update, User, Voice

from tutor.bot.app import create_bot, create_dispatcher
from tutor.bot.storage import Storage
from tutor.config import Settings
from tutor.content import get_content
from tutor.core.speech import SpeechError


class FakeSpeech:
    """Stands in for SpeechService: no network, configurable results."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.transcript = ""
        self.fail_tts = False
        self.fail_stt = False
        self.synthesized: list[tuple[str, bool]] = []

    def synthesize(self, text: str, slow: bool = False) -> bytes:
        if self.fail_tts:
            raise SpeechError("no network")
        self.synthesized.append((text, slow))
        return b"ID3-fake-mp3"

    def transcribe(self, audio: bytes, suffix: str = "") -> str:
        if self.fail_stt:
            raise SpeechError("no network")
        return self.transcript

    async def asynthesize(self, text: str, slow: bool = False) -> bytes:
        return self.synthesize(text, slow)

    async def asynthesize_voice(self, text: str, slow: bool = False) -> tuple[bytes, str]:
        return self.synthesize(text, slow), "speech.ogg"

    async def atranscribe(self, audio: bytes, suffix: str = "") -> str:
        return self.transcribe(audio, suffix)


class MockedSession(BaseSession):
    """Records Telegram API calls and answers them with plausible objects."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        self._ids = itertools.count(1000)

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        self.requests.append(method)
        if method.__returning__ is bool:
            return True
        if isinstance(method, GetFile):
            return File(file_id=method.file_id, file_unique_id="u", file_path="voice/file.oga")
        message_id = next(self._ids)
        markup = getattr(method, "reply_markup", None)
        return Message(
            message_id=message_id,
            date=datetime.now(),
            chat=Chat(id=getattr(method, "chat_id", None) or 1, type="private"),
            text=getattr(method, "text", None),
            caption=getattr(method, "caption", None),
            voice=Voice(file_id=f"voice-{message_id}", file_unique_id=f"v{message_id}", duration=2)
            if isinstance(method, SendVoice) else None,
            reply_markup=markup if isinstance(markup, InlineKeyboardMarkup) else None,
        )

    async def stream_content(self, url: str, headers=None, timeout: int = 30, chunk_size: int = 65536,
                             raise_for_status: bool = True) -> AsyncGenerator[bytes, None]:
        yield b"OggS-fake-voice"

    async def close(self) -> None:
        pass


class BotHarness:
    """Feeds updates into the dispatcher as a user and collects the bot's replies."""

    def __init__(self, dp, bot: Bot, session: MockedSession, chat_id: int) -> None:
        self.dp, self.bot, self.session, self.chat_id = dp, bot, session, chat_id
        self._update_ids = itertools.count(1)
        self.user = User(id=chat_id, is_bot=False, first_name="Anna")
        self.chat = Chat(id=chat_id, type="private")

    async def _feed(self, **kwargs) -> list[TelegramMethod]:
        self.session.requests.clear()
        await self.dp.feed_update(self.bot, Update(update_id=next(self._update_ids), **kwargs))
        return list(self.session.requests)

    async def send(self, text: str) -> list[TelegramMethod]:
        message = Message(message_id=1, date=datetime.now(), chat=self.chat, from_user=self.user, text=text)
        return await self._feed(message=message)

    async def send_voice(self, duration: int = 3) -> list[TelegramMethod]:
        voice = Voice(file_id="user-voice", file_unique_id="uv", duration=duration)
        message = Message(message_id=1, date=datetime.now(), chat=self.chat, from_user=self.user, voice=voice)
        return await self._feed(message=message)

    async def click(self, data: CallbackData | str, message_text: str = "question") -> list[TelegramMethod]:
        packed = data.pack() if isinstance(data, CallbackData) else data
        message = Message(message_id=2, date=datetime.now(), chat=self.chat, text=message_text,
                          from_user=User(id=42, is_bot=True, first_name="Bot"))
        query = CallbackQuery(id="cb", from_user=self.user, chat_instance="ci", data=packed, message=message)
        return await self._feed(callback_query=query)


def texts(requests: list[TelegramMethod]) -> list[str]:
    out = []
    for r in requests:
        if isinstance(r, (SendMessage, EditMessageText)):
            out.append(r.text)
        elif isinstance(r, SendVoice):
            out.append(r.caption or "")
    return out


def joined(requests: list[TelegramMethod]) -> str:
    return "\n".join(texts(requests))


def buttons(requests: list[TelegramMethod]) -> list[tuple[str, str]]:
    found = []
    for r in requests:
        markup = getattr(r, "reply_markup", None)
        if isinstance(markup, InlineKeyboardMarkup):
            for row in markup.inline_keyboard:
                found.extend((b.text, b.callback_data) for b in row)
    return found


@pytest.fixture(scope="session")
def content():
    return get_content()


@pytest.fixture(scope="session")
def fake_speech() -> FakeSpeech:
    return FakeSpeech()


@pytest.fixture(scope="session")
def bot_env(content, fake_speech):
    # Routers are module-level singletons, so the dispatcher is built once per session;
    # every test uses its own chat id, which isolates FSM state and progress.
    db = Storage(":memory:")
    session = MockedSession()
    bot = create_bot("42:TEST")
    bot.session = session
    dp = create_dispatcher(content, fake_speech, db, Settings(site_url="https://example.com"))
    return dp, bot, session, db


_chat_ids = itertools.count(100)


@pytest.fixture
def tg(bot_env, fake_speech) -> BotHarness:
    fake_speech.reset()
    dp, bot, session, _db = bot_env
    return BotHarness(dp, bot, session, next(_chat_ids))


@pytest.fixture
def db(bot_env) -> Storage:
    return bot_env[3]
