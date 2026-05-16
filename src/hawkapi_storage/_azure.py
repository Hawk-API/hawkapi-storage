"""Azure Blob Storage backend."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

from ._base import NotFoundError, StorageError, StoredObject, guess_content_type, to_bytes


@dataclass(slots=True)
class AzureConfig:
    container: str
    connection_string: str = ""
    account_url: str = ""
    """e.g. https://myaccount.blob.core.windows.net — used with ``credential``."""

    account_name: str = ""
    account_key: str = ""


@dataclass
class AzureStorage:
    config: AzureConfig
    name: str = "azure"
    _service: Any = field(default=None, init=False)
    _container: Any = field(default=None, init=False)

    def _get_container(self) -> Any:
        if self._container is not None:
            return self._container
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise StorageError(
                "azure-storage-blob not installed; pip install 'hawkapi-storage[azure]'"
            ) from exc
        if self.config.connection_string:
            self._service = BlobServiceClient.from_connection_string(self.config.connection_string)
        elif self.config.account_url and self.config.account_key:
            self._service = BlobServiceClient(
                account_url=self.config.account_url, credential=self.config.account_key
            )
        else:
            raise StorageError("AzureConfig requires connection_string or account_url+account_key")
        self._container = self._service.get_container_client(self.config.container)
        return self._container

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
        container = self._get_container()

        def _upload() -> None:
            from azure.storage.blob import ContentSettings  # type: ignore[import-not-found]

            blob = container.get_blob_client(key)
            blob.upload_blob(
                body,
                overwrite=True,
                content_settings=ContentSettings(
                    content_type=content_type or guess_content_type(key)
                ),
                metadata={k: str(v) for k, v in (metadata or {}).items()} or None,
            )

        await asyncio.to_thread(_upload)
        return StoredObject(
            key=key,
            size=len(body),
            content_type=content_type or guess_content_type(key),
            metadata=dict(metadata or {}),
        )

    async def get(self, key: str) -> bytes:
        container = self._get_container()

        def _download() -> bytes:
            blob = container.get_blob_client(key)
            try:
                stream = blob.download_blob()
            except Exception as exc:
                raise NotFoundError(key) from exc
            return stream.readall()

        return await asyncio.to_thread(_download)

    async def stream(self, key: str, *, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        data = await self.get(key)
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    async def exists(self, key: str) -> bool:
        container = self._get_container()
        return await asyncio.to_thread(container.get_blob_client(key).exists)

    async def delete(self, key: str) -> None:
        container = self._get_container()
        try:
            await asyncio.to_thread(container.delete_blob, key)
        except Exception:
            pass

    async def head(self, key: str) -> StoredObject:
        container = self._get_container()

        def _props() -> StoredObject:
            blob = container.get_blob_client(key)
            try:
                props = blob.get_blob_properties()
            except Exception as exc:
                raise NotFoundError(key) from exc
            return StoredObject(
                key=key,
                size=props.size or 0,
                content_type=(
                    props.content_settings.content_type if props.content_settings else None
                )
                or guess_content_type(key),
                last_modified=props.last_modified,
                etag=str(props.etag or "").strip('"'),
                metadata=dict(props.metadata or {}),
            )

        return await asyncio.to_thread(_props)

    async def list(self, prefix: str = "", *, limit: int = 1000) -> AsyncIterator[StoredObject]:
        container = self._get_container()

        def _list() -> list[Any]:
            return list(
                container.list_blobs(name_starts_with=prefix or None, results_per_page=limit)
            )

        emitted = 0
        for item in await asyncio.to_thread(_list):
            yield StoredObject(
                key=item.name,
                size=item.size or 0,
                content_type=(item.content_settings.content_type if item.content_settings else None)
                or guess_content_type(item.name),
                last_modified=item.last_modified,
            )
            emitted += 1
            if emitted >= limit:
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
        try:
            from azure.storage.blob import (  # type: ignore[import-not-found]
                BlobSasPermissions,
                generate_blob_sas,
            )
        except ImportError as exc:  # pragma: no cover
            raise StorageError("azure-storage-blob not installed") from exc
        container = self._get_container()
        account_name = container.account_name
        permissions = BlobSasPermissions(
            read=method.upper() == "GET", write=method.upper() == "PUT"
        )
        token = await asyncio.to_thread(
            generate_blob_sas,
            account_name=account_name,
            container_name=self.config.container,
            blob_name=key,
            account_key=self.config.account_key or None,
            permission=permissions,
            expiry=datetime.now(UTC) + timedelta(seconds=expires_in),
        )
        return f"{container.url}/{key}?{token}"


__all__ = ["AzureConfig", "AzureStorage"]
