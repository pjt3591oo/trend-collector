"""HTTP handlers and static assets for the local viewer."""
from src.publication_status import LABELS
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import sqlite3
import secrets
from threading import Lock
from src.drafts import generate_draft, query_drafts
from src.post_generation import analysis_items
from src.publishing import publish_posts, publication_state, PublicationRepository
from urllib.parse import parse_qs, urlsplit



STATIC = Path(__file__).parent / 'static'


def make_handler(repository, *, draft_store=None, generator_factory=None, max_posts=3,
                 channel_factory=None, journal=None, publishing_enabled=True):
    journal = Path(journal) if journal is not None else Path('data/publications.sqlite3')
    csrf_token = secrets.token_urlsafe(32)
    generating = Lock()
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, mime):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, data):
            self.send(status, json.dumps(data, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

        def do_GET(self):
            url = urlsplit(self.path)
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'),
                      '/drafts': ('drafts.html', 'text/html'), '/drafts.js': ('drafts.js', 'text/javascript')}
            if url.path in assets:
                file, mime = assets[url.path]
                self.send(200, (STATIC / file).read_bytes(), mime + '; charset=utf-8')
                return
            params = parse_qs(url.query)
            def value(key, default=''):
                return params.get(key, [default])[0]
            try:
                page = int(value('page', '1'))
                page_size = int(value('page_size', '30'))
                if page < 1 or not 1 <= page_size <= 100 or len(value('q')) > 500:
                    raise ValueError('Invalid pagination or search')
                if url.path == '/api/summary':
                    result = repository.summary()
                elif url.path == '/api/runs':
                    result = repository.runs(page, page_size)
                elif url.path == '/api/items':
                    result = repository.items(query=value('q'), source=value('source'), run_id=value('run'), page=page, page_size=page_size)
                elif url.path == '/api/item':
                    result = repository.item(value('source'), value('id'), value('run'))
                    if result is None:
                        self.json(404, {'error': '항목을 찾을 수 없습니다.'})
                        return
                elif url.path == '/api/analysis':
                    result = repository.analyses(value('id'))
                elif url.path == '/api/drafts':
                    result = query_drafts(draft_store, journal, page=page, page_size=page_size,
                        query=value('q'), category=value('category'), source=value('source'),
                        status=value('status')) if draft_store else {'rows': [], 'total': 0, 'categories': [], 'sources': []}
                elif url.path == '/api/draft':
                    draft = draft_store.get(value('id')) if draft_store else None
                    if draft is None:
                        self.json(404, {'error': '초안을 찾을 수 없습니다.'})
                        return
                    result = publication_state(draft, journal)
                elif url.path == '/api/draft-session':
                    result = {'token': csrf_token, 'status_labels': LABELS, 'max_posts': max_posts,
                              'publishing_enabled': bool(channel_factory and publishing_enabled)}
                elif url.path == '/api/draft-items':
                    report = repository.analyses(value('id'))['report']
                    items = analysis_items(report) if report else []
                    result = {'items': draft_store.annotate(items, journal) if draft_store else [
                        {**item, 'has_draft': None, 'draft_count': None} for item in items]}
                else:
                    self.json(404, {'error': '페이지를 찾을 수 없습니다.'})
                    return
                self.json(200, result)
            except ValueError:
                self.json(400, {'error': '조회 조건을 확인해 주세요.'})
            except (sqlite3.Error, OSError):
                self.json(503, {'error': '데이터베이스를 읽을 수 없습니다. 수집 결과 파일을 확인해 주세요.'})

        def do_POST(self):
            reconciling = urlsplit(self.path).path == '/api/drafts/reconcile'
            publishing = urlsplit(self.path).path == '/api/drafts/publish'
            if urlsplit(self.path).path not in ('/api/drafts', '/api/drafts/publish', '/api/drafts/reconcile'):
                self.json(404, {'error': '페이지를 찾을 수 없습니다.'})
                return
            host = self.headers.get('Host', '')
            port = self.server.server_address[1]
            allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
            if host not in allowed or self.headers.get('Origin') not in (None, f'http://{host}') or not secrets.compare_digest(
                    self.headers.get('X-Draft-Token', ''), csrf_token):
                self.json(403, {'error': '페이지를 새로고침한 후 다시 시도해 주세요.'})
                return
            if not draft_store or (not publishing and not reconciling and not generator_factory) or (publishing and not channel_factory):
                self.json(503, {'error': '초안 생성이 구성되지 않았습니다.'})
                return
            if not generating.acquire(blocking=False):
                self.json(409, {'error': '다른 초안을 생성 중입니다. 완료 후 다시 시도하세요.'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16000 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid request')
                request = json.loads(self.rfile.read(size))
                if reconciling:
                    draft = draft_store.get(request.get('draft_id'))
                    if draft is None:
                        raise ValueError('초안을 찾을 수 없습니다.')
                    result = PublicationRepository(journal).reconcile(draft, request.get('post_index'),
                        request.get('status'), post_id=request.get('post_id'), confirmed=request.get('confirmed'))
                    self.json(200, result)
                    return
                if publishing:
                    if request.get('confirmed') is not True:
                        raise ValueError('Confirmation required')
                    draft_id = request.get('draft_id')
                    if not isinstance(draft_id, str) or not draft_id:
                        raise ValueError('Draft ID required')
                    draft = draft_store.get(draft_id)
                    if draft is None:
                        self.json(404, {'error': '초안을 찾을 수 없습니다.'})
                        return
                    state = publication_state(draft, journal)
                    if state['publication_status'] not in ('draft', 'failed'):
                        self.json(409, {'error': '발행 이력이 있습니다. 발행 상태를 확인하세요.', 'draft': state})
                        return
                    channels = channel_factory()
                    if not channels:
                        self.json(503, {'error': 'Threads 채널이 비활성화되어 있습니다. config.toml의 channels.threads.enabled를 true로 설정한 뒤 뷰어를 재시작하세요.'})
                        return
                    try:
                        publish_posts(draft, channels, journal)
                    except ValueError:
                        self.json(409, {'error': '발행이 완료되지 않았습니다. 계정과 발행 상태를 확인하세요.',
                                        'draft': publication_state(draft, journal)})
                        return
                    self.json(200, publication_state(draft, journal))
                    return
                analysis_id = request.get('analysis_id')
                if not isinstance(analysis_id, str) or not analysis_id:
                    raise ValueError('분석을 선택하세요.')
                report = repository.analyses(analysis_id)['report']
                if report is None:
                    raise ValueError('분석을 찾을 수 없습니다.')
                result = generate_draft(report, request.get('selected'), generator_factory(), draft_store, max_posts)
                self.json(201, result)
            except (ValueError, TypeError, KeyError):
                self.json(400, {'error': '요청 내용을 확인하세요. 발행 요청에는 draft_id와 confirmed=true가 필요합니다.'
                    if publishing else '초안을 생성하지 못했습니다. 선택 항목, 원문 접근 및 LLM 설정을 확인하세요.'})
            except Exception:
                self.json(503, {'error': '원문 읽기, LLM 요청 또는 초안 저장에 실패했습니다. 다시 확인해 주세요.'})
            finally:
                generating.release()

        def log_message(self, fmt, *args):
            pass
    return Handler
