"""Bounded, best-effort usage telemetry; never part of inference success."""
import logging
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass

from .database import Database

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageEvent:
    created_at: str
    source: str
    key_id: int | None
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class UsageWriter:
    def __init__(self, db: Database, *, capacity: int = 1000, batch_size: int = 100,
                 flush_interval: float = 1.0, shutdown_timeout: float = 5.0):
        if min(capacity, batch_size, flush_interval, shutdown_timeout) <= 0:
            raise ValueError("Usage writer limits must be positive")
        self.db = db
        self.capacity = capacity
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.shutdown_timeout = shutdown_timeout
        self._condition = threading.Condition()
        self._pending: deque[UsageEvent] = deque()
        self._thread: threading.Thread | None = None
        self._accepting = False
        self._deadline: float | None = None
        self.dropped = 0

    def start(self) -> None:
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Previous usage writer is still running")
            self._deadline = None
            self._accepting = True
            self._thread = threading.Thread(target=self._run, name="laya-usage-writer", daemon=True)
            self._thread.start()

    def submit(self, event: UsageEvent) -> bool:
        with self._condition:
            if not self._accepting or len(self._pending) >= self.capacity:
                self.dropped += 1
                # Avoid flooding logs when storage cannot keep up.
                if self.dropped == 1 or self.dropped & (self.dropped - 1) == 0:
                    logger.warning("Usage queue unavailable/full; dropped events=%d", self.dropped)
                return False
            self._pending.append(event)
            self._condition.notify()
            return True

    def stop(self) -> None:
        with self._condition:
            self._accepting = False
            self._deadline = time.monotonic() + self.shutdown_timeout
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(self.shutdown_timeout)
            if self._thread.is_alive():
                logger.warning("Usage shutdown timed out; unflushed statistics may be lost")

    def _next_batch(self) -> list[UsageEvent]:
        with self._condition:
            while not self._pending and self._accepting:
                self._condition.wait()
            flush_at = time.monotonic() + self.flush_interval
            while self._accepting and len(self._pending) < self.batch_size:
                remaining = flush_at - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            if self._deadline is not None and time.monotonic() >= self._deadline:
                self.dropped += len(self._pending)
                self._pending.clear()
            return [self._pending.popleft() for _ in range(min(self.batch_size, len(self._pending)))]

    @staticmethod
    def _write_batch(connection: sqlite3.Connection, batch: list[UsageEvent]) -> None:
        latest: dict[int, str] = {}
        for event in batch:
            if event.key_id is not None:
                latest[event.key_id] = max(latest.get(event.key_id, ""), event.created_at)
        with connection:
            connection.executemany(
                "INSERT INTO usage_events (created_at,source,key_id,model,input_tokens,output_tokens,duration_ms) "
                "VALUES (?,?,?,?,?,?,?)",
                [(e.created_at, e.source, e.key_id, e.model, e.input_tokens, e.output_tokens, e.duration_ms)
                 for e in batch],
            )
            connection.executemany(
                "UPDATE api_keys SET last_used_at=MAX(COALESCE(last_used_at,''),?) WHERE id=?",
                [(created_at, key_id) for key_id, created_at in latest.items()],
            )

    def _run(self) -> None:
        connection = None
        try:
            while batch := self._next_batch():
                try:
                    if connection is None:
                        connection = self.db.open_connection()
                    self._write_batch(connection, batch)
                except sqlite3.Error:
                    with self._condition:
                        self.dropped += len(batch)
                    logger.exception("Failed to persist %d usage events; dropping batch", len(batch))
                    # Do not retry an ambiguously committed batch and double-count it.
                    if connection is not None:
                        connection.close()
                        connection = None
        finally:
            with self._condition:
                self._accepting = False
                if self._pending:
                    self.dropped += len(self._pending)
                    logger.warning("Usage writer stopped; discarding %d pending events", len(self._pending))
                    self._pending.clear()
            if connection is not None:
                connection.close()
