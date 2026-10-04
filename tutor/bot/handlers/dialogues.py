"""💬 Role-play dialogues answered by voice (or text)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...content import Content
from ...core.scoring import check_turn
from ...core.speech import SpeechService
from ..callbacks import DlgCb
from ..common import DialogueState, back_button, esc, send_speech, transcribe
from ..storage import Storage

router = Router(name="dialogues")


async def show_dialogues(message: Message, content: Content, db: Storage) -> None:
    best = db.best(message.chat.id, "dialogue")
    builder = InlineKeyboardBuilder()
    for d in content.dialogues:
        mark = " ✅" if d["id"] in best else ""
        builder.button(text=f"{d['title']} · {d['level']}{mark}", callback_data=DlgCb(action="start", id=d["id"]))
    builder.adjust(1)
    await message.answer(
        "💬 <b>Диалоги</b>\n\nРолевая игра: собеседник говорит, вы отвечаете <b>голосовым сообщением</b> "
        "(или текстом). Ответ засчитывается, если он подходит по смыслу. Перевод реплик спрятан под спойлером.",
        reply_markup=builder.as_markup(),
    )


def _turn_markup(dialogue_id: str, turn: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💡 Подсказка", callback_data=DlgCb(action="hint", id=dialogue_id, turn=turn).pack()),
        InlineKeyboardButton(text="⏭ Пропустить", callback_data=DlgCb(action="skip", id=dialogue_id, turn=turn).pack()),
        InlineKeyboardButton(text="✖️ Выход", callback_data=DlgCb(action="stop", id=dialogue_id, turn=turn).pack()),
    ]])


async def _say(message: Message, speech: SpeechService, dialogue: dict, line: str, ru: str, markup=None) -> None:
    caption = f"🧑 <b>{esc(dialogue['partner'])}:</b> {esc(line)}\n<tg-spoiler>{esc(ru)}</tg-spoiler>"
    await send_speech(message, speech, line, caption=caption, reply_markup=markup)


async def _send_turn(message: Message, speech: SpeechService, dialogue: dict, turn: int) -> None:
    t = dialogue["turns"][turn]
    await _say(message, speech, dialogue, t["line"], t["ru"], _turn_markup(dialogue["id"], turn))


async def _current(state: FSMContext, callback_data: DlgCb) -> dict | None:
    data = (await state.get_data()).get("dialogue")
    if await state.get_state() != DialogueState.active.state or not data:
        return None
    if data["id"] != callback_data.id or data["turn"] != callback_data.turn:
        return None
    return data


@router.callback_query(DlgCb.filter(F.action == "start"))
async def on_start(
    callback: CallbackQuery, callback_data: DlgCb, state: FSMContext, content: Content, speech: SpeechService
) -> None:
    await callback.answer()
    dialogue = content.dialogue(callback_data.id)
    await state.set_state(DialogueState.active)
    await state.update_data(dialogue={"id": dialogue["id"], "turn": 0, "attempts": 0, "first_try": 0, "skipped": 0})
    await callback.message.answer(
        f"<b>{esc(dialogue['title'])}</b> · {dialogue['level']}\n{esc(dialogue['description'])}\n\n"
        "🎤 Отвечайте голосовыми сообщениями. Можно и текстом, если неудобно говорить."
    )
    await _send_turn(callback.message, speech, dialogue, 0)


async def _advance(message: Message, state: FSMContext, content: Content, speech: SpeechService, db: Storage, data: dict) -> None:
    dialogue = content.dialogue(data["id"])
    data["turn"] += 1
    data["attempts"] = 0
    if data["turn"] < len(dialogue["turns"]):
        await state.update_data(dialogue=data)
        await _send_turn(message, speech, dialogue, data["turn"])
        return
    await state.clear()
    total = len(dialogue["turns"])
    db.add_result(message.chat.id, "dialogue", dialogue["id"], data["first_try"], total)
    await _say(message, speech, dialogue, dialogue["final"], dialogue["final_ru"])
    skipped = f", пропущено: {data['skipped']}" if data["skipped"] else ""
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔁 Ещё раз", callback_data=DlgCb(action="start", id=dialogue["id"]).pack()),
        back_button("dialogues", "💬 Другие диалоги"),
    ]])
    await message.answer(
        f"{'🏆' if data['first_try'] == total else '🎉'} <b>Диалог завершён!</b>\n"
        f"С первой попытки: {data['first_try']} из {total}{skipped}.",
        reply_markup=markup,
    )


async def _handle_reply(
    message: Message, text: str, state: FSMContext, content: Content, speech: SpeechService, db: Storage
) -> None:
    data = (await state.get_data())["dialogue"]
    turn = content.dialogue(data["id"])["turns"][data["turn"]]
    result = check_turn(turn, text)
    data["attempts"] += 1
    if result.accepted:
        if data["attempts"] == 1:
            data["first_try"] += 1
        await message.answer(result.feedback)
        await _advance(message, state, content, speech, db, data)
    else:
        await state.update_data(dialogue=data)
        await message.answer(f"🤔 {result.feedback}")


@router.message(DialogueState.active, F.voice | F.audio)
async def on_voice(
    message: Message, bot: Bot, state: FSMContext, content: Content, speech: SpeechService, db: Storage
) -> None:
    said = await transcribe(message, bot, speech)
    if said is None:
        return
    await message.answer(f"🗣 Вы: <i>{esc(said) or '—'}</i>")
    await _handle_reply(message, said, state, content, speech, db)


@router.message(DialogueState.active, F.text)
async def on_text(message: Message, state: FSMContext, content: Content, speech: SpeechService, db: Storage) -> None:
    await _handle_reply(message, message.text, state, content, speech, db)


@router.callback_query(DlgCb.filter(F.action == "hint"))
async def on_hint(callback: CallbackQuery, callback_data: DlgCb, state: FSMContext, content: Content, speech: SpeechService) -> None:
    if await _current(state, callback_data) is None:
        await callback.answer("Эта реплика уже пройдена")
        return
    await callback.answer()
    hint = content.dialogue(callback_data.id)["turns"][callback_data.turn]["hint"]
    await send_speech(callback.message, speech, hint, caption=f"💡 Например: <b>{esc(hint)}</b>\nПовторите голосом 🎤")


@router.callback_query(DlgCb.filter(F.action == "skip"))
async def on_skip(
    callback: CallbackQuery, callback_data: DlgCb, state: FSMContext, content: Content, speech: SpeechService, db: Storage
) -> None:
    data = await _current(state, callback_data)
    if data is None:
        await callback.answer("Эта реплика уже пройдена")
        return
    await callback.answer()
    hint = content.dialogue(callback_data.id)["turns"][callback_data.turn]["hint"]
    data["skipped"] += 1
    await callback.message.answer(f"⏭ Пропущено. Можно было ответить: <i>{esc(hint)}</i>")
    await _advance(callback.message, state, content, speech, db, data)


@router.callback_query(DlgCb.filter(F.action == "stop"))
async def on_stop(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Диалог завершён")
    await callback.message.answer("Диалог остановлен. Выберите раздел в меню 👇")
