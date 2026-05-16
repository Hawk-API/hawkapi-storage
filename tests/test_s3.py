"""S3 backend — exercise sync boto3 client via fakes."""

from __future__ import annotations

from typing import Any

import pytest

from hawkapi_storage import S3Config, S3Storage


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []

    def put_object(self, **kw: Any) -> dict[str, Any]:
        self.calls.append("put_object")
        self.objects[kw["Key"]] = {
            "Body": kw["Body"],
            "ContentType": kw.get("ContentType"),
            "Metadata": kw.get("Metadata", {}),
        }
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        self.calls.append("get_object")
        if Key not in self.objects:
            raise FileNotFoundError(Key)

        class _Body:
            def __init__(self, data: bytes) -> None:
                self._data = data
                self._cursor = 0

            def read(self, n: int = -1) -> bytes:
                if n < 0:
                    out = self._data[self._cursor :]
                    self._cursor = len(self._data)
                    return out
                out = self._data[self._cursor : self._cursor + n]
                self._cursor += len(out)
                return out

        return {"Body": _Body(self.objects[Key]["Body"])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        self.calls.append("head_object")
        if Key not in self.objects:
            raise FileNotFoundError
        body = self.objects[Key]["Body"]
        return {
            "ContentLength": len(body),
            "ContentType": self.objects[Key]["ContentType"],
            "Metadata": self.objects[Key]["Metadata"],
            "ETag": '"abc"',
        }

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        self.objects.pop(Key, None)

    def list_objects_v2(self, **kw: Any) -> dict[str, Any]:
        prefix = kw.get("Prefix", "")
        contents = [
            {"Key": k, "Size": len(v["Body"]), "ETag": '"abc"'}
            for k, v in self.objects.items()
            if k.startswith(prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}

    def generate_presigned_url(self, op: str, **kw: Any) -> str:
        return f"https://signed.example/{kw['Params']['Key']}?op={op}&exp={kw['ExpiresIn']}"


@pytest.fixture
def s3() -> S3Storage:
    backend = S3Storage(config=S3Config(bucket="b"))
    backend._client = FakeS3Client()
    return backend


async def test_s3_put_and_get(s3: S3Storage) -> None:
    obj = await s3.put("k", b"data")
    assert obj.size == 4
    assert await s3.get("k") == b"data"


async def test_s3_exists_and_head(s3: S3Storage) -> None:
    await s3.put("k", b"x")
    assert await s3.exists("k") is True
    head = await s3.head("k")
    assert head.size == 1


async def test_s3_delete(s3: S3Storage) -> None:
    await s3.put("k", b"x")
    await s3.delete("k")
    assert await s3.exists("k") is False


async def test_s3_list(s3: S3Storage) -> None:
    await s3.put("a/1", b"1")
    await s3.put("a/2", b"2")
    await s3.put("b/3", b"3")
    keys = [obj.key async for obj in s3.list(prefix="a/")]
    assert set(keys) == {"a/1", "a/2"}


async def test_s3_signed_url(s3: S3Storage) -> None:
    url = await s3.signed_url("k", expires_in=120, method="PUT", content_type="image/png")
    assert "k" in url
    assert "op=put_object" in url
