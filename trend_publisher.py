#!/usr/bin/env python3
"""Interactive analysis selection, LLM drafting and confirmed publishing."""
import argparse
import json
from pathlib import Path
import sqlite3
from src.channels import build_channels
from src.models import CollectionError
from src.post_generation import OpenAICompatibleGenerator, analysis_items
from src.publishing import publish_posts, publication_state, PublicationRepository
from src.environment import load_application_config, resolve_settings
from src.drafts import DraftStore, generate_draft
from src.analysis.repository import AnalysisRepository
from src.security import safe_error


def main(argv=None, *, ui=None,
         generator_factory=OpenAICompatibleGenerator, channel_factory=build_channels):
    parser = argparse.ArgumentParser(description='분석 선택 → LLM 초안 → 미리보기 → 게시 확인')
    parser.add_argument('--config', type=Path, default=Path('config.toml'))
    args = parser.parse_args(argv)
    if ui is None:
        from src.publisher_tui import PublisherTUI
        ui = PublisherTUI()
    try:
        config = load_application_config(args.config)
        settings = config.get('publishing', {})
        analysis_database = Path(settings.get('analysis_database', str(Path(
            config.get('collector', {}).get('output_dir', 'data')) / 'trends.sqlite3')))
        catalog = AnalysisRepository(analysis_database)
        reports = catalog.list()['rows']
        if not reports:
            raise ValueError(f'분석 보고서가 없습니다: {analysis_database}')
        selected_report = ui.select_report(reports)
        if selected_report is None:
            return 0
        report = catalog.list(str(selected_report))['report']
        if report is None:
            raise ValueError('분석 보고서를 찾을 수 없습니다.')
        database = Path(settings.get('draft_database', str(Path(
            config.get('collector', {}).get('output_dir', 'data')) / 'trends.sqlite3')))
        store = DraftStore(database)
        journal = Path(settings.get('journal', 'data/publications.sqlite3'))
        items = store.annotate(analysis_items(report), journal)
        if not items:
            raise ValueError('선택할 항목이 없습니다.')
        limit = settings.get('max_posts', 3)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError('max_posts must be 1..20')
        while True:
            selected = ui.select_items(items, limit, refresh=lambda: store.annotate(analysis_items(report), journal))
            if selected is None:
                return 0
            if selected and len(selected) <= limit:
                break
            ui.message('선택 확인', f'1개 이상, 최대 {limit}개를 선택하세요.')
        for index in selected:
            item = items[index]
            publication_repository = PublicationRepository(journal)
            snapshot = publication_repository.snapshot()
            drafts = [publication_repository.state(draft, snapshot) for draft in store.for_item(item)]
            choice = ui.choose_draft(item, drafts)
            if choice is None:
                continue
            if choice == 'new':
                generator = generator_factory(resolve_settings(settings.get('llm', {})))
                def generate(log):
                    log(f"원문 읽기 및 게시글 생성: {item['title']}\n")
                    return generate_draft(report, [index], generator, store, limit)
                draft = ui.work('원문 분석 · LLM 게시글 생성', generate)
                ui.message('초안 저장 완료', f"데이터베이스에 저장했습니다.\n초안 ID: {draft['draft_id']}")
            elif type(choice) is int and 0 <= choice < len(drafts):
                draft = drafts[choice]
            else:
                raise ValueError('초안 선택이 올바르지 않습니다.')
            state = publication_state(draft, journal)
            if not ui.preview(state):
                continue
            if state['publication_status'] == 'pending':
                recovery = ui.reconcile(state)
                if recovery is not None:
                    post_index, outcome, post_id = recovery
                    state = PublicationRepository(journal).reconcile(draft, post_index, outcome,
                        post_id=post_id, confirmed=True)
                    ui.message('발행 결과 저장', '계정에서 확인한 결과를 저장했습니다. 미발행 항목은 다시 선택해 발행할 수 있습니다.')
                continue
            if state['publication_status'] not in ('draft', 'failed'):
                ui.message('발행 상태', '발행 완료 또는 결과 미확인 초안입니다. 중복 발행하지 않습니다.')
                continue
            if not ui.confirm(len(draft['posts'])):
                continue
            channels = channel_factory(resolve_settings({'threads': config.get('channels', {}).get('threads', {})}))
            results = ui.work('Threads 게시 중', lambda log: publish_posts(draft, channels, journal))
            ui.message('게시 결과', '\n'.join(f'{name}: {status} ({identifier})'
                                             for name, status, identifier in results))
    except (EOFError, KeyboardInterrupt):
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, CollectionError) as exc:
        ui.message('작업 실패', safe_error(exc, locals().get('config')))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
