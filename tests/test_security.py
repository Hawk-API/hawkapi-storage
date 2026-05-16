"""Regression tests for 0.2.0 hardening fixes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from hawkapi_storage import LocalConfig, LocalStorage, StorageError


def _store(tmp_path: Path) -> LocalStorage:
    return LocalStorage(LocalConfig(root=str(tmp_path)))


@pytest.mark.parametrize(
    "evil",
    [
        "../etc/passwd",
        "foo/../../bar",
        "../../../../../../etc/passwd",
        "a/b/../../../outside",
    ],
)
def test_path_traversal_via_dotdot_rejected(tmp_path: Path, evil: str) -> None:
    storage = _store(tmp_path)
    with pytest.raises(StorageError, match="path traversal"):
        # Any operation that goes through _path is fine; use `put`.
        asyncio.run(storage.put(evil, b"x"))


def test_nul_byte_in_key_rejected(tmp_path: Path) -> None:
    storage = _store(tmp_path)
    with pytest.raises(StorageError, match="control"):
        asyncio.run(storage.put("good\x00bad", b"x"))


def test_signed_url_without_base_url_warns(tmp_path: Path) -> None:
    storage = _store(tmp_path)
    with pytest.warns(UserWarning, match="base_url"):
        url = asyncio.run(storage.signed_url("foo.txt"))
    assert url.startswith("file://")


def test_azure_delete_propagates_real_errors() -> None:
    pytest.importorskip("azure.storage.blob")
    from azure.core.exceptions import (  # type: ignore[import-not-found]
        HttpResponseError,
        ResourceNotFoundError,
    )

    from hawkapi_storage import AzureConfig, AzureStorage

    storage = AzureStorage(
        AzureConfig(
            container="c",
            account_url="https://example.blob.core.windows.net",
            account_key="dGVzdGtleQ==",
        )
    )

    class FakeContainer:
        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        def delete_blob(self, key: str) -> None:
            raise self._exc

    # ResourceNotFoundError → swallowed (idempotent delete).
    storage._container = FakeContainer(ResourceNotFoundError("missing"))  # noqa: SLF001
    asyncio.run(storage.delete("does-not-matter"))

    # Other errors → wrapped as StorageError.
    storage._container = FakeContainer(HttpResponseError("auth"))  # noqa: SLF001
    with pytest.raises(StorageError):
        asyncio.run(storage.delete("x"))
