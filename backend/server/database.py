import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, csrf_digest TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    source TEXT NOT NULL, username TEXT NOT NULL,
                    attempted_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS login_attempts_time ON login_attempts(attempted_at);
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, digest TEXT NOT NULL UNIQUE,
                    mask TEXT NOT NULL, created_at TEXT NOT NULL, revoked_at TEXT,
                    last_used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    source TEXT NOT NULL, key_id INTEGER REFERENCES api_keys(id),
                    model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL, duration_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS usage_events_date ON usage_events(created_at);
            """)
