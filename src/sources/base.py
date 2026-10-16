"""Common source contracts and constructor dependencies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from src.models import Item
from src.parsing import Node


class HTTPClient(Protocol):
    def get(self, url: str, headers: dict | None = None,
            payload: dict | None = None) -> bytes: ...

    def json(self, url: str, headers: dict | None = None,
             payload: dict | None = None) -> Any: ...

    def page(self, url: str) -> Node: ...


@dataclass(frozen=True)
class CollectionRequest:
    limit: int = 20
    days: int = 7

    def __post_init__(self):
        if not 1 <= self.limit <= 500 or not 1 <= self.days <= 365:
            raise ValueError('limit must be 1..500, days must be 1..365')


class Source(Protocol):
    name: str

    def collect(self, request: CollectionRequest) -> Iterator[Item]: ...


class BaseSource(ABC):
    name: str

    def __init__(self, http: HTTPClient, config: Mapping[str, Any] | None = None,
                 *, credentials: Mapping[str, str] | None = None):
        self.http = http
        self.config = dict(config) if config is not None else {}
        self.credentials = dict(credentials) if credentials is not None else {}

    @abstractmethod
    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        """Yield normalized items; errors may follow successfully yielded items."""
        raise NotImplementedError
