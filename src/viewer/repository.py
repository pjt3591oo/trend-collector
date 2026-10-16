"""Read-only SQLite queries, independent of collection and HTTP serving."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


class TrendRepository:
    def __init__(self, database: Path):
        self.database = database.resolve()

    @contextmanager
    def connect(self):
        with_connection = sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True, timeout=5)
        with_connection.row_factory = sqlite3.Row
        try:
            yield with_connection
        finally:
            with_connection.close()

    def summary(self):
        if not self.database.is_file():
            return {'ready': False, 'items': 0, 'runs': 0, 'observations': 0, 'sources': [], 'latest_run': None}
        with self.connect() as db:
            counts = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                      for table in ('items', 'runs', 'observations')}
            sources = [dict(row) for row in db.execute(
                'SELECT source, COUNT(*) AS count, MAX(last_seen) AS last_seen FROM items GROUP BY source ORDER BY count DESC, source')]
            latest = db.execute('SELECT * FROM runs ORDER BY started_at DESC, run_id DESC LIMIT 1').fetchone()
        return {'ready': True, **counts, 'sources': sources, 'latest_run': self.run_record(latest) if latest else None}

    @staticmethod
    def run_record(row):
        result = dict(row)
        result['sources'] = json.loads(result.pop('statuses_json'))
        result['count'] = sum(s.get('count', 0) for s in result['sources'].values())
        return result

    def runs(self, page=1, page_size=20):
        if not self.database.is_file():
            return {'total': 0, 'rows': [], 'page': page, 'page_size': page_size}
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
            rows = db.execute('SELECT * FROM runs ORDER BY started_at DESC, run_id DESC LIMIT ? OFFSET ?',
                              (page_size, (page - 1) * page_size)).fetchall()
        return {'total': total, 'rows': [self.run_record(row) for row in rows], 'page': page, 'page_size': page_size}

    def items(self, *, query='', source='', run_id='', page=1, page_size=30):
        if not self.database.is_file():
            return {'total': 0, 'rows': [], 'page': page, 'page_size': page_size}
        table = 'observations' if run_id else 'items'
        clauses, params = [], []
        if run_id:
            clauses.append('run_id = ?')
            params.append(run_id)
        if source:
            clauses.append('source = ?')
            params.append(source)
        if query:
            # instr treats %, _, and SQL punctuation literally.
            clauses.append('instr(lower(record_json), lower(?)) > 0')
            params.append(query)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        order = 'observed_at' if run_id else 'last_seen'
        with self.connect() as db:
            total = db.execute(f'SELECT COUNT(*) FROM {table}{where}', params).fetchone()[0]
            rows = db.execute(f'SELECT record_json FROM {table}{where} ORDER BY {order} DESC, source, external_id LIMIT ? OFFSET ?',
                              [*params, page_size, (page - 1) * page_size]).fetchall()
        return {'total': total, 'rows': [json.loads(row[0]) for row in rows], 'page': page, 'page_size': page_size}

    def item(self, source, external_id, run_id=''):
        if not self.database.is_file():
            return None
        with self.connect() as db:
            if run_id:
                row = db.execute('SELECT record_json FROM observations WHERE source=? AND external_id=? AND run_id=?',
                                 (source, external_id, run_id)).fetchone()
            else:
                row = db.execute('SELECT record_json FROM items WHERE source=? AND external_id=?',
                                 (source, external_id)).fetchone()
            if row is None:
                return None
            history = db.execute('SELECT run_id, observed_at, metrics_json FROM observations WHERE source=? AND external_id=? '
                                 'ORDER BY observed_at DESC LIMIT 100', (source, external_id)).fetchall()
        return {'item': json.loads(row[0]), 'history': [
            {'run_id': h['run_id'], 'observed_at': h['observed_at'], 'metrics': json.loads(h['metrics_json'])}
            for h in history]}
