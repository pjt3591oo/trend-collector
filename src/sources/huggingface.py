"""Site-specific collection and parsing."""
from __future__ import annotations

from collections.abc import Iterator
from .base import BaseSource, CollectionRequest

import os
from urllib.parse import urlencode
from src.models import CollectionError, Item

class HuggingFaceSource(BaseSource):
    name = 'huggingface'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        http, cfg = self.http, self.config
        limit, days = request.limit, request.days
        params = {'sort': 'trendingScore', 'direction': -1, 'limit': limit}
        token = self.credentials.get('HF_TOKEN')
        headers = {'Authorization': 'Bearer ' + token} if token else None
        data = http.json('https://huggingface.co/api/models?' + urlencode(params), headers=headers)
        if not isinstance(data, list):
            raise CollectionError('Unexpected Hugging Face model list')
        for rank, model in enumerate(data[:limit], 1):
            name = model['id']
            yield Item('huggingface', name, name, 'https://huggingface.co/' + name,
                       published_at=model.get('createdAt'), summary=model.get('pipeline_tag', ''),
                       tags=model.get('tags', []),
                       metrics={'likes': model.get('likes'), 'downloads': model.get('downloads'),
                                'trending_score': model.get('trendingScore')},
                       rank=rank, collection_method='official_api',
                       metadata={'last_modified': model.get('lastModified'), 'scope': 'models',
                                 'downloads_window': 'provider_default'})

def collect(http, cfg, limit, days):
    """Compatibility wrapper; use HuggingFaceSource for dependency injection."""
    return HuggingFaceSource(http, cfg, credentials=os.environ).collect(CollectionRequest(limit, days))
