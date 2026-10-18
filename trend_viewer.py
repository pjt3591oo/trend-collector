#!/usr/bin/env python3
"""Launch the local viewer: python trend_viewer.py --config config.toml."""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from src.viewer.repository import TrendRepository
from src.viewer.server import make_handler
from src.environment import load_application_config, resolve_settings
from src.drafts import DraftStore
from src.post_generation import OpenAICompatibleGenerator
from src.channels import build_channels


def main(argv=None):
    parser = argparse.ArgumentParser(description='저장된 트렌드 데이터의 로컬 조회 화면')
    parser.add_argument('--config', type=Path, default=Path('config.toml'))
    parser.add_argument('--database', type=Path, help='조회할 SQLite 파일; 설정의 output_dir보다 우선')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        settings = load_application_config(args.config, optional=True)
        database = args.database or Path(settings.get('collector', {}).get('output_dir', 'data')) / 'trends.sqlite3'
        if not 0 <= args.port <= 65535:
            parser.error('port must be 0..65535')
        publishing = settings.get('publishing', {})
        draft_store = DraftStore(Path(publishing.get('draft_database', str(database))))
        server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(TrendRepository(database),
            draft_store=draft_store, generator_factory=lambda: OpenAICompatibleGenerator(resolve_settings(publishing.get('llm', {}))),
            max_posts=publishing.get('max_posts', 3), journal=Path(publishing.get('journal', 'data/publications.sqlite3')),
            publishing_enabled=settings.get('channels', {}).get('threads', {}).get('enabled', False),
            channel_factory=lambda: build_channels(resolve_settings({'threads': settings.get('channels', {}).get('threads', {})}))))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f'Trend viewer: http://127.0.0.1:{server.server_port}', flush=True)
    print(f'Database: {database.resolve()} (collection read-only; drafts writable)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
