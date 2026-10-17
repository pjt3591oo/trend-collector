"""Explicit local topic selection for feeds without reliable native categories."""
from collections.abc import Iterator
import re

from .models import Item
from .sources.base import CollectionRequest, Source


TECHNOLOGY_TERMS = (
    'ai', 'artificial intelligence', 'llm', 'machine learning', 'deep learning',
    'software', 'programming', 'developer', 'coding', 'code', 'api', 'saas',
    'open source', 'opensource', 'github', 'linux', 'python', 'javascript', 'typescript',
    'rust', 'kubernetes', 'docker', 'database', 'cloud', 'cybersecurity', 'security',
    'vulnerability', 'ransomware', 'malware', 'cve', 'encryption', 'browser',
    'semiconductor', 'chip', 'gpu', 'cpu', 'nvidia', 'openai', 'chatgpt', 'claude',
    'gemini', 'copilot', 'iphone', 'android', 'ios', 'macos', 'windows', 'microsoft',
    'app', 'apps', 'web', 'website', 'automation', 'robotics', 'data science',
    '인공지능', '소프트웨어', '프로그래밍', '개발자', '코딩', '오픈소스', '클라우드',
    '데이터베이스', '보안', '취약점', '랜섬웨어', '반도체', '엔비디아', '삼성전자',
    '하이닉스', '아이폰', '안드로이드', '애플', '챗지피티', '챗GPT', '로봇', '자동화', '앱',
    '웹사이트', '웹서비스', '웹 서비스', '웹앱', '모바일 앱', '스마트폰', '컴퓨터',
)


def term_pattern(term):
    # ASCII token boundaries avoid matching AI in "said" or app in "happy",
    # while allowing Korean suffixes such as "AI가".
    escaped = re.escape(term)
    if term[0].isascii() and term[0].isalnum():
        escaped = r'(?<![a-z0-9])' + escaped
    if term[-1].isascii() and term[-1].isalnum():
        escaped += r'(?![a-z0-9])'
    return re.compile(escaped, re.I)


class CategorySource:
    """DI-compatible source decorator; source rank and identity are preserved."""
    def __init__(self, source: Source, config: dict):
        self.name = source.name
        self.source = source
        self.category = config.get('category', 'all')
        if self.category not in ('technology', 'all'):
            raise ValueError(f'{self.name}: category must be technology or all')
        self.scan_limit = config.get('scan_limit', 100)
        if type(self.scan_limit) is not int or not 1 <= self.scan_limit <= 500:
            raise ValueError(f'{self.name}: scan_limit must be 1..500')
        include = config.get('include_keywords', [])
        exclude = config.get('exclude_keywords', [])
        for key, values in (('include_keywords', include), ('exclude_keywords', exclude)):
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f'{self.name}: {key} must be a list of nonempty strings')
        terms = (TECHNOLOGY_TERMS if self.category == 'technology' else ()) + tuple(include)
        self.include = [term_pattern(term) for term in terms]
        self.exclude = [term_pattern(term) for term in exclude]
        self.filter_counts = {}

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        self.filter_counts = {'scanned': 0, 'filtered': 0, 'accepted': 0}
        scan = CollectionRequest(max(request.limit, self.scan_limit), request.days)
        for item in self.source.collect(scan):
            self.filter_counts['scanned'] += 1
            content = ' '.join([item.title, item.summary, *item.tags])
            matches = any(p.search(content) for p in self.include)
            if (self.include and not matches) or any(p.search(content) for p in self.exclude):
                self.filter_counts['filtered'] += 1
                continue
            item.metadata['category_filter'] = {'category': self.category, 'method': 'local_keywords'}
            self.filter_counts['accepted'] += 1
            yield item
            if self.filter_counts['accepted'] >= request.limit:
                break
