"""Analyze a consistent SQLite snapshot in two adjacent equal windows."""
from contextlib import closing
from datetime import timedelta
import json
from pathlib import Path
import sqlite3

from . import VERSION
from .classification import CATEGORIES, classify_details, primary_for_group
from .grouping import DEFAULT_ENTITIES, groups
from .signals import changes, identity, latest, timestamp


def analyze(database: Path, *, end, window_hours=24, entities=None):
    if not database.is_file():
        raise ValueError('수집 데이터베이스가 없습니다. 먼저 수집해 주세요.')
    start = end - timedelta(hours=window_hours)
    baseline = start - timedelta(hours=window_hours)
    entities = {**DEFAULT_ENTITIES, **(entities or {})}
    for name, aliases in entities.items():
        if not isinstance(aliases, list) or not aliases or any(not isinstance(a, str) or not a.strip() for a in aliases):
            raise ValueError(f'analysis.entities.{name}: nonempty keyword list required')
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        observations = [json.loads(r[0]) for r in db.execute(
            'SELECT record_json FROM observations WHERE julianday(observed_at)>=julianday(?) '
            'AND julianday(observed_at)<julianday(?) ORDER BY julianday(observed_at),run_id', (baseline.isoformat(), end.isoformat()))]
        first_seen = {(r[0], r[1]): r[2] for r in db.execute(
            'SELECT source,external_id,MIN(julianday(observed_at)) FROM observations '
            'WHERE julianday(observed_at)<julianday(?) GROUP BY source,external_id', (end.isoformat(),))}
        start_jd = db.execute('SELECT julianday(?)', (start.isoformat(),)).fetchone()[0]
        runs = db.execute('SELECT started_at,statuses_json FROM runs WHERE julianday(started_at)<julianday(?)',
                          (end.isoformat(),)).fetchall()
    current_rows = [r for r in observations if timestamp(r['observed_at']) >= start]
    previous_rows = [r for r in observations if timestamp(r['observed_at']) < start]
    current, previous = latest(current_rows), latest(previous_rows)
    details = {key: classify_details(row) for key, row in current.items()}
    coverage = {'current': {}, 'baseline': {}}
    earliest = min((timestamp(r[0]) for r in runs), default=None)
    for date, statuses in runs:
        date = timestamp(date)
        period = 'current' if date >= start else 'baseline' if date >= baseline else None
        if period:
            for source, status in json.loads(statuses).items():
                counts = coverage[period].setdefault(source, {'ok': 0, 'other': 0})
                counts['ok' if status['status'] in ('ok', 'empty') else 'other'] += 1
    common = {s for s in coverage['current'] if coverage['current'][s]['ok']
              and not coverage['current'][s]['other'] and coverage['baseline'].get(s, {}).get('ok')
              and not coverage['baseline'][s]['other']}
    comparable = bool(previous and common and earliest and earliest <= baseline)
    buckets = {}
    for period, values in (('current', current), ('baseline', previous)):
        for key, row in values.items():
            for group_id, name, kind in groups(row, entities):
                bucket = buckets.setdefault(group_id, {'id': group_id, 'name': name, 'kind': kind, 'current': {}, 'baseline': {}})
                bucket[period][key] = row
    trends = []
    for bucket in buckets.values():
        if not bucket['current']:
            continue
        rows = list(bucket['current'].values())
        old = bucket['baseline']
        now_common = sum(r['source'] in common for r in rows)
        old_common = sum(r['source'] in common for r in old.values())
        delta = now_common - old_common if comparable else None
        sources = sorted({r['source'] for r in rows})
        is_new = all(first_seen[identity(row)] >= start_jd for row in rows) and not old
        # First sighting of items alone cannot prove that a named topic is new.
        group_details = [details[identity(row)] for row in rows]
        topics = sorted({topic for classification in group_details for topic in classification['category_reasons']})
        primary_category = primary_for_group(group_details)
        news_types = sorted({tag for classification in group_details for tag in classification['news_types']})
        evidence = [{'source': r['source'], 'external_id': r['external_id'], 'title': r['title'],
                     'url': r['url'], 'observed_at': r['observed_at'], 'metrics': r.get('metrics', {}),
                     'classification': details[identity(r)]} for r in rows]
        trends.append({'id': bucket['id'], 'name': bucket['name'], 'kind': bucket['kind'], 'topics': topics,
                       'primary_category': primary_category,
                       'related_categories': [category for category in topics if category != primary_category],
                       'news_types': news_types,
                       'items': len(rows), 'baseline_items': len(old), 'sources': sources,
                       'new_items_only': is_new, 'multi_source': len(sources) >= 2,
                       'comparable_item_delta': delta, 'increasing': delta is not None and delta > 0 and old_common > 0,
                       'evidence': evidence})
    trends.sort(key=lambda t: (-len(t['sources']), -t['items'], t['name']))
    topic_counts = {}
    category_counts = dict.fromkeys(CATEGORIES, 0)
    news_counts = {}
    classifications = []
    for key, row in current.items():
        classification = details[key]
        topics = classification['category_reasons']
        category_counts[classification['primary_category']] += 1
        for tag in classification['news_types']:
            news_counts[tag] = news_counts.get(tag, 0) + 1
        for topic in topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        classifications.append({'source': key[0], 'external_id': key[1], 'topics': topics, **classification,
                                'groups': [g[0] for g in groups(row, entities)]})
    return {'version': VERSION, 'window': {'start': start.isoformat(), 'end': end.isoformat(),
            'baseline_start': baseline.isoformat(), 'hours': window_hours},
            'summary': {'items': len(current), 'observations': len(current_rows), 'baseline_items': len(previous),
                        'new_items': sum(first_seen[key] >= start_jd for key in current),
                        'sources': len({key[0] for key in current}), 'topics': topic_counts,
                        'categories': category_counts, 'news_types': news_counts},
            'coverage': {**coverage, 'comparable': comparable, 'common_sources': sorted(common)},
            'trends': trends, 'metric_changes': changes(current_rows, previous), 'classifications': classifications,
            'rules': {'entities': entities},
            'notes': ['고유 항목은 (source, external_id) 기준입니다. 반복 관측을 추가 언급으로 세지 않습니다.',
                      '같은 CVE·URL·저장소는 연결하지만 재보도와 독립 검증을 구분하지는 않습니다.',
                      '이름 기반 묶음은 기업·제품 주제이며 동일 사건이라는 의미는 아닙니다.',
                      '신규는 수집 범위에서 항목이 처음 관측되었다는 의미이며 최초 공개를 뜻하지 않습니다.',
                      '증가량은 공통 수집 소스의 고유 항목 수 차이입니다. 수집 빈도·범위 변화의 영향을 받습니다.',
                      '이전 기간까지 관측 이력이 부족하면 증가 신호를 계산하지 않습니다.',
                      '대표 카테고리는 항목당 하나이며 카테고리별 항목 수의 합은 고유 항목 수와 같습니다.',
                      '관련 분야와 소식 성격은 여러 개일 수 있습니다. 묶음의 대표 분야는 근거 항목의 다수결로 정합니다.',
                      '동점은 보안→AI→데이터→개발→하드웨어→인프라→앱 순서로 결정합니다.']}
