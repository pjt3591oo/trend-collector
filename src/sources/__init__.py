"""Source contracts, implementations, and dependency composition."""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from .base import CollectionRequest, HTTPClient, Source

from .geeknews import GeekNewsSource
from .producthunt import ProductHuntSource
from .hackernews import HackerNewsSource
from .reddit import RedditSource
from .github import GitHubSource
from .google_trends import GoogleTrendsSource
from .indiehackers import IndieHackersSource
from .disquiet import DisquietSource
from .huggingface import HuggingFaceSource
from .bleepingcomputer import BleepingComputerSource
from .cisa_kev import CISAKEVSource
from .github_advisories import GitHubAdvisoriesSource
from .kisa import KISASource

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


# Legacy callers can keep importing the original named function aliases.
# Both aliases and COLLECTORS derive from the sole SOURCE_TYPES registry.
from .compat import collectors as _legacy_collectors
import sys as _sys
COLLECTORS = _legacy_collectors(SOURCE_TYPES)
for _name, _type in SOURCE_TYPES.items():
    if callable(getattr(_sys.modules[_type.__module__], 'collect', None)):
        globals()[_name] = COLLECTORS[_name]
del _name, _type, _legacy_collectors, _sys
