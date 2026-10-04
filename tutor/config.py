"""Application settings read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    bot_token: str = ""
    web_host: str = "0.0.0.0"
    web_port: int = 8000
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    # Speech-to-text backend: "google" (free Google Web Speech API via SpeechRecognition)
    # or "whisper" (offline, requires `pip install faster-whisper`).
    stt_backend: str = "google"
    whisper_model: str = "base.en"
    # Accent of the gTTS voice: "com" (US), "co.uk" (UK), "com.au", "ca", ...
    tts_tld: str = "com"
    # Public URL of the website, shown by the bot (optional).
    site_url: str = ""
    # Bot username without @, shown on the website (optional).
    bot_username: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bot.sqlite3"

    @property
    def tts_cache_dir(self) -> Path:
        return self.data_dir / "tts_cache"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(PROJECT_ROOT / ".env")
        data_dir = _env("DATA_DIR")
        return cls(
            bot_token=_env("BOT_TOKEN"),
            web_host=_env("WEB_HOST", "0.0.0.0"),
            web_port=int(_env("WEB_PORT", "8000") or 8000),
            data_dir=Path(data_dir) if data_dir else PROJECT_ROOT / "data",
            stt_backend=_env("STT_BACKEND", "google").lower() or "google",
            whisper_model=_env("WHISPER_MODEL", "base.en"),
            tts_tld=_env("TTS_TLD", "com"),
            site_url=_env("SITE_URL"),
            bot_username=_env("BOT_USERNAME").lstrip("@"),
        )
