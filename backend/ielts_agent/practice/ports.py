"""Persistence boundary: each edit is an atomic, serialized transaction."""

from contextlib import AbstractContextManager
from typing import Protocol


class AttemptStore(Protocol):
    def load_source(self, item_id: str) -> tuple[dict, dict] | None: ...

    def create(self, attempt: dict) -> None: ...

    def get(self, attempt_id: str) -> dict | None: ...

    def edit(self, attempt_id: str) -> AbstractContextManager[dict | None]: ...
