"""
Supabase Storage helpers.

Uploads are direct from the browser to Storage, never proxied through Django.
That is what makes a 25MB upload viable on a 512MB instance: the file bytes
never touch the application process, only a signed URL and a row do.

The signed URL is time-limited and scoped to one key, so a leaked URL cannot be
used to read or overwrite anything else. See phases/phase-1-upload-and-parse.md.
"""

from __future__ import annotations

import uuid

from django.conf import settings

# Long enough for a slow connection to finish, short enough that a URL captured
# from a browser network log is not useful much later.
UPLOAD_URL_TTL_SECONDS = 300


class StorageError(Exception):
    pass


def _client():
    """
    A boto3 S3 client aimed at Supabase Storage.

    Built directly rather than through `default_storage` because we need the raw
    boto3 client to sign a URL; django-storages exposes the connection but not a
    stable public signing API for arbitrary keys.
    """
    import boto3

    if not settings.SUPABASE_S3_ENDPOINT:
        raise StorageError("Storage is not configured.")

    return boto3.client(
        "s3",
        endpoint_url=settings.SUPABASE_S3_ENDPOINT,
        aws_access_key_id=settings.SUPABASE_S3_ACCESS_KEY,
        aws_secret_access_key=settings.SUPABASE_S3_SECRET_KEY,
        region_name=settings.SUPABASE_S3_REGION,
    )


def presigned_upload_url(path: str, mime: str) -> str:
    """
    Sign a PUT for one object.

    `ContentType` is part of the signature, so the browser must send exactly the
    declared type. That is deliberate: it stops a caller from declaring a PDF
    and uploading arbitrary bytes under a .pdf key.
    """
    client = _client()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.SUPABASE_S3_BUCKET,
            "Key": path,
            "ContentType": mime,
        },
        ExpiresIn=UPLOAD_URL_TTL_SECONDS,
    )


def object_exists(path: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        _client().head_object(Bucket=settings.SUPABASE_S3_BUCKET, Key=path)
        return True
    except ClientError:
        return False


def object_size(path: str) -> int:
    from botocore.exceptions import ClientError

    try:
        head = _client().head_object(Bucket=settings.SUPABASE_S3_BUCKET, Key=path)
        return int(head["ContentLength"])
    except ClientError as exc:  # pragma: no cover - network dependent
        raise StorageError(f"Could not stat object: {exc}") from exc


def delete(path: str) -> None:
    """Best-effort delete, used when a document row is created but upload fails."""
    from botocore.exceptions import ClientError

    try:
        _client().delete_object(Bucket=settings.SUPABASE_S3_BUCKET, Key=path)
    except ClientError:  # pragma: no cover
        pass


def build_path(library_id, filename: str) -> str:
    """
    Storage key for an upload.

    Namespaced by library and prefixed with a random component, so two users
    uploading `paper.pdf` cannot collide and a key never encodes anything the
    uploader controls beyond the extension.
    """
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    # Sanitise: the suffix comes from user input and ends up in a storage key.
    safe_suffix = "".join(c for c in suffix if c.isalnum())[:8] or "bin"
    return f"{library_id}/{uuid.uuid4().hex}.{safe_suffix}"
