#!/usr/bin/env python3
"""Trend collector. Python 3.11+, standard library only.

Run: python trend_collector.py --config config.toml
No article-body crawling or automatic posting. Credentials stay in environment variables.
"""
from __future__ import annotations

import argparse
import tomllib
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
from pathlib import Path
from datetime import datetime
import uuid
import time

# Legacy names remain available; new integrations use src modules.
from src.collector_compat import (
    UTC, CollectionError, Skipped, now, digest, iso_date, canonical_url, Item, Node, Document, text, plain, number, xml_text, SafeRedirect, HTTP, save_database, csv_safe, save_exports, parse_geeknews, geeknews, parse_producthunt, producthunt, hackernews, reddit, parse_github, github, parse_google, google_trends, parse_indiehackers, indiehackers, parse_disquiet, disquiet, huggingface, COLLECTORS, SOURCES
)
from src.sources import CollectionRequest, HTTPClient, Source, create_sources
from src.enrichment import Enricher, EPSSEnricher
from src.collection import collect_source
from src.config_display import print_config
from src.environment import load_config


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError('must be positive')
    return parsed


def main(argv=None, *, sources: Mapping[str, Source] | None = None,
         http: HTTPClient | None = None, enricher: Enricher | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='TOML configuration file')
    parser.add_argument('--limit', type=positive_int, help='Maximum items per source (not per subreddit)')
    parser.add_argument('--days', type=positive_int, help='Legacy option; HTML sources collect current listings and ignore days')
    parser.add_argument('--out', type=Path, help='Output directory, default: ./data')
    parser.add_argument('--strict', action='store_true', help='Exit 1 if any source fails/is skipped or enrichment fails')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config, sections=('collector', 'sources', 'enrichment'))
        settings = config.get('collector', {})
        source_cfg = config.get('sources', {})
        available = tuple(sources) if sources is not None else SOURCES
        unknown = set(source_cfg) - (set(available) | set(SOURCES))
        if unknown:
            parser.error('Unknown sources in config: ' + ', '.join(sorted(unknown)))
        for name, options in source_cfg.items():
            if not isinstance(options, dict) or not isinstance(options.get('enabled', True), bool):
                parser.error(f'sources.{name}.enabled must be a boolean')
        selected = [name for name in available
                    if (not args.config or name in source_cfg)
                    and source_cfg.get(name, {}).get('enabled', True)]
        if not selected:
            parser.error('No enabled sources; enable a source in the configuration file')
        limit = args.limit if args.limit is not None else int(settings.get('limit', 20))
        days = args.days if args.days is not None else int(settings.get('days', 7))
        if not 1 <= limit <= 500 or not 1 <= days <= 365:
            parser.error('limit must be 1..500, days must be 1..365')
        request = CollectionRequest(limit, days)
        max_workers = settings.get('max_workers', 4)
        if type(max_workers) is not int or not 1 <= max_workers <= 32:
            parser.error('collector.max_workers must be an integer in 1..32')
        epss_enabled = config.get('enrichment', {}).get('epss', {}).get('enabled', False)
        if http is None and (sources is None or (epss_enabled and enricher is None)):
            http = HTTP(settings)
        if sources is None:
            sources = create_sources(http, source_cfg)
        if enricher is None and epss_enabled:
            enricher = EPSSEnricher(http)
        if any(source.name != name for name, source in sources.items()):
            parser.error('Source registry keys must match source.name')
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))
    out = args.out or Path(settings.get('output_dir', 'data'))
    print_config({
        **config,
        'config_file': str(args.config.resolve()) if args.config else None,
        'collector': {
            'timeout': 20, 'retries': 2, 'request_interval': 1.0,
            'user_agent': 'TrendCollector/1.0 (personal trend research)',
            **settings, 'limit': limit, 'days': days, 'max_workers': max_workers,
            'active_workers': min(max_workers, len(selected)),
            'output_dir': str(out.resolve()), 'strict': args.strict,
        },
        'sources': {name: {**source_cfg.get(name, {}), 'enabled': name in selected}
                    for name in dict.fromkeys([*source_cfg, *available])},
        'enrichment': {**config.get('enrichment', {}), 'epss': {
            **config.get('enrichment', {}).get('epss', {}), 'enabled': enricher is not None,
        }},
    })
    out.mkdir(parents=True, exist_ok=True)
    started = now()
    run_id = datetime.now(UTC).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:12]
    rows = []
    statuses = {}
    results = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(selected)), thread_name_prefix='collector') as executor:
        futures = {executor.submit(collect_source, sources[name], request): name for name in selected}
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
            _, result = results[name]
            print(f"{name:14} {result['status']:8} {result['count']:4} {result['message']}", flush=True)
    # Deterministic exports; workers never write SQLite or shared result lists.
    for name in selected:
        source_rows, statuses[name] = results[name]
        rows.extend(source_rows)
    enrichment_status = {'status': 'disabled'}
    if enricher is not None:
        try:
            enrichment_status = enricher.enrich(rows)
        except Exception as exc:
            enrichment_status = {'status': 'error', 'errors': [
                str(exc) if isinstance(exc, CollectionError) else 'Enrichment failed']}
        print(f"epss           {enrichment_status['status']:8} "
              f"{enrichment_status.get('matched_cves', 0):4} CVEs matched; "
              + '; '.join(enrichment_status.get('errors', [])), flush=True)
    manifest = {'run_id': run_id, 'started_at': started, 'finished_at': now(),
                'sources': statuses, 'count': len(rows), 'limit_per_source': limit,
                'enrichment': {'epss': enrichment_status},
                'legacy_days_option': days,
                'max_workers': min(max_workers, len(selected)),
                'notes': ['Rank/metrics are source-specific; do not sum across sources.',
                          'Sources collect current feed/list snapshots; the legacy --days option is ignored.',
                          'A shared group_id means the same normalized URL, not independent corroboration.',
                          'GeekNews RSS does not currently expose original article URLs.']}
    save_database(out / 'trends.sqlite3', run_id, rows, statuses, started)
    folder = out / 'runs' / run_id
    save_exports(folder, rows, manifest)
    print(f'Saved {len(rows)} records: {folder.resolve()}', flush=True)
    failed = any(v['status'] != 'ok' for v in statuses.values())
    failed = failed or enrichment_status['status'] in ('partial', 'error')
    return 1 if (args.strict and failed) or not rows else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
