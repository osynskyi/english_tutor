"""Callback data of inline buttons (must fit into 64 bytes)."""

from aiogram.filters.callback_data import CallbackData


class NavCb(CallbackData, prefix="nav"):
    to: str  # tests | grammar | listening | speaking | dialogues | progress | menu


class QuizCb(CallbackData, prefix="qz"):
    action: str  # start | quit
    kind: str = ""  # test | grammar | listening
    ref: str = ""


class AnswerCb(CallbackData, prefix="ans"):
    q: int  # question index (to ignore presses on old questions)
    o: int  # option index


class LessonCb(CallbackData, prefix="les"):
    action: str  # open | voice
    id: str


class DictCb(CallbackData, prefix="dic"):
    action: str  # new (ref = level) | slow | show (ref = item id)
    ref: str


class ListenCb(CallbackData, prefix="lis"):
    action: str  # text | play | slow
    ref: str


class SpeakCb(CallbackData, prefix="spk"):
    action: str  # topics | topic | play | slow | questions | question | qplay | sample
    ref: str = ""


class DlgCb(CallbackData, prefix="dlg"):
    action: str  # start | hint | skip | stop
    id: str
    turn: int = 0


class ProgressCb(CallbackData, prefix="prg"):
    action: str  # reset | confirm
