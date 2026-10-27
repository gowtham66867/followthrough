"""A lifetime request ceiling shared by every provider path and retry."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def reserve(config, body):
    budget = config.get('provider_budget')
    if not budget:
        return
    expires = datetime.fromisoformat(budget['expires_at'].replace('Z', '+00:00'))
    if expires.utcoffset() is None or datetime.now(timezone.utc) >= expires:
        raise ValueError('Judge inference access has expired')
    if body.get('model') not in budget['models']:
        raise ValueError('Model is outside the judge inference allowance')
    if body.get('max_tokens', 0) > budget['max_output_tokens']:
        raise ValueError('Response limit exceeds the judge inference allowance')
    if len(json.dumps(body, ensure_ascii=False).encode()) > budget['max_request_bytes']:
        raise ValueError('Request exceeds the judge inference allowance')
    path = Path(budget['ledger'])
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(path, timeout=15)) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS allowance (id INTEGER PRIMARY KEY CHECK(id=1), used INTEGER NOT NULL)')
        connection.execute('INSERT OR IGNORE INTO allowance VALUES (1, 0)')
        connection.commit()
        connection.execute('BEGIN IMMEDIATE')
        used = connection.execute('SELECT used FROM allowance WHERE id=1').fetchone()[0]
        if used >= budget['max_requests']:
            raise ValueError('Judge inference allowance exhausted; no automatic top-up')
        connection.execute('UPDATE allowance SET used=used+1 WHERE id=1')
        connection.commit()
    path.chmod(0o600)
