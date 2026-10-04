"""Telegram bot assembly and entry point."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from ..config import Settings
from ..content import Content, get_content
from ..core.speech import SpeechService, build_speech_service
from .handlers import routers
from .storage import Storage

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Начать / главное меню"),
    BotCommand(command="tests", description="📝 Тесты"),
    BotCommand(command="grammar", description="📘 Грамматика"),
    BotCommand(command="listening", description="🎧 Аудирование"),
    BotCommand(command="speaking", description="🗣 Говорение"),
    BotCommand(command="dialogues", description="💬 Диалоги"),
    BotCommand(command="progress", description="📊 Прогресс"),
    BotCommand(command="help", description="❓ Помощь"),
    BotCommand(command="cancel", description="Прервать упражнение"),
]


def create_dispatcher(content: Content, speech: SpeechService, db: Storage, settings: Settings) -> Dispatcher:
    """Handlers receive `content`, `speech`, `db` and `settings` as keyword arguments."""
    dp = Dispatcher(storage=MemoryStorage(), content=content, speech=speech, db=db, settings=settings)
    for router in routers():
        dp.include_router(router)
    return dp


def create_bot(token: str) -> Bot:
    return Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def run(settings: Settings) -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set. Get a token from @BotFather and put it into .env")
    bot = create_bot(settings.bot_token)
    db = Storage(settings.db_path)
    dp = create_dispatcher(get_content(), build_speech_service(settings), db, settings)

    async def on_startup() -> None:
        await bot.set_my_commands(COMMANDS)
        me = await bot.get_me()
        log.info("Bot @%s started", me.username)

    dp.startup.register(on_startup)
    try:
        await dp.start_polling(bot)
    finally:
        db.close()
        await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run(Settings.from_env()))
