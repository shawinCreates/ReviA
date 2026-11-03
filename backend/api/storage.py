from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import PurePosixPath

from django.conf import settings

logger = logging.getLogger(__name__)

#: Guards against a client that silently points nowhere (unset endpoint).
_MISSING = object()


class StorageNotConfiguredError(Exception):
    pass


class StorageError(Exception):
    pass


def reset_client_cache() -> None:
    _client.cache_clear()


@dataclass(frozen=True)
class StoredObject:
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
    # slugify() drops dots; the extension is re-attached, not sliced off.
    from django.utils.text import slugify

    from api.uploads import clean_filename

    name = clean_filename(filename)
    suffix = PurePosixPath(name).suffix.lower()

    stem = slugify(PurePosixPath(name).stem)[:80].strip("-") or "document"

    # Random suffix: a re-upload of the same name must not replace the first.
    unique = uuid.uuid4().hex[:12]

    return f"{owner_id}/{stem}-{unique}{suffix}"


def guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or fallback


def upload_file(owner_id: str, filename: str, fileobj) -> StoredObject:
    _credentials()  # Fail with a clear message before touching the file.
    path = build_object_path(owner_id, filename)
    content_type = guess_content_type(filename)
    bucket = settings.STORAGE_BUCKET

    try:
        client = _client()
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
        # Keep only the class name; never echo credentials or file contents.
        logger.exception("Upload of %s failed", path)
        raise StorageError(f"upload failed: {type(exc).__name__}") from exc

    return StoredObject(
        path=path,
        size=int(head.get("ContentLength", 0)),
        content_type=content_type,
    )


def download_file(storage_path: str) -> bytes:
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
