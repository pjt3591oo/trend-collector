"""Shared contract for injectable publishing adapters."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Post:
    text: str


class Channel(Protocol):
    def validate(self) -> None:
        """Validate channel settings before recording an attempt."""
        ...

    def publish(self, post: Post) -> str:
        """Publish once and return the provider post ID; never retry implicitly."""
        ...


class PublishError(ValueError):
    """Sanitized adapter failure; uncertain means the provider may have published."""
    def __init__(self, message, *, uncertain=True):
        super().__init__(message)
        self.uncertain = uncertain
