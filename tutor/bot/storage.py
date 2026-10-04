"""SQLite storage for bot users' progress."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    ref TEXT NOT NULL,
    correct INTEGER NOT NULL,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS results_user ON results (user_id, kind);
"""

PASS_PERCENT = 70


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    """Kinds of results: test, grammar, listening, dictation, speaking, answer, dialogue."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def touch_user(self, user_id: int, name: str | None) -> None:
        now = _now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO users (id, name, created_at, last_seen) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, last_seen = excluded.last_seen",
                (user_id, name, now, now),
            )

    def add_result(self, user_id: int, kind: str, ref: str, correct: int, total: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO results (user_id, kind, ref, correct, total, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, kind, ref, correct, total, _now()),
            )

    def best(self, user_id: int, kind: str) -> dict[str, int]:
        """Best percentage per item of the given kind."""
        rows = self.conn.execute(
            "SELECT ref, MAX(100 * correct / total) AS best FROM results "
            "WHERE user_id = ? AND kind = ? AND total > 0 GROUP BY ref",
            (user_id, kind),
        ).fetchall()
        return {row["ref"]: int(row["best"]) for row in rows}

    def last(self, user_id: int, kind: str, ref: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM results WHERE user_id = ? AND kind = ? AND ref = ? ORDER BY id DESC LIMIT 1",
            (user_id, kind, ref),
        ).fetchone()

    def streak(self, user_id: int, today: date | None = None) -> tuple[int, int]:
        """(current streak of consecutive active days, total active days)."""
        rows = self.conn.execute(
            "SELECT DISTINCT substr(created_at, 1, 10) AS day FROM results WHERE user_id = ?", (user_id,)
        ).fetchall()
        days = {row["day"] for row in rows}
        day = today or datetime.now(timezone.utc).date()
        if day.isoformat() not in days:
            day -= timedelta(days=1)
        streak = 0
        while day.isoformat() in days:
            streak += 1
            day -= timedelta(days=1)
        return streak, len(days)

    def stats(self, user_id: int) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT kind, COUNT(*) AS n, AVG(100.0 * correct / total) AS avg FROM results "
            "WHERE user_id = ? AND total > 0 GROUP BY kind",
            (user_id,),
        ).fetchall()
        per_kind = {row["kind"]: {"count": row["n"], "avg": round(row["avg"])} for row in rows}
        streak, days = self.streak(user_id)
        return {
            "kinds": per_kind,
            "tests_best": self.best(user_id, "test"),
            "grammar_passed": [ref for ref, best in self.best(user_id, "grammar").items() if best >= PASS_PERCENT],
            "dialogues_done": list(self.best(user_id, "dialogue")),
            "streak": streak,
            "days": days,
        }

    def reset(self, user_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM results WHERE user_id = ?", (user_id,))
