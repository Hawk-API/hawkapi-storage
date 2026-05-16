# Changelog

## 0.2.0 — 2026-05-16

Security hardening.

- `LocalStorage._path` uses ``Path.resolve()`` + ``is_relative_to`` to reject
  every spelling of path traversal (``../``, symlink, etc.). NUL bytes in keys
  are now refused (CWE-22).
- `LocalStorage.signed_url` now emits a `UserWarning` when no `base_url` is
  configured to flag the production-unsafe `file://` URL (CWE-73).
- `AzureStorage.delete` only swallows `ResourceNotFoundError`; every other
  failure (auth, network, permission) propagates as `StorageError` instead of
  being silently dropped (CWE-732).
- S3 / GCS / Azure backend client init is now guarded by a per-instance
  ``threading.Lock`` so concurrent first calls don't race-init two SDK clients.
- `LocalStorage.list` uses prefix-targeted glob instead of `rglob("*")` so
  callers with a deep prefix on a large tree no longer scan the whole bucket.
- The active-storage registry uses `WeakKeyDictionary` to eliminate the
  `id(app)` ABA hazard.

## 0.1.0 — 2026-05-16

Initial release.

- `Storage` protocol — single async interface across every backend.
- Backends: `LocalStorage` (always), `S3Storage` (`[s3]`), `GCSStorage` (`[gcs]`), `AzureStorage` (`[azure]`). S3 backend speaks to MinIO / Wasabi / R2 via `endpoint_url=` + `use_path_style=`.
- `put` accepts `bytes`, file-like, or `AsyncIterator[bytes]` for streaming uploads.
- `stream(key, chunk_size=...)` for streaming downloads on every backend.
- Pre-signed URLs (GET/PUT/DELETE where supported) — `signed_url(key, expires_in=...)`.
- HMAC-signed local URLs with `verify_signed_url()` for self-hosted download endpoints.
- Path traversal rejected at `put`/`get` time.
- `init_storage(app, storage=...)` + `Depends(get_storage)`.
- `NotFoundError` / `StorageError` for clean handler-level error handling.
