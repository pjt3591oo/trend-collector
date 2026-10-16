"""HTTP handlers and static assets for the local viewer."""
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit



STATIC = Path(__file__).parent / 'static'


def make_handler(repository):
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
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
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
                else:
                    self.json(404, {'error': '페이지를 찾을 수 없습니다.'})
                    return
                self.json(200, result)
            except ValueError:
                self.json(400, {'error': '조회 조건을 확인해 주세요.'})
            except (sqlite3.Error, OSError):
                self.json(503, {'error': '데이터베이스를 읽을 수 없습니다. 수집 결과 파일을 확인해 주세요.'})

        def log_message(self, fmt, *args):
            pass
    return Handler
