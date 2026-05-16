"""hawkapi-storage — pluggable file storage for HawkAPI.

Backends: local filesystem, AWS S3 (extras ``[s3]``), Google Cloud Storage
(extras ``[gcs]``), Azure Blob Storage (extras ``[azure]``). Single
:class:`Storage` protocol — swap backends freely.
"""

from __future__ import annotations

from ._azure import AzureConfig, AzureStorage
from ._base import (
    NotFoundError,
    Storage,
    StorageError,
    StoredObject,
    guess_content_type,
)
from ._gcs import GCSConfig, GCSStorage
from ._local import LocalConfig, LocalStorage
from ._plugin import get_storage, init_storage, resolve_storage
from ._s3 import S3Config, S3Storage

__version__ = "0.1.0"

__all__ = [
    "AzureConfig",
    "AzureStorage",
    "GCSConfig",
    "GCSStorage",
    "LocalConfig",
    "LocalStorage",
    "NotFoundError",
    "S3Config",
    "S3Storage",
    "Storage",
    "StorageError",
    "StoredObject",
    "__version__",
    "get_storage",
    "guess_content_type",
    "init_storage",
    "resolve_storage",
]
