from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import PurePosixPath

from django.conf import settings

logger = logging.getLogger(__name__)

#: Leading bytes of each allowed format. Matched case-insensitively because PDF
#: headers are conventionally uppercase but the format does not require it.
_MAGIC_NUMBERS: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    # Every Office Open XML file is a zip container, so "PK\x03\x04" is as
    # specific as the signature gets without unpacking the whole archive. The
    # file extension carries the rest of the distinction.
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
    # A null byte truncates the name in some C libraries, which is how a
    # "safe.pdf\x00.png" style bypass works. Remove it before anything else.
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
        # Said in MB because the limit is a round number in MB and a raw byte
        # count means nothing to the person reading it.
        raise UploadRejected(
            f"That file is larger than the {limit // (1024 * 1024)} MB limit.",
            code="too_large",
        )


def check_magic_bytes(filename: str, head: bytes) -> None:
    suffix = PurePosixPath(filename).suffix.lower()
    expected = _MAGIC_NUMBERS.get(suffix)

    # An extension we allow but have no signature for is not an error; it just
    # cannot be checked this way.
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

    # `size` is populated from the request headers, so it can be trusted to be
    # wrong. It is still the cheapest possible first pass.
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
