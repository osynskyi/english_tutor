"""FastAPI application: JSON API + the single-page website."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import Settings
from ..content import Content, NotFound, get_content, public_question
from ..core.render import theory_to_html
from ..core.scoring import check_answer, check_free_answer, check_turn, compare_texts
from ..core.speech import MAX_AUDIO_BYTES, MAX_TTS_CHARS, SpeechError, SpeechService, build_speech_service

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


class AnswerIn(BaseModel):
    question_id: str
    answer: int | str


class TextIn(BaseModel):
    answer: str = Field(default="", max_length=2000)


class TurnIn(BaseModel):
    turn: int
    answer: str = Field(default="", max_length=2000)


class ScoreIn(BaseModel):
    expected: str = Field(max_length=2000)
    actual: str = Field(default="", max_length=2000)


def _find_question(questions: list[dict], question_id: str) -> dict:
    for question in questions:
        if question["id"] == question_id:
            return question
    raise HTTPException(404, f"Question '{question_id}' not found")


def create_app(
    content: Content | None = None,
    speech: SpeechService | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    content = content or get_content()
    speech = speech or build_speech_service(settings)

    app = FastAPI(title="English Tutor", version="1.0.0", docs_url="/api/docs", redoc_url=None)

    @app.exception_handler(NotFound)
    async def not_found_handler(_request: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc.args[0])}, status_code=404)

    # ------------------------------------------------------------------ meta

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/overview")
    def overview() -> dict:
        return {
            "grammar": len(content.grammar),
            "tests": len(content.tests),
            "dictation": len(content.dictation),
            "comprehension": len(content.comprehension),
            "phrases": len(content.phrases),
            "speaking_questions": len(content.speaking_questions),
            "dialogues": len(content.dialogues),
            "bot_url": f"https://t.me/{settings.bot_username}" if settings.bot_username else None,
        }

    # --------------------------------------------------------------- grammar

    @app.get("/api/grammar")
    def grammar_list() -> list[dict]:
        return [
            {
                "id": lesson["id"],
                "title": lesson["title"],
                "title_ru": lesson["title_ru"],
                "level": lesson["level"],
                "summary": lesson["summary"],
                "exercises": len(lesson["exercises"]),
            }
            for lesson in content.grammar
        ]

    @app.get("/api/grammar/{lesson_id}")
    def grammar_lesson(lesson_id: str) -> dict:
        lesson = content.lesson(lesson_id)
        return {
            "id": lesson["id"],
            "title": lesson["title"],
            "title_ru": lesson["title_ru"],
            "level": lesson["level"],
            "summary": lesson["summary"],
            "theory_html": theory_to_html(lesson["theory"]),
            "examples": lesson["examples"],
            "exercises": [public_question(q) for q in lesson["exercises"]],
        }

    @app.post("/api/grammar/{lesson_id}/check")
    def grammar_check(lesson_id: str, body: AnswerIn) -> dict:
        question = _find_question(content.lesson(lesson_id)["exercises"], body.question_id)
        return check_answer(question, body.answer).to_dict()

    # ----------------------------------------------------------------- tests

    @app.get("/api/tests")
    def tests_list() -> list[dict]:
        return [
            {
                "id": test["id"],
                "title": test["title"],
                "description": test["description"],
                "level": test["level"],
                "questions": len(test["questions"]),
            }
            for test in content.tests
        ]

    @app.get("/api/tests/{test_id}")
    def test_detail(test_id: str) -> dict:
        test = content.test(test_id)
        return {
            "id": test["id"],
            "title": test["title"],
            "description": test["description"],
            "level": test["level"],
            "grading": test.get("grading", []),
            "questions": [public_question(q) for q in test["questions"]],
        }

    @app.post("/api/tests/{test_id}/check")
    def test_check(test_id: str, body: AnswerIn) -> dict:
        question = _find_question(content.test(test_id)["questions"], body.question_id)
        return check_answer(question, body.answer).to_dict()

    # ------------------------------------------------------------- listening

    @app.get("/api/listening")
    def listening() -> dict:
        # The text is needed by the browser to synthesize speech locally;
        # the page keeps it hidden until the learner has answered.
        return {
            "dictation": content.dictation,
            "comprehension": [
                {**{k: v for k, v in item.items() if k != "questions"},
                 "questions": [public_question(q) for q in item["questions"]]}
                for item in content.comprehension
            ],
        }

    @app.post("/api/listening/dictation/{item_id}/check")
    def dictation_check(item_id: str, body: TextIn) -> dict:
        item = content.dictation_item(item_id)
        result = compare_texts(item["text"], body.answer).to_dict()
        result.update(text=item["text"], ru=item["ru"])
        return result

    @app.post("/api/listening/comprehension/{item_id}/check")
    def comprehension_check(item_id: str, body: AnswerIn) -> dict:
        question = _find_question(content.comprehension_item(item_id)["questions"], body.question_id)
        return check_answer(question, body.answer).to_dict()

    # -------------------------------------------------------------- speaking

    @app.get("/api/speaking")
    def speaking() -> dict:
        return {
            "topics": content.speaking_topics,
            "phrases": content.phrases,
            "questions": content.speaking_questions,
        }

    @app.post("/api/score")
    def score(body: ScoreIn) -> dict:
        """Compare what was said / typed with a reference sentence."""
        return compare_texts(body.expected, body.actual).to_dict()

    @app.post("/api/speaking/questions/{question_id}/check")
    def speaking_question_check(question_id: str, body: TextIn) -> dict:
        return check_free_answer(content.speaking_question(question_id), body.answer).to_dict()

    # ------------------------------------------------------------- dialogues

    @app.get("/api/dialogues")
    def dialogues_list() -> list[dict]:
        return [
            {k: d[k] for k in ("id", "title", "level", "partner", "description")} | {"turns": len(d["turns"])}
            for d in content.dialogues
        ]

    @app.get("/api/dialogues/{dialogue_id}")
    def dialogue_detail(dialogue_id: str) -> dict:
        return content.dialogue(dialogue_id)

    @app.post("/api/dialogues/{dialogue_id}/check")
    def dialogue_check(dialogue_id: str, body: TurnIn) -> dict:
        turns = content.dialogue(dialogue_id)["turns"]
        if not 0 <= body.turn < len(turns):
            raise HTTPException(404, "Turn not found")
        return check_turn(turns[body.turn], body.answer).to_dict()

    # ---------------------------------------------------------------- speech

    @app.get("/api/tts")
    async def tts(
        text: str = Query(..., min_length=1, max_length=MAX_TTS_CHARS),
        slow: bool = False,
    ) -> Response:
        try:
            audio = await speech.asynthesize(text, slow)
        except SpeechError as exc:
            log.warning("TTS unavailable: %s", exc)
            raise HTTPException(503, "Озвучка на сервере сейчас недоступна") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=604800"})

    @app.post("/api/stt")
    async def stt(audio: Annotated[UploadFile, File()]) -> dict:
        data = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Аудиофайл слишком большой")
        suffix = Path(audio.filename or "").suffix or _suffix_for(audio.content_type or "")
        try:
            text = await speech.atranscribe(data, suffix)
        except SpeechError as exc:
            log.warning("STT unavailable: %s", exc)
            raise HTTPException(503, "Распознавание речи на сервере сейчас недоступно") from exc
        except ValueError as exc:
            raise HTTPException(400, f"Не удалось обработать аудио: {exc}") from exc
        return {"text": text}

    # --------------------------------------------------------------- website

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def _suffix_for(content_type: str) -> str:
    content_type = content_type.split(";")[0].strip().lower()
    return {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
    }.get(content_type, "")
