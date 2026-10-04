"""Routers in priority order: menu (works in any state) → exercises → fallback."""

from aiogram import Router

from . import dialogues, fallback, grammar, listening, menu, progress, quiz, speaking, tests


def routers() -> list[Router]:
    return [
        menu.router,
        quiz.router,
        tests.router,
        grammar.router,
        listening.router,
        speaking.router,
        dialogues.router,
        progress.router,
        fallback.router,
    ]
