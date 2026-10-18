"""Prepare reviewable posts and record attempts before network side effects."""
from pathlib import Path

from src.security import safe_error
from src.channels.base import Post, PublishError
from src.publications import PublicationRepository, post_digest, publication_state



def publish_posts(draft, channels, journal: Path):
    return _publish_posts(draft, channels, Path(journal))


def _publish_posts(draft, channels, journal: Path):
    if not channels:
        raise ValueError('No output channels enabled in config')
    for channel in channels.values():
        validate = getattr(channel, 'validate', None)
        if validate is not None:
            validate()
    posts = [Post(p['text']) for p in draft['posts']]
    if not posts or any(not isinstance(p.text, str) or not p.text.strip() or len(p.text) > 500 for p in posts):
        raise ValueError('Draft must contain nonempty posts of at most 500 characters')
    repository = PublicationRepository(journal)
    results = []
    with repository.connect() as db:
        for name, channel in channels.items():
            for index, post in enumerate(posts):
                digest = post_digest(post.text)
                original_index = draft.get('post_indices', list(range(len(posts))))[index]
                if not repository.claim(db, name, digest, draft.get('draft_id'), original_index):
                    results.append((name, 'skipped', digest))
                    continue
                try:
                    post_id = channel.publish(post)
                except PublishError as exc:
                    message = safe_error(exc)
                    repository.finish(db, name, digest, 'pending' if exc.uncertain else 'failed', error=message)
                    raise ValueError(message + (' 발행 결과는 미확인 상태로 보관했습니다. 계정을 확인해 주세요.' if exc.uncertain else ' 발행하지 못했습니다. 설정 수정 후 다시 시도할 수 있습니다.')) from None
                except Exception:
                    repository.finish(db, name, digest, 'pending', error='Provider result not confirmed')
                    raise ValueError(f'{name}: publish not confirmed; check account and journal before retrying') from None
                repository.finish(db, name, digest, 'published', post_id=post_id)
                results.append((name, 'published', post_id))
    return results


