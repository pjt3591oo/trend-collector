"""SQLite persistence and file exports."""
from __future__ import annotations

from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
from typing import Any
from src.models import Item, now


def save_database(path: Path, run_id: str, rows: list[dict], statuses: dict, started: str):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, statuses_json TEXT
            );
            CREATE TABLE IF NOT EXISTS items (
                source TEXT, external_id TEXT, canonical_url TEXT, group_id TEXT,
                title TEXT, first_seen TEXT, last_seen TEXT, record_json TEXT,
                PRIMARY KEY(source, external_id)
            );
            CREATE TABLE IF NOT EXISTS observations (
                run_id TEXT, source TEXT, external_id TEXT, observed_at TEXT,
                metrics_json TEXT, record_json TEXT,
                PRIMARY KEY(run_id, source, external_id)
            );
            CREATE INDEX IF NOT EXISTS observations_item ON observations(source, external_id, observed_at);
            CREATE INDEX IF NOT EXISTS items_group ON items(group_id);
        ''')
        db.execute('INSERT INTO runs VALUES (?, ?, ?, ?)',
                   (run_id, started, now(), json.dumps(statuses, ensure_ascii=False)))
        for row in rows:
            encoded = json.dumps(row, ensure_ascii=False)
            db.execute('''INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, external_id) DO UPDATE SET
                canonical_url=excluded.canonical_url, group_id=excluded.group_id,
                title=excluded.title, last_seen=excluded.last_seen, record_json=excluded.record_json''',
                       (row['source'], row['external_id'], row['canonical_url'], row['group_id'], row['title'],
                        row['observed_at'], row['observed_at'], encoded))
            db.execute('INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)',
                       (run_id, row['source'], row['external_id'], row['observed_at'],
                        json.dumps(row['metrics'], ensure_ascii=False), encoded))


def csv_safe(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    # A leading apostrophe keeps spreadsheet applications from executing formulas.
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def save_exports(folder: Path, rows: list[dict], manifest: dict):
    folder.mkdir(parents=True, exist_ok=False)
    with (folder / 'items.jsonl').open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    fields = list(Item.__dataclass_fields__) + ['canonical_url', 'group_id']
    with (folder / 'items.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: csv_safe(v) for k, v in row.items()} for row in rows)
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
