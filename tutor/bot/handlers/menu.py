"""/start, /help, main menu buttons and navigation. Works in any state."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ...config import Settings
from ...content import Content
from ..callbacks import NavCb
from ..common import MENU, esc, main_menu
from ..storage import Storage
from .dialogues import show_dialogues
from .grammar import show_grammar
from .listening import show_listening
from .progress import show_progress
from .speaking import show_speaking
from .tests import show_tests

router = Router(name="menu")

HELP = (
    "🎓 <b>English Tutor</b> — бот для самостоятельного изучения английского.\n\n"
    "📝 <b>Тесты</b> — тест на уровень и тематические тесты.\n"
    "📘 <b>Грамматика</b> — объяснения на русском, примеры с озвучкой, упражнения.\n"
    "🎧 <b>Аудирование</b> — диктанты и тексты с вопросами (голосовые сообщения).\n"
    "🗣 <b>Говорение</b> — повторяйте фразы и отвечайте на вопросы голосом, бот распознаёт речь.\n"
    "💬 <b>Диалоги</b> — ролевые разговоры: кафе, отель, врач, собеседование.\n"
    "📊 <b>Прогресс</b> — статистика и серия дней.\n\n"
    "🎙 В любой момент можно отправить голосовое сообщение на английском — я покажу, что услышал.\n\n"
    "Команды: /tests /grammar /listening /speaking /dialogues /progress /cancel"
)

SECTIONS = ("tests", "grammar", "listening", "speaking", "dialogues", "progress")


async def show_section(section: str, message: Message, content: Content, db: Storage) -> None:
    if section == "tests":
        await show_tests(message, content, db)
    elif section == "grammar":
        await show_grammar(message, content, db)
    elif section == "listening":
        await show_listening(message, content, db)
    elif section == "speaking":
        await show_speaking(message)
    elif section == "dialogues":
        await show_dialogues(message, content, db)
    elif section == "progress":
        await show_progress(message, content, db)
    else:
        await message.answer("Главное меню 👇", reply_markup=main_menu())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Storage, settings: Settings) -> None:
    await state.clear()
    user = message.from_user
    db.touch_user(message.chat.id, user.full_name if user else None)
    name = esc(user.first_name) if user else "друг"
    await message.answer(
        f"Hello, {name}! 👋\n\n"
        "Я помогу учить английский самостоятельно: тесты, грамматика, аудирование и разговорная практика "
        "с распознаванием речи.\n\nС чего начнём? Советую пройти <b>тест на уровень</b> в разделе 📝 Тесты.",
        reply_markup=main_menu(),
    )
    if settings.site_url:
        await message.answer(
            "🌐 Занимайтесь и на сайте — там те же упражнения:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть сайт", url=settings.site_url)]]),
        )


@router.message(Command("help"))
@router.message(F.text == MENU["help"])
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню 👇", reply_markup=main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Выберите раздел 👇", reply_markup=main_menu())


@router.message(Command(*SECTIONS))
async def cmd_section(message: Message, state: FSMContext, content: Content, db: Storage) -> None:
    await state.clear()
    section = message.text.split()[0].lstrip("/").split("@")[0]
    await show_section(section, message, content, db)


@router.message(F.text.in_({MENU[s] for s in SECTIONS}))
async def menu_button(message: Message, state: FSMContext, content: Content, db: Storage) -> None:
    await state.clear()
    section = next(s for s in SECTIONS if MENU[s] == message.text)
    await show_section(section, message, content, db)


@router.callback_query(NavCb.filter())
async def on_nav(callback: CallbackQuery, callback_data: NavCb, state: FSMContext, content: Content, db: Storage) -> None:
    await state.clear()
    await callback.answer()
    await show_section(callback_data.to, callback.message, content, db)
