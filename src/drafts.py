"""Persistent draft history shared by the terminal publisher and web viewer."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid
from src.post_generation import analysis_items


class DraftStore:
    def __init__(self, database):
        self.database = Path(database)
        self._migrate()

    def _migrate(self):
        if not self.database.exists():
            return
        with closing(sqlite3.connect(self.database, timeout=10)) as db, db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='social_drafts'").fetchone():
                return
            self._schema(db)
            rows = db.execute('SELECT draft_json FROM social_drafts d WHERE NOT EXISTS '
                              '(SELECT 1 FROM social_draft_posts p WHERE p.draft_id=d.draft_id)').fetchall()
            for (document,) in rows:
                self._index(db, json.loads(document))

    @staticmethod
    def _schema(db):
        db.execute('CREATE TABLE IF NOT EXISTS social_draft_posts ('
                   'draft_id TEXT, post_index INTEGER, source TEXT, url TEXT, category TEXT, '
                   'title TEXT, body TEXT, digest TEXT, PRIMARY KEY(draft_id,post_index))')
        db.execute('CREATE INDEX IF NOT EXISTS draft_posts_item ON social_draft_posts(source,url)')
        db.execute('CREATE INDEX IF NOT EXISTS draft_posts_filter ON social_draft_posts(category,source)')

    @staticmethod
    def _index(db, draft):
        from src.publications import post_digest
        for index, post in enumerate(draft['posts']):
            evidence = post.get('evidence', {})
            db.execute('INSERT OR IGNORE INTO social_draft_posts VALUES (?,?,?,?,?,?,?,?)',
                       (draft['draft_id'], index, evidence.get('source',''), evidence.get('url',''),
                        evidence.get('category',''), evidence.get('title',''), post['text'], post_digest(post['text'])))

    def save(self, draft):
        if not draft.get('posts') or any(not isinstance(p.get('text'), str) or
                not p['text'].strip() or len(p['text']) > 500 for p in draft['posts']):
            raise ValueError('초안 본문은 1..500자여야 합니다.')
        result = {**draft, 'draft_id': uuid.uuid4().hex,
                  'created_at': datetime.now(timezone.utc).isoformat()}
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database, timeout=10)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS social_drafts '
                       '(draft_id TEXT PRIMARY KEY, analysis_id TEXT, created_at TEXT, draft_json TEXT NOT NULL)')
            db.execute('INSERT INTO social_drafts VALUES (?,?,?,?)',
                (result['draft_id'], result.get('analysis_id'), result['created_at'],
                 json.dumps(result, ensure_ascii=False)))
            self._schema(db)
            self._index(db, result)
        return result

    def list(self, page=1, page_size=20):
        if not self.database.exists():
            return {'rows': [], 'total': 0}
        with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='social_drafts'").fetchone():
                return {'rows': [], 'total': 0}
            total = db.execute('SELECT COUNT(*) FROM social_drafts').fetchone()[0]
            rows = db.execute('SELECT draft_json FROM social_drafts ORDER BY created_at DESC LIMIT ? OFFSET ?',
                              (page_size, (page-1)*page_size)).fetchall()
        return {'rows': [json.loads(r[0]) for r in rows], 'total': total}

    def get(self, draft_id):
        if not self.database.exists():
            return None
        with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='social_drafts'").fetchone():
                return None
            row = db.execute('SELECT draft_json FROM social_drafts WHERE draft_id=?', (draft_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def for_item(self, item):
        if not self.database.exists():
            return []
        with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='social_draft_posts'").fetchone():
                return []
            rows = db.execute('SELECT d.draft_json,p.post_index FROM social_draft_posts p '
                              'JOIN social_drafts d USING(draft_id) WHERE p.source=? AND p.url=? '
                              'ORDER BY d.created_at DESC', (item.get('source'),item.get('url'))).fetchall()
        matches = []
        for document, index in rows:
            draft = json.loads(document)
            matches.append({**draft, 'posts': [draft['posts'][index]], 'post_indices': [index]})
        return matches

    def annotate(self, items, journal=None):
        """Match source + original URL across analyses, including existing JSON-backed rows."""
        status = {}
        published = set()
        if journal is not None:
            from src.publications import PublicationRepository
            published = {digest for digest, entry in PublicationRepository(journal).snapshot().items()
                         if entry[0] == 'published'}
        if self.database.exists():
            with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='social_drafts'").fetchone():
                    rows = db.execute('SELECT d.draft_id,d.created_at,p.source,p.url,p.digest '
                        'FROM social_drafts d JOIN social_draft_posts p USING(draft_id) '
                        'ORDER BY d.created_at DESC')
                    for draft_id, created_at, source, url, digest in rows:
                        if not source or not url:
                            continue
                        record = status.setdefault((source, url), {'ids': set(), 'published': set(),
                            'latest_draft_id': draft_id, 'draft_created_at': created_at})
                        record['ids'].add(draft_id)
                        if digest in published:
                            record['published'].add(digest)
        result = []
        for item in items:
            record = status.get((item.get('source'), item.get('url')), {})
            count = len(record.get('ids', ()))
            result.append({**item, 'has_draft': count > 0, 'draft_count': count,
                'published_count': len(record.get('published', ())),
                'latest_draft_id': record.get('latest_draft_id'),
                'draft_created_at': record.get('draft_created_at')})
        return result


def generate_draft(report, selected, generator, store, limit=3):
    items = analysis_items(report)
    if not isinstance(selected, list) or not 1 <= len(selected) <= limit:
        raise ValueError(f'1개 이상 {limit}개 이하의 서로 다른 항목을 선택하세요.')
    if any(type(i) is not int or i < 0 or i >= len(items) for i in selected):
        raise ValueError('선택 항목이 올바르지 않습니다.')
    if len(set(selected)) != len(selected):
        raise ValueError('중복 항목을 선택할 수 없습니다.')
    posts = [{'text': generator.generate(items[i]), 'evidence': items[i]} for i in selected]
    return store.save({'analysis_id': report.get('analysis_id'), 'posts': posts})


def query_drafts(store, journal, *, page=1, page_size=20, query='', category='', source='', status=''):
    from src.publications import PublicationRepository
    from src.publication_status import LABELS
    if status and status not in LABELS:
        raise ValueError('Invalid publication status')
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError('Invalid pagination')
    empty = {'rows': [], 'total': 0, 'categories': [], 'sources': []}
    if not store.database.exists():
        return empty
    repository = PublicationRepository(journal)
    snapshot = repository.snapshot()
    with closing(sqlite3.connect(store.database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='social_draft_posts'").fetchone():
            return empty
        # Connection-local snapshot: no per-draft journal connection and no writes to saved data.
        db.execute('CREATE TEMP TABLE publication_snapshot (digest TEXT PRIMARY KEY,status TEXT)')
        db.executemany('INSERT INTO publication_snapshot VALUES (?,?)', [(k,v[0]) for k,v in snapshot.items()])
        db.create_function('casefold', 1, lambda text: (text or '').casefold())
        cte = """WITH states AS (
            SELECT p.draft_id, CASE
              WHEN MIN(COALESCE(s.status,'draft')='published')=1 THEN 'published'
              WHEN MAX(COALESCE(s.status,'draft')='pending')=1 THEN 'pending'
              WHEN MAX(COALESCE(s.status,'draft')='published')=1 THEN 'partial'
              WHEN MAX(COALESCE(s.status,'draft')='failed')=1 THEN 'failed'
              ELSE 'draft' END AS state
            FROM social_draft_posts p LEFT JOIN publication_snapshot s ON p.digest=s.digest GROUP BY p.draft_id)
            """
        where = """FROM social_drafts d JOIN states t USING(draft_id)
            WHERE (?='' OR t.state=?) AND EXISTS (
              SELECT 1 FROM social_draft_posts p WHERE p.draft_id=d.draft_id
              AND (?='' OR p.category=?) AND (?='' OR p.source=?)
              AND (?='' OR instr(casefold(p.body || ' ' || p.title),casefold(?))>0))"""
        parameters = (status,status,category,category,source,source,query,query)
        total = db.execute(cte+'SELECT COUNT(*) '+where,parameters).fetchone()[0]
        rows = db.execute(cte+'SELECT d.draft_json '+where+' ORDER BY d.created_at DESC LIMIT ? OFFSET ?',
                          parameters+(page_size,(page-1)*page_size)).fetchall()
        categories = [r[0] for r in db.execute("SELECT DISTINCT category FROM social_draft_posts WHERE category!='' ORDER BY category")]
        sources = [r[0] for r in db.execute("SELECT DISTINCT source FROM social_draft_posts WHERE source!='' ORDER BY source")]
    return {'rows': [repository.state(json.loads(row[0]),snapshot) for row in rows], 'total': total,
            'categories': categories, 'sources': sources}
