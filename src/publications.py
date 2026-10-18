"""Publication identity, journal schema, transitions and batch state snapshots."""
from contextlib import closing, contextmanager
import hashlib
from pathlib import Path
import sqlite3

def post_digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class PublicationRepository:
    """Own journal reads and reuse one snapshot across a page or item list."""
    def __init__(self, journal):
        self.database = Path(journal)

    def reconcile(self, draft, post_index, status, *, post_id=None, confirmed=False):
        """Operator-confirmed recovery only. No provider calls and no automatic resend."""
        if confirmed is not True or status not in ('published', 'failed') or type(post_index) is not int:
            raise ValueError('계정 확인 후 발행 결과를 명시해 주세요.')
        indices = draft.get('post_indices', list(range(len(draft['posts']))))
        if post_index not in indices:
            raise ValueError('초안 항목을 확인해 주세요.')
        if status == 'published' and (not isinstance(post_id, str) or not post_id.isdigit()):
            raise ValueError('발행된 게시글의 숫자 ID가 필요합니다.')
        if not self.database.exists():
            raise ValueError('발행 이력이 없습니다.')
        digest = post_digest(draft['posts'][indices.index(post_index)]['text'])
        with self.connect() as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS publication_reconciliations ('
                       'channel TEXT,digest TEXT,previous_status TEXT,status TEXT,post_id TEXT,'
                       'created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
            changed = db.execute("UPDATE publications SET status=?,post_id=?,error=NULL "
                                 "WHERE channel='threads' AND digest=? AND status='pending'",
                                 (status, post_id if status == 'published' else None, digest)).rowcount
            if not changed:
                raise ValueError('결과 미확인 항목만 확인 처리할 수 있습니다.')
            db.execute('INSERT INTO publication_reconciliations '
                       '(channel,digest,previous_status,status,post_id) VALUES (?,?,?,?,?)',
                       ('threads',digest,'pending',status,post_id if status == 'published' else None))
        return self.state(draft)

    @contextmanager
    def connect(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database, timeout=10)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS publications (channel TEXT,digest TEXT,status TEXT,post_id TEXT,PRIMARY KEY(channel,digest))')
            db.execute('CREATE TABLE IF NOT EXISTS publication_links (draft_id TEXT,post_index INTEGER,channel TEXT,digest TEXT,PRIMARY KEY(draft_id,post_index,channel))')
            if 'error' not in {r[1] for r in db.execute('PRAGMA table_info(publications)')}:
                db.execute('ALTER TABLE publications ADD COLUMN error TEXT')
            db.execute('CREATE TABLE IF NOT EXISTS publication_attempts (channel TEXT,digest TEXT,status TEXT,post_id TEXT,error TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
            db.commit()
            yield db

    def claim(self, db, channel, digest, draft_id, index):
        with db:
            if draft_id:
                db.execute('INSERT OR IGNORE INTO publication_links VALUES (?,?,?,?)',(draft_id,index,channel,digest))
            inserted = db.execute("INSERT INTO publications (channel,digest,status,post_id,error) VALUES (?,?,'pending',NULL,NULL) "
                "ON CONFLICT(channel,digest) DO UPDATE SET status='pending',post_id=NULL,error=NULL WHERE publications.status='failed'",
                (channel,digest)).rowcount
            if inserted:
                db.execute('INSERT INTO publication_attempts (channel,digest,status) VALUES (?,?,?)',(channel,digest,'pending'))
        return bool(inserted)

    def finish(self, db, channel, digest, status, *, post_id=None, error=None):
        with db:
            db.execute('UPDATE publications SET status=?,post_id=?,error=? WHERE channel=? AND digest=?',
                       (status,post_id,error,channel,digest))
            db.execute('INSERT INTO publication_attempts (channel,digest,status,post_id,error) VALUES (?,?,?,?,?)',
                       (channel,digest,status,post_id,error))

    def snapshot(self, channel='threads'):
        if not self.database.exists():
            return {}
        with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='publications'").fetchone():
                return {}
            error = 'error' if 'error' in {r[1] for r in db.execute('PRAGMA table_info(publications)')} else 'NULL'
            return {r[0]: (r[1], r[2], r[3]) for r in db.execute(
                f'SELECT digest,status,post_id,{error} FROM publications WHERE channel=?', (channel,))}

    def state(self, draft, snapshot=None):
        snapshot = self.snapshot() if snapshot is None else snapshot
        return _state(draft, snapshot)


def publication_state(draft, journal):
    return PublicationRepository(journal).state(draft)


def _state(draft, snapshot):
    entries = []
    for index, post in enumerate(draft['posts']):
        digest = post_digest(post['text'])
        status, post_id, error = snapshot.get(digest, ('draft', None, None))
        entries.append({'post_index': draft.get('post_indices', list(range(len(draft['posts']))))[index], 'channel': 'threads', 'status': status, 'post_id': post_id,
                        'error': error})
    statuses = [entry['status'] for entry in entries]
    status = ('published' if statuses and all(s == 'published' for s in statuses) else
              'pending' if 'pending' in statuses else 'partial' if 'published' in statuses else 'failed' if 'failed' in statuses else 'draft')
    return {**draft, 'publication_status': status, 'published': status == 'published', 'publications': entries}

