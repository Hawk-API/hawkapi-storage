"""Local filesystem backend — useful for dev + tests."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import shutil
import time
import warnings
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote, urlencode

from ._base import (
    NotFoundError,
    StorageError,
    StoredObject,
    guess_content_type,
    to_bytes,
)


@dataclass(slots=True)
class LocalConfig:
    root: str
    """Filesystem directory that holds the objects."""

    base_url: str = ""
    """Public base URL prefix used by :meth:`signed_url`. Leave empty to return a
    ``file://`` URL (only meaningful for tests)."""

    signing_secret: str = ""
    """HMAC secret for short-lived download URLs. Generated lazily if unset."""


@dataclass
class LocalStorage:
    config: LocalConfig
    name: str = "local"
    _secret: str = field(default="", init=False)

    def __post_init__(self) -> None:
        os.makedirs(self.config.root, exist_ok=True)
        self._secret = (
            self.config.signing_secret or base64.urlsafe_b64encode(os.urandom(32)).decode()
        )

    def _path(self, key: str) -> Path:
        # Reject control characters outright — NUL anywhere in a path is
        # never legitimate and can confuse downstream tooling.
        if "\x00" in key:
            raise StorageError("invalid key (control characters)")
        root = Path(self.config.root).resolve()
        # ``resolve()`` collapses every ``..`` segment so escapes can be
        # detected unambiguously, no matter how they are spelled.
        target = (root / key.lstrip("/")).resolve()
        if not target.is_relative_to(root):
            raise StorageError("invalid key (path traversal)")
        return target

    async def put(
        self,
        key: str,
        data: bytes | BinaryIO | AsyncIterator[bytes],
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        if isinstance(data, (bytes, bytearray)) or hasattr(data, "read"):
            buf = to_bytes(data)  # type: ignore[arg-type]
            await asyncio.to_thread(path.write_bytes, buf)
        else:
            chunks: list[bytes] = []
            async for chunk in data:
                chunks.append(chunk)
            await asyncio.to_thread(path.write_bytes, b"".join(chunks))
        stat = await asyncio.to_thread(path.stat)
        return StoredObject(
            key=key,
            size=stat.st_size,
            content_type=content_type or guess_content_type(key),
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            metadata=dict(metadata or {}),
        )

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError(key)
        return await asyncio.to_thread(path.read_bytes)

    async def stream(self, key: str, *, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError(key)

        def _chunks() -> list[bytes]:
            out: list[bytes] = []
            with path.open("rb") as fh:
                while True:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    out.append(chunk)
            return out

        for chunk in await asyncio.to_thread(_chunks):
            yield chunk

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_dir():
            await asyncio.to_thread(shutil.rmtree, str(path))
        elif path.exists():
            await asyncio.to_thread(path.unlink)

    async def head(self, key: str) -> StoredObject:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError(key)
        stat = await asyncio.to_thread(path.stat)
        return StoredObject(
            key=key,
            size=stat.st_size,
            content_type=guess_content_type(key),
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )

    async def list(self, prefix: str = "", *, limit: int = 1000) -> AsyncIterator[StoredObject]:
        root = Path(self.config.root)
        if not root.exists():
            return
        # Prefix-targeted glob avoids walking the full tree when callers
        # query a deep sub-prefix in a large bucket.
        normalised = prefix.lstrip("/")
        pattern = f"{normalised}**/*" if normalised else "**/*"
        count = 0
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if normalised and not rel.startswith(normalised):
                continue
            stat = await asyncio.to_thread(path.stat)
            yield StoredObject(
                key=rel,
                size=stat.st_size,
                content_type=guess_content_type(rel),
                last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
            count += 1
            if count >= limit:
                return

    async def signed_url(
        self,
        key: str,
        *,
        expires_in: int = 3600,
        method: str = "GET",
        content_type: str | None = None,
    ) -> str:
        _ = content_type
        if method.upper() not in {"GET", "PUT"}:
            raise StorageError("LocalStorage only signs GET / PUT")
        expires = int(time.time()) + max(1, expires_in)
        msg = f"{method.upper()}:{key}:{expires}".encode()
        sig = hmac.new(self._secret.encode(), msg, hashlib.sha256).hexdigest()
        query = urlencode({"expires": expires, "sig": sig, "method": method.upper()})
        if self.config.base_url:
            base = self.config.base_url.rstrip("/")
            return f"{base}/{quote(key)}?{query}"
        warnings.warn(
            "LocalStorage.signed_url called without base_url; returning file:// URL "
            "(safe for tests only — set LocalConfig.base_url in production)",
            UserWarning,
            stacklevel=2,
        )
        return f"file://{self._path(key)}?{query}"

    def verify_signed_url(self, key: str, expires: int, sig: str, *, method: str = "GET") -> bool:
        if expires < int(time.time()):
            return False
        msg = f"{method.upper()}:{key}:{expires}".encode()
        expected = hmac.new(self._secret.encode(), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)


__all__ = ["LocalConfig", "LocalStorage"]
