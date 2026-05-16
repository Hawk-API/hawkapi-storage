"""AWS S3 backend (boto3, sync API offloaded to a thread)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from ._base import NotFoundError, StorageError, StoredObject, guess_content_type, to_bytes


@dataclass(slots=True)
class S3Config:
    bucket: str
    region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    endpoint_url: str = ""
    """Set to a non-AWS S3-compatible endpoint (MinIO, Wasabi, …)."""

    use_path_style: bool = False
    """Path-style addressing for MinIO and friends."""


@dataclass
class S3Storage:
    config: S3Config
    name: str = "s3"
    _client: Any = field(default=None, init=False)
    _init_lock: Any = field(default=None, init=False, repr=False)

    def _client_lock(self) -> Any:
        # Lazily create the lock so the dataclass remains hashable/copyable
        # and we never bind it to a foreign event loop.
        import threading  # noqa: PLC0415

        if self._init_lock is None:
            self._init_lock = threading.Lock()
        return self._init_lock

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        with self._client_lock():
            if self._client is not None:
                return self._client
            try:
                import boto3  # noqa: PLC0415
                from botocore.config import Config  # noqa: PLC0415
            except ImportError as exc:  # pragma: no cover
                raise StorageError(
                    "boto3 not installed; pip install 'hawkapi-storage[s3]'"
                ) from exc
            kwargs: dict[str, Any] = {"region_name": self.config.region}
            if self.config.aws_access_key_id:
                kwargs["aws_access_key_id"] = self.config.aws_access_key_id
                kwargs["aws_secret_access_key"] = self.config.aws_secret_access_key
            if self.config.endpoint_url:
                kwargs["endpoint_url"] = self.config.endpoint_url
            if self.config.use_path_style:
                kwargs["config"] = Config(s3={"addressing_style": "path"})
            self._client = boto3.client("s3", **kwargs)
            return self._client

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
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "Bucket": self.config.bucket,
            "Key": key,
            "Body": body,
            "ContentType": content_type or guess_content_type(key),
        }
        if metadata:
            kwargs["Metadata"] = {k: str(v) for k, v in metadata.items()}
        await asyncio.to_thread(client.put_object, **kwargs)
        return StoredObject(
            key=key,
            size=len(body),
            content_type=kwargs["ContentType"],
            metadata=dict(metadata or {}),
        )

    async def get(self, key: str) -> bytes:
        client = self._get_client()
        try:
            obj = await asyncio.to_thread(client.get_object, Bucket=self.config.bucket, Key=key)
        except Exception as exc:
            raise NotFoundError(key) from exc
        return await asyncio.to_thread(obj["Body"].read)

    async def stream(self, key: str, *, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        client = self._get_client()
        try:
            obj = await asyncio.to_thread(client.get_object, Bucket=self.config.bucket, Key=key)
        except Exception as exc:
            raise NotFoundError(key) from exc
        stream = obj["Body"]
        while True:
            chunk = await asyncio.to_thread(stream.read, chunk_size)
            if not chunk:
                break
            yield chunk

    async def exists(self, key: str) -> bool:
        client = self._get_client()
        try:
            await asyncio.to_thread(client.head_object, Bucket=self.config.bucket, Key=key)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> None:
        client = self._get_client()
        await asyncio.to_thread(client.delete_object, Bucket=self.config.bucket, Key=key)

    async def head(self, key: str) -> StoredObject:
        client = self._get_client()
        try:
            meta = await asyncio.to_thread(client.head_object, Bucket=self.config.bucket, Key=key)
        except Exception as exc:
            raise NotFoundError(key) from exc
        return StoredObject(
            key=key,
            size=meta.get("ContentLength", 0),
            content_type=meta.get("ContentType", guess_content_type(key)),
            last_modified=meta.get("LastModified"),
            etag=str(meta.get("ETag", "")).strip('"'),
            metadata=dict(meta.get("Metadata", {})),
        )

    async def list(self, prefix: str = "", *, limit: int = 1000) -> AsyncIterator[StoredObject]:
        client = self._get_client()
        token: str | None = None
        emitted = 0
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self.config.bucket,
                "Prefix": prefix,
                "MaxKeys": min(limit - emitted, 1000),
            }
            if token:
                kwargs["ContinuationToken"] = token
            resp = await asyncio.to_thread(client.list_objects_v2, **kwargs)
            for obj in resp.get("Contents", []):
                yield StoredObject(
                    key=obj["Key"],
                    size=obj.get("Size", 0),
                    content_type=guess_content_type(obj["Key"]),
                    last_modified=obj.get("LastModified"),
                    etag=str(obj.get("ETag", "")).strip('"'),
                )
                emitted += 1
                if emitted >= limit:
                    return
            if not resp.get("IsTruncated"):
                return
            token = resp.get("NextContinuationToken")

    async def signed_url(
        self,
        key: str,
        *,
        expires_in: int = 3600,
        method: str = "GET",
        content_type: str | None = None,
    ) -> str:
        client = self._get_client()
        op = {"GET": "get_object", "PUT": "put_object", "DELETE": "delete_object"}.get(
            method.upper()
        )
        if op is None:
            raise StorageError(f"unsupported signed URL method {method!r}")
        params: dict[str, Any] = {"Bucket": self.config.bucket, "Key": key}
        if method.upper() == "PUT" and content_type:
            params["ContentType"] = content_type
        return await asyncio.to_thread(
            client.generate_presigned_url, op, Params=params, ExpiresIn=expires_in
        )


__all__ = ["S3Config", "S3Storage"]
