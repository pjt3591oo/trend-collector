"""Fetch source HTML and extract bounded article context for post generation."""
import re
from src.http_client import HTTP
from src.parsing import Document, Node, text


class ArticleReader:
    def __init__(self, *, http=None, max_chars=12000):
        self.http = http if http is not None else HTTP({'retries': 1, 'timeout': 20})
        self.max_chars = max_chars

    def read(self, url):
        raw = self.http.get(url)  # No LLM Authorization header is sent to source pages.
        charset = re.search(br'charset\s*=\s*["\x27]?([\w-]+)', raw[:4096], re.I)
        encoding = charset[1].decode('ascii') if charset else 'utf-8-sig'
        try:
            html = raw.decode(encoding)
        except (LookupError, UnicodeError):
            raise ValueError('원문 문자 인코딩을 해석하지 못했습니다.') from None
        if not re.search(r'<(?:html|article|main|body|p)\b', html, re.I):
            raise ValueError('원문이 지원하는 HTML 형식이 아닙니다.')
        document = Document(html).root
        title = text(document.first('title'))
        region = document.first('article') or document.first('main') or document.first('body') or document
        excluded = {'script', 'style', 'svg', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'iframe'}
        def clean(node):
            if node.tag in excluded or 'hidden' in node.attrs or node.attrs.get('aria-hidden') == 'true':
                return ''
            return ' '.join(clean(c) if isinstance(c, Node) else c for c in node.children)
        content = re.sub(r'\s+', ' ', clean(region)).strip()
        if len(content) < 120:
            raise ValueError('원문 본문이 너무 짧거나 동적 렌더링이 필요합니다. 게시글을 생성하지 않습니다.')
        if any(marker in (title + ' ' + content[:500]).lower() for marker in
               ('just a moment', 'verify you are human', 'access denied', 'captcha', 'enable javascript')):
            raise ValueError('원문 접근 제한 페이지입니다. 게시글을 생성하지 않습니다.')
        return {'page_title': title, 'body': content[:self.max_chars],
                'truncated': len(content) > self.max_chars}
