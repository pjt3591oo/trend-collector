#!/usr/bin/env python3
"""Analyze saved observations: uv run trend_analyzer.py --config config.toml."""
import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tomllib
import uuid

from src.analysis.engine import analyze
from src.analysis.reporting import save_analysis


def main(argv=None):
    parser = argparse.ArgumentParser(description='저장된 IT 관측 데이터의 주제·변화 분석')
    parser.add_argument('--config', type=Path, default=Path('config.toml'))
    parser.add_argument('--database', type=Path)
    parser.add_argument('--date', type=date.fromisoformat, help='분석할 한국 날짜 YYYY-MM-DD; 생략하면 현재까지')
    parser.add_argument('--window-hours', type=int, help='현재/이전 비교 구간 길이, 기본 24시간')
    parser.add_argument('--out', type=Path, help='보고서 폴더; 기본 collector.output_dir/analysis')
    args = parser.parse_args(argv)
    try:
        config = tomllib.loads(args.config.read_text(encoding='utf-8-sig')) if args.config.exists() else {}
        settings = config.get('analysis', {})
        out = Path(config.get('collector', {}).get('output_dir', 'data'))
        database = args.database or out / 'trends.sqlite3'
        hours = args.window_hours if args.window_hours is not None else settings.get('window_hours', 24)
        if type(hours) is not int or not 1 <= hours <= 720:
            raise ValueError('window_hours must be 1..720')
        if args.date and hours != 24:
            raise ValueError('--date는 24시간 일간 보고서에만 사용할 수 있습니다.')
        current = datetime.now(timezone.utc)
        if args.date:
            end = datetime.combine(args.date + timedelta(days=1), datetime.min.time(),
                                   tzinfo=timezone(timedelta(hours=9)))
            if end > current:
                raise ValueError('--date는 종료된 한국 날짜를 지정해 주세요. 현재까지의 분석은 --date 없이 실행합니다.')
        else:
            end = current
        report = analyze(database, end=end, window_hours=hours, entities=settings.get('entities'))
        analysis_id = current.strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:12]
        folder = save_analysis(database, report, analysis_id, args.out or out / 'analysis')
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(f"분석 완료 · 고유 항목 {report['summary']['items']}건 · 관측 {report['summary']['observations']}건")
    print(f"비교 기간: {'비교 가능' if report['coverage']['comparable'] else '데이터 부족 (증가 신호 미계산)'}")
    print(f'보고서: {folder.resolve()}')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
