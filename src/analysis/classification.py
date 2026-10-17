"""Explainable multi-label topic classification; no external model requests."""
from src.categories import term_pattern

TOPICS = {
    'AI': ('ai', 'llm', '人工', '인공지능', 'machine learning', 'model', '모델', 'openai', 'claude', 'chatgpt', 'gemini'),
    '개발 도구': ('developer', 'programming', 'code', 'coding', '개발자', '프로그래밍', '코딩', 'github', 'python', 'javascript', 'api', 'sdk', 'ide'),
    '클라우드·인프라': ('cloud', '클라우드', 'kubernetes', 'docker', 'database', '데이터베이스', 'postgresql', 'server', '서버', 'linux', 'apache spark', '스키마'),
    '보안': ('security', '보안', '취약점', 'cve', 'vulnerability', 'ransomware', '랜섬웨어', 'malware', '해킹'),
    '하드웨어': ('gpu', 'cpu', 'chip', 'semiconductor', '반도체', 'nvidia', '엔비디아', '아이폰', 'iphone', '스마트폰'),
    '제품·서비스': ('saas', 'app', 'apps', '앱', 'product', '제품', '서비스', 'automation', '자동화'),
}


def classify(item):
    content = ' '.join([item['title'], item.get('summary', ''), *item.get('tags', [])])
    result = {topic: [term for term in terms if term_pattern(term).search(content)]
              for topic, terms in TOPICS.items()}
    result = {topic: terms for topic, terms in result.items() if terms}
    if item['source'] in ('cisa_kev', 'github_advisories', 'kisa', 'bleepingcomputer'):
        result.setdefault('보안', []).append('security_source')
    if item['source'] == 'huggingface':
        result.setdefault('AI', []).append('model_hub_source')
    if item['source'] == 'github':
        result.setdefault('개발 도구', []).append('repository_source')
    if item['source'] == 'producthunt':
        result.setdefault('제품·서비스', []).append('product_listing_source')
    return result or {'기타·미분류': []}
