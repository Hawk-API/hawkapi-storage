"""Storage backend abstraction."""

from __future__ import annotations

import io
import mimetypes
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import BinaryIO, Protocol


@dataclass(slots=True)
class StoredObject:
    key: str
    size: int = 0
    content_type: str = "application/octet-stream"
    last_modified: datetime | None = None
    etag: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class StorageError(Exception):
    """Raised by every backend when a primitive fails."""


class NotFoundError(StorageError):
    """Raised when a key does not exist."""


class Storage(Protocol):
    """The minimal contract every backend implements."""

    name: str

    async def put(
        self,
        key: str,
        data: bytes | BinaryIO | AsyncIterator[bytes],
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject: ...

    async def get(self, key: str) -> bytes: ...

    async def stream(self, key: str, *, chunk_size: int = 65536) -> AsyncIterator[bytes]: ...

    async def exists(self, key: str) -> bool: ...

    async def delete(self, key: str) -> None: ...

    async def head(self, key: str) -> StoredObject: ...

    async def list(self, prefix: str = "", *, limit: int = 1000) -> AsyncIterator[StoredObject]: ...

    async def signed_url(
        self,
        key: str,
        *,
        expires_in: int = 3600,
        method: str = "GET",
        content_type: str | None = None,
    ) -> str: ...


def guess_content_type(key: str) -> str:
    """Best-effort MIME guess from the key/filename."""
    return mimetypes.guess_type(key)[0] or "application/octet-stream"


def to_bytes(data: bytes | BinaryIO) -> bytes:
    """Read a bytes/file-like into memory. Used by backends that need a single buffer."""
    if isinstance(data, bytes):
        return data
    if isinstance(data, io.IOBase) or hasattr(data, "read"):
        return data.read()
    raise TypeError(f"unsupported data type: {type(data).__name__}")


__all__ = [
    "NotFoundError",
    "Storage",
    "StorageError",
    "StoredObject",
    "guess_content_type",
    "to_bytes",
]
