from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import PurePosixPath

from django.conf import settings

logger = logging.getLogger(__name__)

#: Leading bytes per allowed format, matched case-insensitively.
_MAGIC_NUMBERS: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    # Office Open XML is a zip container; the extension does the rest.
    ".docx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
}

#: Read this much from the front of the file to check the signature.
_SNIFF_BYTES = 8


class UploadRejected(Exception):
    def __init__(self, reason: str, *, code: str = "rejected"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    size: int
    content_type: str


def clean_filename(raw: str) -> str:
    # Null bytes truncate names in some C libraries ("safe.pdf\0" bypass).
    candidate = raw.replace("\x00", "")
    candidate = PurePosixPath(candidate).name
    candidate = candidate.replace("\\", "/").split("/")[-1]
    candidate = candidate.strip().lstrip(".")

    if not candidate or candidate in {".", ".."}:
        raise UploadRejected("That file has no usable name.", code="bad_filename")

    if len(candidate) > 255:
        raise UploadRejected("That filename is too long.", code="bad_filename")

    return candidate


def check_extension(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_UPLOAD_EXTENSIONS)
        raise UploadRejected(
            f"{suffix or 'That file type'} is not supported. Allowed types: {allowed}.",
            code="bad_extension",
        )
    return suffix


def check_size(size: int) -> None:
    limit = settings.MAX_UPLOAD_BYTES

    if size <= 0:
        raise UploadRejected("That file is empty.", code="empty_file")

    if size > limit:
        raise UploadRejected(
            f"That file is larger than the {limit // (1024 * 1024)} MB limit.",
            code="too_large",
        )


def check_magic_bytes(filename: str, head: bytes) -> None:
    suffix = PurePosixPath(filename).suffix.lower()
    expected = _MAGIC_NUMBERS.get(suffix)

    # An allowed extension without a signature just cannot be sniffed.
    if not expected:
        return

    if not head:
        raise UploadRejected("That file is empty.", code="empty_file")

    if not any(head.startswith(signature) for signature in expected):
        logger.info("Upload named %s did not match its %s signature", filename, suffix)
        raise UploadRejected(
            "That file does not look like the type its name says it is.",
            code="content_mismatch",
        )


def validate_upload(upload) -> ValidatedUpload:
    filename = clean_filename(upload.name)

    # From request headers, so untrusted; still the cheapest first pass.
    check_size(upload.size)

    check_extension(filename)

    position = upload.tell()
    try:
        head = upload.read(_SNIFF_BYTES)
    finally:
        upload.seek(position)

    check_magic_bytes(filename, head)

    from api.storage import guess_content_type

    return ValidatedUpload(
        filename=filename,
        size=upload.size,
        content_type=guess_content_type(filename),
    )
