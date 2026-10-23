"""Transactions and persisted events for the single-owner local workspace."""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / 'followthrough.sqlite3'
        with closing(self.connect()) as connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise ValueError('Database is newer than this application')
            if version == 0:
                connection.executescript((Path(__file__).parent / 'migrations/001_initial.sql').read_text())
            if version < 2:
                connection.executescript((Path(__file__).parent / 'migrations/002_proposals.sql').read_text())
        self.path.chmod(0o600)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def query(self, sql, params=()):
        with closing(self.connect()) as connection:
            return [dict(row) for row in connection.execute(sql, params)]


def event(connection, kind, detail, opportunity_id=None, job_id=None):
    connection.execute('INSERT INTO events(opportunity_id,job_id,kind,detail_json,created_at) VALUES (?,?,?,?,?)',
                       (opportunity_id, job_id, kind, json.dumps(detail), now()))
