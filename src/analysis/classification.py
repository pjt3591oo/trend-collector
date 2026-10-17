"""Eight primary categories with related fields and independent news-type tags."""
from collections import Counter
from src.categories import term_pattern

CATEGORIES = (
    'AI·머신러닝', '개발·오픈소스', '클라우드·인프라', '데이터·분석',
    '보안·개인정보', '하드웨어·반도체', '앱·서비스', '기타·분류 검토',
)
TOPICS = {
    CATEGORIES[0]: ('ai', 'llm', '인공지능', 'machine learning', 'deep learning', '생성형', '추론', '모델', 'openai', 'claude', 'chatgpt', 'gemini', 'transformers'),
    CATEGORIES[1]: ('developer', 'programming', 'code', 'coding', '개발자', '프로그래밍', '코딩', '오픈소스', 'open source', 'github', 'python', 'javascript', 'typescript', 'framework', '프레임워크', 'library', '라이브러리', 'api', 'sdk', 'ide'),
    CATEGORIES[2]: ('cloud', '클라우드', 'kubernetes', 'docker', 'server', '서버', 'linux', '네트워크', 'network', '배포', '인프라', 'devops', 'container', '컨테이너'),
    CATEGORIES[3]: ('database', '데이터베이스', 'postgresql', 'postgres', 'sql', 'mysql', 'mongodb', 'redis', 'apache spark', '데이터 분석', 'data analytics', 'data pipeline', '데이터 파이프라인', 'etl', '검색 엔진', 'search engine', '스키마'),
    CATEGORIES[4]: ('security', '보안', '개인정보', 'privacy', '취약점', 'cve', 'vulnerability', 'ransomware', '랜섬웨어', 'malware', '해킹', 'authentication', '인증', '암호화', '침해'),
    CATEGORIES[5]: ('gpu', 'cpu', 'chip', 'semiconductor', '반도체', 'nvidia', '엔비디아', '아이폰', 'iphone', '스마트폰', '하드웨어', 'hardware', 'robotics', '로봇'),
    CATEGORIES[6]: ('saas', 'app', 'apps', '앱', 'productivity', '생산성', '모바일', 'mobile', '업무 도구', 'automation', '자동화'),
}
NEWS_TYPES = {
    '출시·업데이트': ('launch', 'launched', 'release', 'released', 'update', '출시', '업데이트', '신제품', '공개'),
    '연구·기술 해설': ('research', 'paper', '연구', '논문', '해설', 'explained', 'benchmark', '벤치마크'),
    '개발 사례·튜토리얼': ('tutorial', 'guide', 'how to', 'i built', 'we built', '튜토리얼', '가이드', '구현', '만들었습니다', '개발 사례', '실무'),
    '취약점·보안 권고': ('cve', 'vulnerability', '취약점', 'advisory', '보안 업데이트', '보안 권고'),
    '침해사고·위협 동향': ('ransomware', '랜섬웨어', 'malware', 'spyware', 'attack', '침해사고', '공격', '유출', '악성', '스미싱'),
    '기업·시장 동향': ('funding', 'acquisition', 'earnings', 'stock', '투자 유치', '인수', '실적', '주가', '시장 점유율'),
}
# Explicit tie-break order. A CVE or specialist advisory source takes precedence below.
PRIORITY = ('보안·개인정보', 'AI·머신러닝', '데이터·분석', '개발·오픈소스',
            '하드웨어·반도체', '클라우드·인프라', '앱·서비스', '기타·분류 검토')


def classify_details(item):
    fields = [(item['title'], 3), (' '.join(item.get('tags', [])), 2), (item.get('summary', ''), 1)]
    scores, reasons = {}, {}
    for category, terms in TOPICS.items():
        matched, score = [], 0
        for term in terms:
            pattern = term_pattern(term)
            weights = [weight for content, weight in fields if pattern.search(content)]
            if weights:
                matched.append(term)
                score += max(weights)
        if matched:
            reasons[category], scores[category] = matched, score
    source = item['source']
    hint = {'huggingface': ('AI·머신러닝', 'model_hub_source'),
            'github': ('개발·오픈소스', 'repository_source'),
            'producthunt': ('앱·서비스', 'product_listing_source'),
            'bleepingcomputer': ('보안·개인정보', 'security_news_source')}.get(source)
    if hint:
        reasons.setdefault(hint[0], []).append(hint[1])
        scores[hint[0]] = scores.get(hint[0], 0) + 1
    is_advisory = source in ('cisa_kev', 'github_advisories', 'kisa')
    if is_advisory or item.get('metadata', {}).get('cve_ids'):
        reasons.setdefault('보안·개인정보', []).append('advisory_source' if is_advisory else 'cve_identifier')
        primary = '보안·개인정보'
    elif scores:
        primary = max(PRIORITY, key=lambda category: scores.get(category, 0))
    else:
        primary = '기타·분류 검토'
        reasons[primary] = []
    content = ' '.join(content for content, _ in fields)
    news_reasons = {tag: [term for term in terms if term_pattern(term).search(content)]
                    for tag, terms in NEWS_TYPES.items()}
    news_reasons = {tag: terms for tag, terms in news_reasons.items() if terms}
    if is_advisory:
        news_reasons.setdefault('취약점·보안 권고', []).append('advisory_source')
    return {'primary_category': primary,
            'related_categories': [category for category in CATEGORIES if category in reasons and category != primary],
            'news_types': list(news_reasons), 'category_reasons': reasons, 'news_type_reasons': news_reasons}


def classify(item):
    """Category-to-evidence mapping retained for existing analysis callers."""
    return classify_details(item)['category_reasons']


def primary_for_group(classifications):
    counts = Counter(c['primary_category'] for c in classifications)
    return max(PRIORITY, key=lambda category: counts[category])
