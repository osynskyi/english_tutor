import shutil
import subprocess
import sys
import types
from datetime import date

import pytest

from tutor.bot.storage import Storage
from tutor.core.speech import SpeechError, SpeechService, TextToSpeech, convert_to_wav, to_ogg_opus

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


def _tone(fmt: str) -> bytes:
    """One second of a sine tone encoded by ffmpeg."""
    codec = {"ogg": ["-c:a", "libopus"], "mp3": ["-c:a", "libmp3lame"], "webm": ["-c:a", "libopus"]}[fmt]
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         *codec, "-f", fmt, "pipe:1"],
        capture_output=True, check=True,
    )
    return proc.stdout


@needs_ffmpeg
@pytest.mark.parametrize("fmt", ["ogg", "webm"])
def test_convert_to_wav(fmt):
    wav = convert_to_wav(_tone(fmt), f".{fmt}")
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert len(wav) > 16000  # ~1 s of 16 kHz 16-bit mono


@needs_ffmpeg
def test_convert_rejects_garbage():
    with pytest.raises(ValueError):
        convert_to_wav(b"definitely not audio", ".ogg")


def test_convert_rejects_empty():
    with pytest.raises(ValueError):
        convert_to_wav(b"")


@needs_ffmpeg
def test_to_ogg_opus():
    ogg = to_ogg_opus(_tone("mp3"))
    assert ogg[:4] == b"OggS"


def test_tts_cache(tmp_path, monkeypatch):
    calls = []

    class FakeGTTS:
        def __init__(self, text, lang, tld, slow):
            calls.append((text, slow))

        def write_to_fp(self, fp):
            fp.write(b"mp3-bytes")

    monkeypatch.setitem(sys.modules, "gtts", types.SimpleNamespace(gTTS=FakeGTTS))
    tts = TextToSpeech(tmp_path)
    assert tts.synthesize("Hello   world") == b"mp3-bytes"
    assert tts.synthesize("Hello world") == b"mp3-bytes"  # cached, whitespace-normalized
    assert tts.synthesize("Hello world", slow=True) == b"mp3-bytes"
    assert calls == [("Hello world", False), ("Hello world", True)]
    with pytest.raises(ValueError):
        tts.synthesize("   ")


def test_tts_error_is_speech_error(tmp_path, monkeypatch):
    class BrokenGTTS:
        def __init__(self, **kwargs):
            pass

        def write_to_fp(self, fp):
            raise ConnectionError("offline")

    monkeypatch.setitem(sys.modules, "gtts", types.SimpleNamespace(gTTS=BrokenGTTS))
    with pytest.raises(SpeechError):
        TextToSpeech(tmp_path).synthesize("Hello")


@needs_ffmpeg
def test_speech_service_transcribe_pipeline():
    class EchoRecognizer:
        def transcribe_wav(self, wav: bytes) -> str:
            assert wav[:4] == b"RIFF"
            return "hello"

    service = SpeechService(TextToSpeech(None), EchoRecognizer())
    assert service.transcribe(_tone("ogg"), ".ogg") == "hello"


# ------------------------------------------------------------------ storage


def test_storage_results_and_stats():
    db = Storage(":memory:")
    db.touch_user(1, "Anna")
    db.touch_user(1, "Anna K")
    db.add_result(1, "test", "placement", 12, 20)
    db.add_result(1, "test", "placement", 16, 20)
    db.add_result(1, "grammar", "to-be", 8, 8)
    db.add_result(1, "grammar", "articles", 3, 8)
    db.add_result(1, "dictation", "a1-1", 90, 100)
    db.add_result(2, "test", "tenses", 1, 15)

    assert db.best(1, "test") == {"placement": 80}
    stats = db.stats(1)
    assert stats["grammar_passed"] == ["to-be"]
    assert stats["kinds"]["test"] == {"count": 2, "avg": 70}
    assert stats["kinds"]["dictation"]["avg"] == 90
    assert stats["streak"] == 1 and stats["days"] == 1
    assert db.last(1, "test", "placement")["correct"] == 16

    db.reset(1)
    assert db.stats(1)["kinds"] == {}
    assert db.best(2, "test") == {"tenses": 6}


def test_storage_streak():
    db = Storage(":memory:")
    for day in ("2026-10-01", "2026-10-02", "2026-10-03", "2026-09-28"):
        db.conn.execute(
            "INSERT INTO results (user_id, kind, ref, correct, total, created_at) VALUES (1, 'test', 'x', 1, 1, ?)",
            (f"{day}T10:00:00+00:00",),
        )
    assert db.streak(1, today=date(2026, 10, 3)) == (3, 4)
    assert db.streak(1, today=date(2026, 10, 4)) == (3, 4)  # today not done yet, streak still alive
    assert db.streak(1, today=date(2026, 10, 6)) == (0, 4)


def test_storage_creates_directory(tmp_path):
    path = tmp_path / "nested" / "bot.sqlite3"
    Storage(path).close()
    assert path.is_file()
