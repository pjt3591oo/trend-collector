"""Evidence-linked Markdown reports and separately persisted analysis versions."""
from contextlib import closing
import html
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

from src.models import now


def markdown_text(value):
    return re.sub(r'([\\`*_\[\]])', r'\\\1', html.escape(str(value).replace('\n', ' ').replace('\r', ' ')))


def markdown_report(report):
    summary, window = report['summary'], report['window']
    lines = ['# IT 트렌드 관측 보고서', '', f"분석 버전: {report['version']}",
             f"관측 구간: {window['start']} ~ {window['end']} (끝 시각 제외)", '',
             f"- 고유 항목: {summary['items']}건 / 관측값: {summary['observations']}건",
             f"- 처음 관측한 항목: {summary['new_items']}건 / 출처: {summary['sources']}곳",
             f"- 이전 구간 고유 항목: {summary['baseline_items']}건", '', '## 대표 카테고리별 항목 수', '']
    lines += [f'- {topic}: {count}건' for topic, count in summary.get('categories', summary['topics']).items()]
    if not report['coverage']['comparable']:
        lines += ['', '> 비교 기간 데이터가 부족해 증가 신호를 계산하지 않았습니다.']
    sections = [(category, lambda t, category=category: t.get('primary_category') == category)
                for category in summary.get('categories', {})]
    sections += [('여러 출처에서 관측한 주제', lambda t: t['multi_source']),
                ('고유 항목이 증가한 주제', lambda t: t['increasing']),
                ('처음 관측한 항목으로 구성된 묶음', lambda t: t['new_items_only']),
                ('보안 동향', lambda t: any(topic in t['topics'] for topic in ('보안', '보안·개인정보')))]
    for title, predicate in sections:
        lines += ['', '## ' + title, '']
        trends = [t for t in report['trends'] if predicate(t)][:20]
        if not trends:
            lines.append('해당 조건의 관측 결과가 없습니다.')
        for trend in trends:
            if summary.get('categories') and title not in summary['categories']:
                lines.append(f"- {markdown_text(trend['name'])} · {trend['primary_category']} · "
                             f"고유 항목 {trend['items']}건 · 출처 {len(trend['sources'])}곳")
                continue
            lines += [f"### {markdown_text(trend['name'])}",
                      f"고유 항목 {trend['items']}건 · 출처 {len(trend['sources'])}곳 · 유형 {trend['kind']}"]
            if trend.get('news_types'):
                lines.append('소식 성격: ' + ' · '.join(trend['news_types']))
            for item in trend['evidence'][:10]:
                url = quote(item['url'], safe=':/?&=%#@+;,~')
                lines.append(f"- [{markdown_text(item['title'])}](<{url}>) — {item['source']}")
                metrics = item.get('metrics', {})
                if metrics.get('known_exploited') is True:
                    lines.append('  - CISA KEV: 실제 악용 확인 목록에 포함')
                for cve, score in metrics.get('epss', {}).items():
                    lines.append(f"  - {markdown_text(cve)} EPSS: {score.get('probability')} · 기준일 {score.get('date')}")
    lines += ['', '## 동일 항목의 관측 지표 변화', '']
    for item in report['metric_changes'][:30]:
        values = ', '.join(f"{key}: {v['before']} → {v['after']} ({v['delta']:+g})" for key, v in item['metrics'].items())
        lines.append(f"- {item['source']} · {markdown_text(item['title'])}: {values or '순위 변화만 관측'}")
    if not report['metric_changes']:
        lines.append('비교 가능한 지표 변화가 없습니다.')
    lines += ['', '## 해석 범위', ''] + ['- ' + note for note in report['notes']]
    return '\n'.join(lines) + '\n'


def save_analysis(database: Path, report: dict, analysis_id: str, output_dir: Path):
    report = {**report, 'analysis_id': analysis_id, 'created_at': now()}
    folder = output_dir / analysis_id
    if folder.exists():
        raise FileExistsError(folder)
    markdown = markdown_report(report)
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS analysis_runs (
                analysis_id TEXT PRIMARY KEY, created_at TEXT, window_start TEXT,
                window_end TEXT, version TEXT, report_json TEXT
            );
            CREATE TABLE IF NOT EXISTS analysis_members (
                analysis_id TEXT, source TEXT, external_id TEXT, topics_json TEXT, groups_json TEXT,
                classification_json TEXT,
                PRIMARY KEY(analysis_id, source, external_id)
            );
        ''')
        columns = {row[1] for row in db.execute('PRAGMA table_info(analysis_members)')}
        if 'classification_json' not in columns:
            db.execute('ALTER TABLE analysis_members ADD COLUMN classification_json TEXT')
        db.execute('INSERT INTO analysis_runs VALUES (?, ?, ?, ?, ?, ?)',
                   (analysis_id, report['created_at'], report['window']['start'], report['window']['end'],
                    report['version'], json.dumps(report, ensure_ascii=False)))
        db.executemany('INSERT INTO analysis_members '
                       '(analysis_id,source,external_id,topics_json,groups_json,classification_json) VALUES (?, ?, ?, ?, ?, ?)', [
            (analysis_id, row['source'], row['external_id'], json.dumps(row['topics'], ensure_ascii=False),
             json.dumps(row['groups'], ensure_ascii=False), json.dumps(row, ensure_ascii=False))
            for row in report['classifications']])
    try:
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (folder / 'report.md').write_text(markdown, encoding='utf-8')
    except OSError:
        raise OSError('분석은 DB에 저장했지만 보고서 파일을 내보내지 못했습니다. DB에서 조회할 수 있습니다.') from None
    return folder
