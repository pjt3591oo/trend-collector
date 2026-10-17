"""Source contracts, implementations, and dependency composition."""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from .base import CollectionRequest, HTTPClient, Source

from .geeknews import GeekNewsSource, collect as geeknews
from .producthunt import ProductHuntSource, collect as producthunt
from .hackernews import HackerNewsSource, collect as hackernews
from .reddit import RedditSource, collect as reddit
from .github import GitHubSource, collect as github
from .google_trends import GoogleTrendsSource, collect as google_trends
from .indiehackers import IndieHackersSource, collect as indiehackers
from .disquiet import DisquietSource, collect as disquiet
from .huggingface import HuggingFaceSource, collect as huggingface
from .bleepingcomputer import BleepingComputerSource
from .cisa_kev import CISAKEVSource
from .github_advisories import GitHubAdvisoriesSource
from .kisa import KISASource

COLLECTORS = {
    'geeknews': geeknews,
    'producthunt': producthunt,
    'hackernews': hackernews,
    'reddit': reddit,
    'github': github,
    'google_trends': google_trends,
    'indiehackers': indiehackers,
    'disquiet': disquiet,
    'huggingface': huggingface,
}



SOURCE_TYPES = {
    'geeknews': GeekNewsSource,
    'producthunt': ProductHuntSource,
    'hackernews': HackerNewsSource,
    'reddit': RedditSource,
    'github': GitHubSource,
    'google_trends': GoogleTrendsSource,
    'indiehackers': IndieHackersSource,
    'disquiet': DisquietSource,
    'huggingface': HuggingFaceSource,
    'bleepingcomputer': BleepingComputerSource,
    'cisa_kev': CISAKEVSource,
    'github_advisories': GitHubAdvisoriesSource,
    'kisa': KISASource,
}


SOURCES = tuple(SOURCE_TYPES)


def create_sources(
    http: HTTPClient,
    config: Mapping[str, Mapping[str, Any]] | None = None,
    *, credentials: Mapping[str, str] | None = None,
) -> dict[str, Source]:
    """Compose built-in sources; explicit credentials bypass environment lookup."""
    config = config if config is not None else {}
    credentials = os.environ if credentials is None else credentials
    from ..categories import CategorySource

    result = {}
    for name, cls in SOURCE_TYPES.items():
        options = config.get(name, {})
        source = cls(http, options, credentials=credentials)
        if any(key in options for key in ('category', 'include_keywords', 'exclude_keywords')):
            source = CategorySource(source, options)
        result[name] = source
    return result
