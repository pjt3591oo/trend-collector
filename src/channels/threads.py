"""Meta Threads text publishing using the official container API."""
import re

from src.channels.base import Post, PublishError
from src.http_client import HTTP
from src.models import CollectionError


class ThreadsPublishError(PublishError):
    """Safe, stage-specific error without token or remote response body."""


def request_json(http, url, headers, payload, stage):
    try:
        return http.json(url, headers, payload)
    except CollectionError as exc:
        match = re.search(r'HTTP (\d{3})', str(exc))
        detail = f'HTTP {match[1]}' if match else '네트워크 또는 응답 오류'
        raise ThreadsPublishError(f'Threads {stage} 실패 ({detail}).',
            uncertain=stage != '컨테이너 생성' and not (match and 400 <= int(match[1]) < 500 and match[1] != '408')) from None
    except (ValueError, TypeError):
        raise ThreadsPublishError(f'Threads {stage} 응답을 해석하지 못했습니다.', uncertain=stage != '컨테이너 생성') from None


class ThreadsChannel:
    def __init__(self, settings, *, http=None):
        self.settings = dict(settings)
        self._validated = False
        self.http = http if http is not None else HTTP({'retries': 0, 'timeout': 20})

    def publish(self, post: Post) -> str:
        return self._publish_text(post.text)

    def _publish_text(self, text):
        if not text.strip() or len(text) > 500:
            raise ValueError('Threads text must contain 1..500 characters')
        if not self._validated:
            self.validate()
        token = self.settings['access_token']
        user = self.settings['user_id']
        headers = {'Authorization': f'Bearer {token}'}
        base = f'https://graph.threads.net/v1.0/{user}'
        payload = {'media_type': 'TEXT', 'text': text}
        container = request_json(self.http, base + '/threads', headers, payload, '컨테이너 생성')
        creation_id = str(container.get('id', ''))
        if not creation_id.isdigit():
            raise ThreadsPublishError('Threads 컨테이너 생성 응답에 유효한 ID가 없습니다.', uncertain=False)
        result = request_json(self.http, base + '/threads_publish', headers, {'creation_id': creation_id}, '게시')
        post_id = str(result.get('id', ''))
        if not post_id.isdigit():
            raise ThreadsPublishError('Threads 게시 응답에 유효한 ID가 없습니다. 계정에서 발행 여부를 확인하세요.')
        return post_id

    def validate(self):
        token = self.settings.get('access_token', '')
        user = self.settings.get('user_id', '')
        if not token or not user:
            raise ValueError('.env에 THREADS_ACCESS_TOKEN과 THREADS_USER_ID를 설정해 주세요.')
        if not re.fullmatch(r'[0-9]+', user):
            raise ValueError('THREADS_USER_ID는 @사용자명이나 프로필 URL이 아닌 숫자 Threads 사용자 ID여야 합니다. .env를 수정한 뒤 뷰어를 재시작하세요.')
        self._validated = True
