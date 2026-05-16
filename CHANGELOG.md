# Changelog

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
