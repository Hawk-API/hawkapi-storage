# hawkapi-storage

Pluggable file storage for [HawkAPI](https://github.com/ashimov/HawkAPI). One `Storage` protocol, four backends: local filesystem, AWS S3 (and S3-compatible — MinIO, Wasabi, R2), Google Cloud Storage, Azure Blob Storage. Pre-signed URLs and streaming on all of them.

## Install

```bash
pip install hawkapi-storage                  # local filesystem only
pip install 'hawkapi-storage[s3]'            # + AWS S3
pip install 'hawkapi-storage[gcs]'           # + Google Cloud Storage
pip install 'hawkapi-storage[azure]'         # + Azure Blob Storage
```

## Quickstart

```python
from hawkapi import Depends, HawkAPI
from hawkapi_storage import LocalConfig, LocalStorage, Storage, get_storage, init_storage

app = HawkAPI()
init_storage(app, storage=LocalStorage(LocalConfig(root="/var/data", base_url="https://cdn.example")))


@app.put("/files/{key}")
async def upload(key: str, body: bytes, s: Storage = Depends(get_storage)):
    obj = await s.put(key, body, content_type="application/octet-stream")
    return {"key": obj.key, "size": obj.size}


@app.get("/files/{key}/url")
async def signed(key: str, s: Storage = Depends(get_storage)):
    return {"url": await s.signed_url(key, expires_in=300)}
```

Swap `LocalStorage` for any other backend — every primitive is identical.

## Backends

```python
from hawkapi_storage import (
    LocalStorage, LocalConfig,
    S3Storage,    S3Config,        # extras: [s3]
    GCSStorage,   GCSConfig,       # extras: [gcs]
    AzureStorage, AzureConfig,     # extras: [azure]
)

local = LocalStorage(LocalConfig(root="/var/data"))
s3    = S3Storage(S3Config(bucket="my-bucket", region="eu-west-1"))
minio = S3Storage(S3Config(bucket="mb", endpoint_url="https://minio.example", use_path_style=True))
gcs   = GCSStorage(GCSConfig(bucket="my-bucket", project="my-project"))
azure = AzureStorage(AzureConfig(container="files", connection_string="..."))
```

## The `Storage` protocol

```python
class Storage(Protocol):
    name: str

    async def put(self, key, data, *, content_type=None, metadata=None) -> StoredObject: ...
    async def get(self, key) -> bytes: ...
    async def stream(self, key, *, chunk_size=65536) -> AsyncIterator[bytes]: ...
    async def exists(self, key) -> bool: ...
    async def delete(self, key) -> None: ...
    async def head(self, key) -> StoredObject: ...
    async def list(self, prefix="", *, limit=1000) -> AsyncIterator[StoredObject]: ...
    async def signed_url(self, key, *, expires_in=3600, method="GET", content_type=None) -> str: ...
```

`put()` accepts `bytes`, a file-like object, or an `AsyncIterator[bytes]` (for streaming uploads).

## Streaming downloads

```python
@app.get("/download/{key}")
async def download(key: str, s: Storage = Depends(get_storage)):
    return StreamingResponse(s.stream(key, chunk_size=65536),
                             media_type=(await s.head(key)).content_type)
```

## Pre-signed URLs

Every backend supports `signed_url(key, expires_in=..., method="GET" | "PUT")`. For PUT/upload pre-signs, pass `content_type=` so the client must send the matching `Content-Type` header.

`LocalStorage` produces HMAC-signed URLs that you verify on download with `local.verify_signed_url(key, expires, sig, method="GET")` — useful when serving downloads through your own handler.

## Local filesystem details

- Path traversal (`..`) is rejected at `put`/`get` time.
- `LocalConfig(base_url=...)` sets the prefix used by `signed_url()` — pair it with a Nginx alias or a HawkAPI download handler.
- `LocalConfig(signing_secret=...)` lets you pin the HMAC secret (otherwise generated once at startup).

## Errors

- `StorageError` — base class.
- `NotFoundError(key)` — `get` / `head` / `stream` on a missing key.

## Development

```bash
git clone https://github.com/ashimov/hawkapi-storage.git
cd hawkapi-storage
uv sync --extra dev
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run pyright src/
```

## License

MIT.
