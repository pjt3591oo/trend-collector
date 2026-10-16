#!/usr/bin/env python3
"""Trend collector. Python 3.11+, standard library only.

Run: python trend_collector.py --config config.toml
No article-body crawling or automatic posting. Credentials stay in environment variables.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
from pathlib import Path
import tomllib
from datetime import datetime
import uuid
import time

# Compatibility exports for existing callers of this module.
from src.models import (
    UTC as UTC, CollectionError as CollectionError, Skipped as Skipped,
    now as now, digest as digest, iso_date as iso_date,
    canonical_url as canonical_url, Item as Item,
)
from src.parsing import Node as Node, Document as Document, text as text, plain as plain, number as number, xml_text as xml_text
from src.http_client import SafeRedirect as SafeRedirect, HTTP as HTTP
from src.storage import save_database as save_database, csv_safe as csv_safe, save_exports as save_exports
from src.sources.geeknews import parse_geeknews as parse_geeknews, collect as geeknews
from src.sources.producthunt import parse_producthunt as parse_producthunt, collect as producthunt
from src.sources.hackernews import collect as hackernews
from src.sources.reddit import collect as reddit
from src.sources.github import parse_github as parse_github, collect as github
from src.sources.google_trends import parse_google as parse_google, collect as google_trends
from src.sources.indiehackers import parse_indiehackers as parse_indiehackers, collect as indiehackers
from src.sources.disquiet import parse_disquiet as parse_disquiet, collect as disquiet
from src.sources.huggingface import collect as huggingface
from src.sources import COLLECTORS, SOURCES
from src.sources import CollectionRequest, HTTPClient, Source, create_sources
from src.enrichment import Enricher, EPSSEnricher
from src.collection import collect_source


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
        config = tomllib.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else {}
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
