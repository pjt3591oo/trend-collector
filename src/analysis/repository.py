"""One read-only analysis catalog for browser and terminal clients."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


class AnalysisRepository:
    def __init__(self, database):
        self.database = Path(database)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def list(self, analysis_id=''):
        if not self.database.is_file():
            return {'rows': [], 'report': None}
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='analysis_runs'").fetchone():
                return {'rows': [], 'report': None}
            rows = [dict(row) for row in db.execute(
                'SELECT analysis_id,created_at,window_start,window_end,version FROM analysis_runs ORDER BY created_at DESC LIMIT 100')]
            if analysis_id:
                record = db.execute('SELECT report_json FROM analysis_runs WHERE analysis_id=?', (analysis_id,)).fetchone()
            else:
                record = db.execute('SELECT report_json FROM analysis_runs ORDER BY created_at DESC LIMIT 1').fetchone()
        return {'rows': rows, 'report': json.loads(record[0]) if record else None}
