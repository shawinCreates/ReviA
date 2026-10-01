"""Uploading a file to Supabase Storage and reading it back.

S3-compatible rather than the Supabase Python SDK, for one reason that matters
here: the backend already has the S3 endpoint and keys in its configuration, and
boto3 does multipart uploads and range reads properly, which the ingestion step
will need for large PDFs. The SDK's own upload helper would be a second code
path for the same bucket.

The client is built lazily and cached. Constructing it at import time would make
a missing credential an import error, which reads as a broken install rather
than a missing key — and it would do that for every management command,
including ones that never touch storage.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import PurePosixPath

from django.conf import settings

logger = logging.getLogger(__name__)

#: Guards against a client that is constructed successfully but silently points
#: nowhere, which is what an unset endpoint produces.
_MISSING = object()


class StorageNotConfiguredError(Exception):
    """Storage credentials are absent, so uploads cannot be attempted."""


class StorageError(Exception):
    """The bucket rejected the operation."""


def reset_client_cache() -> None:
    """Drop the cached boto3 client. Intended for tests and credential changes."""
    _client.cache_clear()


@dataclass(frozen=True)
class StoredObject:
    """Where a file ended up, and what the bucket says about it."""

    path: str
    size: int
    content_type: str


def _credentials() -> tuple[str, str, str, str]:
    endpoint = settings.STORAGE_ENDPOINT
    access_key = settings.STORAGE_ACCESS_KEY
    secret_key = settings.STORAGE_SECRET_KEY
    bucket = settings.STORAGE_BUCKET

    missing = [
        name
        for name, value in (
            ("SUPABASE_S3_ENDPOINT", endpoint),
            ("SUPABASE_S3_ACCESS_KEY", access_key),
            ("SUPABASE_S3_SECRET_KEY", secret_key),
            ("SUPABASE_S3_BUCKET", bucket),
        )
        if not value
    ]
    if missing:
        raise StorageNotConfiguredError(
            f"storage is not configured: {', '.join(missing)} "
            f"(see backend/.env.example for the S3 section)"
        )

    return endpoint, access_key, secret_key, bucket


@lru_cache(maxsize=1)
def _client():
    """A shared boto3 S3 client.

    Cached because building one parses config and opens a connection pool, and
    a request that uploads and then reads back should not pay for it twice.
    """
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise StorageNotConfiguredError(
            "boto3 is required for storage; add it to the backend dependencies"
        ) from exc

    endpoint, access_key, secret_key, _ = _credentials()

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=settings.STORAGE_REGION or "us-east-1",
    )


def build_object_path(owner_id: str, filename: str) -> str:
    """Where a user's file lives in the bucket.

    Namespaced by owner so one account's uploads cannot be guessed or listed
    from another, and so a future bucket policy can be scoped per prefix without
    a database lookup.

    The filename is reduced to something safe rather than used as-is. It comes
    from the client, so a value like `../../other-user/secret.pdf` would
    otherwise escape the prefix and write wherever it liked.
    """
    # `slugify` with `allow_unicode=False` gives an ASCII stem, and the
    # extension is re-attached from the cleaned name rather than sliced off the
    # slug: `slugify` drops the dot, so slicing produced "lecture-3pdf" and two
    # different files could collide on one key.
    from django.utils.text import slugify

    from api.uploads import clean_filename

    name = clean_filename(filename)
    suffix = PurePosixPath(name).suffix.lower()

    # The stem is the name without its extension, and slugified.
    stem = slugify(PurePosixPath(name).stem)[:80].strip("-") or "document"

    # A random suffix, so two uploads of "lecture-3.pdf" do not overwrite each
    # other. Deterministic naming would make the second upload silently replace
    # the first, and the first document's stored_path would then point at
    # different content.
    unique = uuid.uuid4().hex[:12]

    return f"{owner_id}/{stem}-{unique}{suffix}"


def guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    """Content type from the extension.

    `mimetypes` is a system table, so it is advisory: an upload is validated by
    extension allowlist and by inspecting the file, never by trusting this.
    """
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or fallback


def upload_file(owner_id: str, filename: str, fileobj) -> StoredObject:
    """Store an uploaded file under the caller's prefix.

    `fileobj` is a file-like object, which is what Django hands over for an
    uploaded file. It is read from the current position, so a caller that has
    already read part of it sends the remainder.
    """
    _credentials()  # Fail with a clear message before touching the file.
    path = build_object_path(owner_id, filename)
    content_type = guess_content_type(filename)
    bucket = settings.STORAGE_BUCKET

    try:
        client = _client()
        # `upload_fileobj`, not `upload_file`. The latter's first argument is a
        # path on the local filesystem, so handing it a file object fails with
        # "Filename must be a string or a path-like object" — which reads like a
        # bad argument type rather than the wrong method.
        client.upload_fileobj(
            fileobj,
            bucket,
            path,
            ExtraArgs={"ContentType": content_type},
        )
        head = client.head_object(Bucket=bucket, Key=path)
    except StorageNotConfiguredError:
        raise
    except Exception as exc:
        # boto3 raises a wide range of client errors; the class name is the most
        # useful thing to keep without echoing credentials or file contents.
        logger.exception("Upload of %s failed", path)
        raise StorageError(f"upload failed: {type(exc).__name__}") from exc

    return StoredObject(
        path=path,
        size=int(head.get("ContentLength", 0)),
        content_type=content_type,
    )


def download_file(storage_path: str) -> bytes:
    """Read a stored file into memory.

    Sized for the pipeline's inputs, which are documents a user chose to upload
    against a 25 MB cap. Streaming to a parser would be the change to make if
    that ever stops being true.
    """
    try:
        client = _client()
        response = client.get_object(Bucket=_bucket_name(), Key=storage_path)
        return response["Body"].read()
    except StorageNotConfiguredError:
        raise
    except Exception as exc:
        logger.exception("Read of %s failed", storage_path)
        raise StorageError(f"download failed: {type(exc).__name__}") from exc


def delete_file(storage_path: str) -> None:
    """Remove a stored file, treating an already-missing object as success.

    Deletion is the one operation where a missing file is the desired end state,
    so it must not raise. This is also what makes a retried delete safe.
    """
    try:
        client = _client()
        client.delete_object(Bucket=_bucket_name(), Key=storage_path)
    except StorageNotConfiguredError:
        raise
    except Exception as exc:
        if _is_missing(exc):
            return
        logger.exception("Delete of %s failed", storage_path)
        raise StorageError(f"delete failed: {type(exc).__name__}") from exc


def _is_missing(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    code = str(response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


def _bucket_name() -> str:
    return settings.STORAGE_BUCKET
