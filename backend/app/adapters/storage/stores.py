"""Object storage.

Document images. Never public, never served from the API process, always behind
a signed URL with a short expiry.

`LocalObjectStore` is the laptop demo path and the test path: it writes under
`DOCUMENT_STORAGE_DIR` and hands back an API-relative URL that the documents
router serves, so `docker compose up` gives a complete working stack with no
cloud account. `GCSObjectStore` is the deployed path.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.errors import MediKioskError, NotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)


class StorageError(MediKioskError):
    status_code = 500
    code = "storage_error"


def object_key(hospital_id: str, intake_id: str, document_id: str, suffix: str) -> str:
    """Where a document lives.

    Hospital-first, so a per-hospital bucket or a per-hospital IAM condition is
    a prefix change rather than a migration — the same reasoning that puts
    `hospital_id` on every table.
    """
    return f"{hospital_id}/{intake_id}/{document_id}{suffix}"


class LocalObjectStore:
    """Local disk. The demo path when venue wifi fails."""

    name = "local"

    def __init__(self, root: Path, *, api_prefix: str = "/api/v1") -> None:
        self._root = root
        self._api_prefix = api_prefix
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # `key` is built by `object_key` from identifiers we generated, but this
        # is the one place a traversal would land on the filesystem, so it is
        # checked rather than trusted.
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root.resolve()):
            raise StorageError(f"refusing to resolve storage key outside the root: {key!r}")
        return candidate

    async def put(self, key: str, data: bytes, *, content_type: str) -> str:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return key

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError(f"no stored object for key {key!r}")
        data: bytes = await asyncio.to_thread(path.read_bytes)
        return data

    async def signed_url(self, key: str, *, ttl_seconds: int) -> str:
        """An API-relative URL.

        Not cryptographically signed — locally the API is the only reader and it
        checks the caller's role and hospital on every request. The expiry is
        carried so the caller behaves the same way against either backend.
        """
        expires = int((datetime.now(UTC) + timedelta(seconds=ttl_seconds)).timestamp())
        return f"{self._api_prefix}/documents/content/{key}?expires={expires}"

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            await asyncio.to_thread(path.unlink)


class GCSObjectStore:
    """Google Cloud Storage.

    Uniform bucket-level access, no public objects, V4 signed URLs with the
    configured TTL. The bucket is created by `infra/` with public access
    prevention enforced; nothing here can loosen that.
    """

    name = "gcs"

    def __init__(self, bucket: str, *, ttl_seconds: int = 300) -> None:
        if not bucket:
            raise StorageError("GCS_BUCKET is not set")
        self._bucket_name = bucket
        self._ttl = ttl_seconds
        self._client: Any | None = None

    def _bucket(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import storage
            except ImportError as exc:  # pragma: no cover
                raise StorageError(
                    "google-cloud-storage is not installed; install the 'gcp' extra"
                ) from exc
            self._client = storage.Client()
        return self._client.bucket(self._bucket_name)

    async def put(self, key: str, data: bytes, *, content_type: str) -> str:
        blob = self._bucket().blob(key)
        await asyncio.to_thread(blob.upload_from_string, data, content_type=content_type)
        return key

    async def get(self, key: str) -> bytes:
        blob = self._bucket().blob(key)
        if not await asyncio.to_thread(blob.exists):
            raise NotFoundError(f"no stored object for key {key!r}")
        data: bytes = await asyncio.to_thread(blob.download_as_bytes)
        return data

    async def signed_url(self, key: str, *, ttl_seconds: int) -> str:
        blob = self._bucket().blob(key)
        url: str = await asyncio.to_thread(
            blob.generate_signed_url,
            version="v4",
            expiration=timedelta(seconds=ttl_seconds),
            method="GET",
        )
        return url

    async def delete(self, key: str) -> None:
        blob = self._bucket().blob(key)
        await asyncio.to_thread(blob.delete)


def build_store(settings: Settings) -> LocalObjectStore | GCSObjectStore:
    """The configured store."""
    if settings.storage_backend == "gcs":
        return GCSObjectStore(
            settings.gcs_bucket or "", ttl_seconds=settings.signed_url_ttl_seconds
        )
    return LocalObjectStore(settings.document_storage_dir, api_prefix=settings.api_prefix)
