"""Readable configuration logging without credential values."""
import re


def redact(value):
    if isinstance(value, dict):
        return {key: ('***' if re.search(r'token|secret|password|credential|authorization|api[_-]?key', str(key), re.I)
                      else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


LABELS = {
    'limit': '소스별 최대 건수', 'days': '기간 옵션 (호환용)',
    'max_workers': '최대 병렬 소스', 'active_workers': '실제 병렬 소스',
    'output_dir': '저장 경로', 'strict': '엄격 모드', 'timeout': '요청 제한 시간 (초)',
    'retries': '재시도 횟수', 'request_interval': '요청 간격 (초)',
    'user_agent': 'User-Agent', 'enabled': '활성 여부', 'category': '카테고리',
    'scan_limit': '후보 검사 건수', 'include_keywords': '추가 포함 키워드',
    'exclude_keywords': '제외 키워드', 'subreddits': '커뮤니티',
    'feed': '피드', 'sort': '정렬', 'time_filter': '조회 기간', 'since': '순위 기간',
    'language': '언어', 'geo': '지역', 'ecosystem': '패키지 생태계', 'severity': '심각도',
}


def format_value(value):
    if value is None:
        return '없음'
    if isinstance(value, bool):
        return '켜짐' if value else '꺼짐'
    if isinstance(value, list):
        return ', '.join(format_value(item) for item in value) if value else '없음'
    return str(value).replace('\r', ' ').replace('\n', ' ') if value != '' else '미지정'


def print_fields(values, indent='  '):
    for key, value in values.items():
        label = LABELS.get(key, key)
        if isinstance(value, dict):
            print(f'{indent}{label}')
            print_fields(value, indent + '  ')
        else:
            print(f'{indent}{label} : {format_value(value)}')


def print_config(config):
    config = redact(config)
    sources = config.get('sources', {})
    enabled = sum(bool(options.get('enabled')) for options in sources.values())
    print('\n' + '=' * 64)
    print('  트렌드 수집 · 실행 설정')
    print('=' * 64)
    print(f"  설정 파일 : {format_value(config.get('config_file'))}")
    print('\n[수집 설정]')
    print_fields(config.get('collector', {}))
    print(f'\n[수집 소스 · 활성 {enabled} / 전체 {len(sources)}]')
    for name, options in sources.items():
        state = 'ON ' if options.get('enabled') else 'OFF'
        print(f'  [{state}] {name}')
        print_fields({key: value for key, value in options.items() if key != 'enabled'}, '        ')
    print('\n[보강 기능]')
    print_fields(config.get('enrichment', {}))
    remaining = {key: value for key, value in config.items()
                 if key not in ('config_file', 'collector', 'sources', 'enrichment')}
    if remaining:
        print('\n[기타 설정]')
        print_fields(remaining)
    print('-' * 64)
    print('  수집을 시작합니다.\n', flush=True)
