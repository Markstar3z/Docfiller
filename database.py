"""SQLite database helpers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    status TEXT NOT NULL,
                    date TEXT NOT NULL,
                    answers_json TEXT NOT NULL,
                    screenshot_path TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS answer_cache (
                    question_text TEXT PRIMARY KEY,
                    answer_text TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_fields (
                    field_key TEXT PRIMARY KEY,
                    field_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def application_exists(self, url: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM applications WHERE url = ? LIMIT 1", (url,)).fetchone()
        return row is not None

    def save_application(
        self,
        *,
        url: str,
        title: str,
        status: str,
        answers: list[dict[str, Any]],
        screenshot_path: str | None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO applications (url, title, status, date, answers_json, screenshot_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (url, title, status, now, json.dumps(answers, ensure_ascii=False), screenshot_path),
            )
            return int(cur.lastrowid)

    def update_application_status(self, application_id: int, status: str, screenshot_path: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE applications SET status = ?, screenshot_path = COALESCE(?, screenshot_path) WHERE id = ?",
                (status, screenshot_path, application_id),
            )

    def update_application(
        self,
        application_id: int,
        *,
        status: str,
        answers: list[dict[str, Any]] | None = None,
        screenshot_path: str | None = None,
    ) -> None:
        """Update the one durable record for a form job."""
        with self.connect() as conn:
            if answers is None:
                conn.execute(
                    "UPDATE applications SET status = ?, screenshot_path = COALESCE(?, screenshot_path) WHERE id = ?",
                    (status, screenshot_path, application_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE applications
                    SET status = ?, answers_json = ?, screenshot_path = COALESCE(?, screenshot_path)
                    WHERE id = ?
                    """,
                    (status, json.dumps(answers, ensure_ascii=False), screenshot_path, application_id),
                )

    def list_recent(self, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, url, title, status, date FROM applications ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return rows

    def search_applications(self, query: str, limit: int = 25) -> list[sqlite3.Row]:
        like = f"%{query}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, url, title, status, date
                FROM applications
                WHERE url LIKE ? OR title LIKE ? OR answers_json LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        return rows

    def export_all(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, url, title, status, date, answers_json, screenshot_path FROM applications ORDER BY id DESC"
            ).fetchall()
        return rows

    def cache_answer(self, question_text: str, answer_text: str) -> None:
        now = datetime.utcnow().isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO answer_cache (question_text, answer_text, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(question_text) DO UPDATE SET
                    answer_text = excluded.answer_text,
                    updated_at = excluded.updated_at
                """,
                (question_text, answer_text, now),
            )

    def get_cached_answer(self, question_text: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT answer_text FROM answer_cache WHERE question_text = ?",
                (question_text,),
            ).fetchone()
        return row["answer_text"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        now = datetime.utcnow().isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def get_auto_submit(self) -> bool:
        return (self.get_setting("auto_submit", "off") or "off").lower() == "on"

    def set_auto_submit(self, value: bool) -> None:
        self.set_setting("auto_submit", "on" if value else "off")

    def get_profile_fields(self) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT field_key, field_value FROM profile_fields ORDER BY field_key").fetchall()
        return {r["field_key"]: r["field_value"] for r in rows}

    def set_profile_field(self, key: str, value: str) -> None:
        now = datetime.utcnow().isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO profile_fields (field_key, field_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(field_key) DO UPDATE SET
                    field_value = excluded.field_value,
                    updated_at = excluded.updated_at
                """,
                (key.strip().lower(), value.strip(), now),
            )
