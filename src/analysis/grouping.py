"""Strong identifiers first; named entities are topics, not identical events."""
from urllib.parse import urlsplit

from src.text_matching import term_pattern
from src.models import canonical_url
from src.security import cve_ids

DEFAULT_ENTITIES = {
    'OpenAI': ['openai', 'chatgpt', '챗지피티', '챗gpt'],
    'Claude': ['claude', '클로드'],
    'Gemini': ['gemini', '제미나이'],
    'NVIDIA': ['nvidia', '엔비디아'],
    'PostgreSQL': ['postgresql', 'postgres'],
    'Kubernetes': ['kubernetes', '쿠버네티스'],
}


def groups(item, entities):
    content = ' '.join([item['title'], item.get('summary', ''), *item.get('tags', [])])
    cves = cve_ids(content, *item.get('metadata', {}).get('cve_ids', []))
    if cves:
        return [('cve:' + cve, cve, 'cve') for cve in cves]
    parts = urlsplit(item['url'])
    path = parts.path.strip('/').split('/')
    if parts.hostname == 'github.com' and len(path) == 2:
        repo = '/'.join(path)
        return [('repo:' + repo.lower(), repo, 'repository')]
    matched = [('entity:' + name, name, 'entity_topic') for name, aliases in entities.items()
               if any(term_pattern(alias).search(content) for alias in aliases)]
    return matched or [('url:' + canonical_url(item['url']), item['title'], 'url')]
