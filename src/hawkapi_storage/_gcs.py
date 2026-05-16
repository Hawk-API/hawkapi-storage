"""Google Cloud Storage backend (sync API offloaded to a thread)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, BinaryIO

from ._base import NotFoundError, StorageError, StoredObject, guess_content_type, to_bytes


@dataclass(slots=True)
class GCSConfig:
    bucket: str
    project: str = ""
    credentials_path: str = ""


@dataclass
class GCSStorage:
    config: GCSConfig
    name: str = "gcs"
    _client: Any = field(default=None, init=False)
    _bucket: Any = field(default=None, init=False)

    def _get_bucket(self) -> Any:
        if self._bucket is not None:
            return self._bucket
        try:
            from google.cloud import storage  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise StorageError(
                "google-cloud-storage not installed; pip install 'hawkapi-storage[gcs]'"
            ) from exc
        if self.config.credentials_path:
            self._client = storage.Client.from_service_account_json(self.config.credentials_path)
        else:
            self._client = storage.Client(project=self.config.project or None)
        self._bucket = self._client.bucket(self.config.bucket)
        return self._bucket

    async def put(
        self,
        key: str,
        data: bytes | BinaryIO | AsyncIterator[bytes],
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        if not isinstance(data, (bytes, bytearray)) and not hasattr(data, "read"):
            chunks: list[bytes] = []
            async for chunk in data:
                chunks.append(chunk)
            data = b"".join(chunks)
        body = to_bytes(data)  # type: ignore[arg-type]
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        if metadata:
            blob.metadata = {k: str(v) for k, v in metadata.items()}

        def _upload() -> None:
            blob.upload_from_string(body, content_type=content_type or guess_content_type(key))

        await asyncio.to_thread(_upload)
        return StoredObject(
            key=key,
            size=len(body),
            content_type=content_type or guess_content_type(key),
            metadata=dict(metadata or {}),
        )

    async def get(self, key: str) -> bytes:
        bucket = self._get_bucket()
        blob = bucket.blob(key)

        def _download() -> bytes:
            if not blob.exists():
                raise NotFoundError(key)
            return blob.download_as_bytes()

        return await asyncio.to_thread(_download)

    async def stream(self, key: str, *, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        # The GCS SDK does not expose a true streaming reader for blobs; we
        # download once and re-yield in chunks, which is fine for the typical
        # API-served-file size and keeps memory bounded for callers.
        data = await self.get(key)
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    async def exists(self, key: str) -> bool:
        bucket = self._get_bucket()
        return await asyncio.to_thread(bucket.blob(key).exists)

    async def delete(self, key: str) -> None:
        bucket = self._get_bucket()
        await asyncio.to_thread(bucket.blob(key).delete)

    async def head(self, key: str) -> StoredObject:
        bucket = self._get_bucket()
        blob = bucket.blob(key)

        def _reload() -> StoredObject:
            if not blob.exists():
                raise NotFoundError(key)
            blob.reload()
            return StoredObject(
                key=key,
                size=blob.size or 0,
                content_type=blob.content_type or guess_content_type(key),
                last_modified=blob.updated,
                etag=str(blob.etag or "").strip('"'),
                metadata=dict(blob.metadata or {}),
            )

        return await asyncio.to_thread(_reload)

    async def list(self, prefix: str = "", *, limit: int = 1000) -> AsyncIterator[StoredObject]:
        bucket = self._get_bucket()

        def _enumerate() -> list[Any]:
            return list(bucket.list_blobs(prefix=prefix or None, max_results=limit))

        for blob in await asyncio.to_thread(_enumerate):
            yield StoredObject(
                key=blob.name,
                size=blob.size or 0,
                content_type=blob.content_type or guess_content_type(blob.name),
                last_modified=blob.updated,
                etag=str(blob.etag or "").strip('"'),
            )

    async def signed_url(
        self,
        key: str,
        *,
        expires_in: int = 3600,
        method: str = "GET",
        content_type: str | None = None,
    ) -> str:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        return await asyncio.to_thread(
            blob.generate_signed_url,
            expiration=timedelta(seconds=expires_in),
            method=method.upper(),
            content_type=content_type,
            version="v4",
        )


__all__ = ["GCSConfig", "GCSStorage"]
