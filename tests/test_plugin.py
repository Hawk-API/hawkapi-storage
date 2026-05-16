"""Plugin entry point + DI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hawkapi import Depends, HawkAPI
from hawkapi.testing import TestClient

from hawkapi_storage import (
    LocalConfig,
    LocalStorage,
    Storage,
    get_storage,
    init_storage,
    resolve_storage,
)


def test_init_storage_attaches_to_state(tmp_path: Path) -> None:
    app = HawkAPI(openapi_url=None, docs_url=None, redoc_url=None, scalar_url=None)
    s = LocalStorage(config=LocalConfig(root=str(tmp_path)))
    init_storage(app, storage=s)
    assert app.state.storage is s


def test_resolve_storage_falls_back_to_last(tmp_path: Path) -> None:
    app = HawkAPI(openapi_url=None, docs_url=None, redoc_url=None, scalar_url=None)
    init_storage(app, storage=LocalStorage(config=LocalConfig(root=str(tmp_path))))
    assert resolve_storage(None) is not None


def test_get_storage_dep_returns_storage(tmp_path: Path) -> None:
    app = HawkAPI(openapi_url=None, docs_url=None, redoc_url=None, scalar_url=None)
    init_storage(app, storage=LocalStorage(config=LocalConfig(root=str(tmp_path))))

    @app.get("/info")
    async def info(s: Storage = Depends(get_storage)) -> dict[str, Any]:
        return {"backend": s.name}

    client = TestClient(app)
    r = client.get("/info")
    assert r.status_code == 200
    assert r.json() == {"backend": "local"}


def test_get_storage_500_when_missing() -> None:
    app = HawkAPI(openapi_url=None, docs_url=None, redoc_url=None, scalar_url=None)

    @app.get("/x")
    async def x(s: Storage = Depends(get_storage)) -> dict[str, Any]:
        return {"ok": True}

    import hawkapi_storage._plugin as _p

    saved = _p._LAST[0]
    _p._LAST[0] = None
    _p._ACTIVE.pop(app, None)
    try:
        r = TestClient(app).get("/x")
        assert r.status_code == 500
    finally:
        _p._LAST[0] = saved


@pytest.mark.parametrize(
    "backend_cls,config_cls,config_kwargs,expected_name",
    [
        ("S3Storage", "S3Config", {"bucket": "b"}, "s3"),
        ("GCSStorage", "GCSConfig", {"bucket": "b"}, "gcs"),
        ("AzureStorage", "AzureConfig", {"container": "c"}, "azure"),
    ],
)
def test_other_backend_class_metadata(
    backend_cls: str, config_cls: str, config_kwargs: dict[str, Any], expected_name: str
) -> None:
    """Smoke check — construct each backend without invoking real SDK calls."""
    import hawkapi_storage as hs

    cfg = getattr(hs, config_cls)(**config_kwargs)
    backend = getattr(hs, backend_cls)(config=cfg)
    assert backend.name == expected_name
