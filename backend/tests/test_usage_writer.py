import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from server.database import Database
from server.usage_writer import UsageEvent, UsageWriter


def event(key_id=None, created_at='2026-10-10T09:00:00+00:00'):
    return UsageEvent(created_at, 'api_key' if key_id else 'playground', key_id, 'test', 37, 0, 25)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / 'usage.sqlite3')
    database.initialize()
    return database


def rows(db):
    with db.connect() as connection:
        return connection.execute('SELECT * FROM usage_events').fetchall()


def test_batches_coalesce_key_updates_and_reuse_connection(db, monkeypatch):
    with db.connect() as connection:
        connection.execute("INSERT INTO api_keys(id,name,digest,mask,created_at) VALUES (1,'test','hash','mask','now')")
    connections = []
    statements = []
    original = db.open_connection

    def open_connection():
        connection = original()
        connections.append(connection)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(db, 'open_connection', open_connection)
    writer = UsageWriter(db, batch_size=3, flush_interval=60)
    writer.start()
    # Out-of-order timestamps must not move last_used_at backwards.
    for stamp in ['09:00:02', '09:00:01', '09:00:03', '09:00:00']:
        assert writer.submit(event(1, f'2026-10-10T{stamp}+00:00'))
    writer.stop()
    assert not writer._thread.is_alive()
    assert len(connections) == 1
    assert sum(s == 'COMMIT' for s in statements) == 2
    assert sum(s.startswith('UPDATE api_keys') for s in statements) == 2
    assert len(rows(db)) == 4
    with db.connect() as connection:
        assert connection.execute('SELECT last_used_at FROM api_keys').fetchone()[0] == '2026-10-10T09:00:03+00:00'


def test_partial_batch_flushes_without_shutdown(db):
    writer = UsageWriter(db, flush_interval=0.02)
    writer.start()
    try:
        assert writer.submit(event())
        deadline = time.monotonic() + 3
        while not rows(db):
            assert time.monotonic() < deadline
            time.sleep(0.01)
    finally:
        writer.stop()
    assert len(rows(db)) == 1


def test_blocked_storage_bounds_queue_and_shutdown(db, monkeypatch, caplog):
    entered = threading.Event()
    release = threading.Event()

    def blocked_write(connection, batch):
        entered.set()
        assert release.wait(5)

    writer = UsageWriter(db, capacity=2, batch_size=1, shutdown_timeout=0.05)
    monkeypatch.setattr(writer, '_write_batch', blocked_write)
    writer.start()
    try:
        assert writer.submit(event())
        assert entered.wait(3)
        with ThreadPoolExecutor(max_workers=4) as pool:
            accepted = list(pool.map(lambda _: writer.submit(event()), range(20)))
        assert sum(accepted) == 2
        assert writer.dropped == 18
        writer.stop()
        assert writer._thread.is_alive()  # stop returned despite blocked I/O
        assert not writer.submit(event())
        with pytest.raises(RuntimeError, match='still running'):
            writer.start()
        assert 'shutdown timed out' in caplog.text
    finally:
        release.set()
        writer._thread.join(3)
    assert not writer._thread.is_alive()
    assert writer.dropped == 21  # 18 overflow, one after stop, two expired


def test_failed_transaction_rolls_back_and_later_batch_recovers(db, monkeypatch, caplog):
    failed = threading.Event()
    original = UsageWriter._write_batch
    attempts = 0

    def fail_first(connection, batch):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            try:
                with connection:
                    connection.execute("INSERT INTO usage_events(created_at,source,model,input_tokens,output_tokens,duration_ms) VALUES ('now','playground','test',1,0,1)")
                    raise sqlite3.OperationalError('simulated storage failure')
            finally:
                failed.set()
        original(connection, batch)

    writer = UsageWriter(db, batch_size=1)
    monkeypatch.setattr(writer, '_write_batch', fail_first)
    writer.start()
    try:
        writer.submit(event())
        assert failed.wait(3)
        writer.submit(event())
    finally:
        writer.stop()
    assert len(rows(db)) == 1
    assert writer.dropped == 1
    assert 'dropping batch' in caplog.text


def test_writer_can_restart_after_clean_shutdown(db):
    writer = UsageWriter(db)
    for _ in range(2):
        writer.start()
        assert writer.submit(event())
        writer.stop()
    assert len(rows(db)) == 2


def test_connection_failure_does_not_kill_worker(db, monkeypatch, caplog):
    original = db.open_connection
    failed = threading.Event()
    attempts = 0

    def fail_first_open():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            failed.set()
            raise sqlite3.OperationalError('database unavailable')
        return original()

    monkeypatch.setattr(db, 'open_connection', fail_first_open)
    writer = UsageWriter(db, batch_size=1)
    writer.start()
    try:
        writer.submit(event())
        assert failed.wait(3)
        writer.submit(event())
    finally:
        writer.stop()
    assert len(rows(db)) == 1
    assert writer.dropped == 1
    assert 'dropping batch' in caplog.text
