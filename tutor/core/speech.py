"""Text-to-speech and speech-to-text used by the bot and the website's server fallback.

* TTS: gTTS (Google Translate voice), results cached on disk as MP3.
* STT: audio of any format is converted with ffmpeg to 16 kHz mono WAV, then
  recognized by the Google Web Speech API (SpeechRecognition package) or,
  offline, by faster-whisper.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

MAX_TTS_CHARS = 1000
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 90


class SpeechError(RuntimeError):
    """Speech service is unavailable (no network, missing dependency, ...)."""


class TextToSpeech:
    def __init__(self, cache_dir: Path, lang: str = "en", tld: str = "com") -> None:
        self.cache_dir = cache_dir
        self.lang = lang
        self.tld = tld

    def _cache_path(self, text: str, slow: bool) -> Path:
        key = hashlib.sha1(f"{self.lang}|{self.tld}|{int(slow)}|{text}".encode()).hexdigest()
        return self.cache_dir / f"{key}.mp3"

    def synthesize(self, text: str, slow: bool = False) -> bytes:
        text = " ".join(text.split())
        if not text:
            raise ValueError("Empty text")
        if len(text) > MAX_TTS_CHARS:
            raise ValueError(f"Text is longer than {MAX_TTS_CHARS} characters")
        path = self._cache_path(text, slow)
        if path.is_file():
            return path.read_bytes()
        try:
            from gtts import gTTS
        except ImportError as exc:  # pragma: no cover - dependency is in requirements
            raise SpeechError("gTTS is not installed") from exc
        buf = io.BytesIO()
        try:
            gTTS(text=text, lang=self.lang, tld=self.tld, slow=slow).write_to_fp(buf)
        except Exception as exc:  # gTTSError, network errors
            raise SpeechError(f"Text-to-speech failed: {exc}") from exc
        data = buf.getvalue()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return data


def convert_to_wav(audio: bytes, suffix: str = "") -> bytes:
    """Convert OGG/Opus, WebM, MP4/M4A, MP3, WAV... to 16 kHz mono 16-bit WAV."""
    if not audio:
        raise ValueError("Empty audio")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("Audio file is too large")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SpeechError("ffmpeg is not installed")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input{suffix or '.bin'}"
        dst = Path(tmp) / "output.wav"
        src.write_bytes(audio)
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src), "-t", str(MAX_AUDIO_SECONDS),
            "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(dst),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode != 0 or not dst.is_file():
            raise ValueError(f"Could not decode audio: {proc.stderr.decode(errors='ignore')[:200]}")
        return dst.read_bytes()


def to_ogg_opus(audio: bytes) -> bytes:
    """Convert audio (e.g. gTTS MP3) to OGG/Opus — the native Telegram voice format."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SpeechError("ffmpeg is not installed")
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-ac", "1", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1"],
        input=audio, capture_output=True, timeout=60,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise SpeechError(f"ffmpeg failed: {proc.stderr.decode(errors='ignore')[:200]}")
    return proc.stdout


class Recognizer(Protocol):
    def transcribe_wav(self, wav: bytes) -> str: ...


class GoogleRecognizer:
    """Free Google Web Speech API through the SpeechRecognition package."""

    def __init__(self, language: str = "en-US") -> None:
        self.language = language

    def transcribe_wav(self, wav: bytes) -> str:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(wav)) as source:
            audio = recognizer.record(source)
        try:
            return recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            raise SpeechError(f"Speech recognition service error: {exc}") from exc


class WhisperRecognizer:
    """Offline recognition with faster-whisper (`pip install faster-whisper`)."""

    def __init__(self, model_size: str = "base.en") -> None:
        self.model_size = model_size
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SpeechError("faster-whisper is not installed: pip install faster-whisper") from exc
            log.info("Loading Whisper model %s ...", self.model_size)
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe_wav(self, wav: bytes) -> str:
        model = self._load()
        segments, _info = model.transcribe(io.BytesIO(wav), language="en", beam_size=1)
        return " ".join(segment.text.strip() for segment in segments).strip()


class SpeechService:
    """Facade used by the web app and the bot. Blocking work runs in threads."""

    def __init__(self, tts: TextToSpeech, recognizer: Recognizer) -> None:
        self.tts = tts
        self.recognizer = recognizer

    def synthesize(self, text: str, slow: bool = False) -> bytes:
        return self.tts.synthesize(text, slow)

    def transcribe(self, audio: bytes, suffix: str = "") -> str:
        return self.recognizer.transcribe_wav(convert_to_wav(audio, suffix))

    async def asynthesize(self, text: str, slow: bool = False) -> bytes:
        return await asyncio.to_thread(self.synthesize, text, slow)

    async def asynthesize_voice(self, text: str, slow: bool = False) -> tuple[bytes, str]:
        """Speech for a Telegram voice message: (audio, filename). OGG/Opus if ffmpeg is available."""
        mp3 = await self.asynthesize(text, slow)
        try:
            return await asyncio.to_thread(to_ogg_opus, mp3), "speech.ogg"
        except SpeechError:
            return mp3, "speech.mp3"

    async def atranscribe(self, audio: bytes, suffix: str = "") -> str:
        return await asyncio.to_thread(self.transcribe, audio, suffix)


def build_speech_service(settings) -> SpeechService:
    tts = TextToSpeech(settings.tts_cache_dir, tld=settings.tts_tld)
    if settings.stt_backend == "whisper":
        recognizer: Recognizer = WhisperRecognizer(settings.whisper_model)
    else:
        recognizer = GoogleRecognizer()
    return SpeechService(tts, recognizer)
