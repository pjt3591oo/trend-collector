"""Legacy function registry derived from SOURCE_TYPES; use create_sources for new code."""
import os
from .base import CollectionRequest


def collectors(source_types):
    def adapt(cls):
        def collect(http, config, limit, days):
            return cls(http, config, credentials=os.environ).collect(CollectionRequest(limit=limit, days=days))
        return collect
    return {name: adapt(cls) for name, cls in source_types.items()}
