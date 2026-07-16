"""Raw file persistence for ingested documents.

Files are content-addressed: the SHA-256 of the bytes is both the dedup key and
the on-disk name, laid out as ``<storage_root>/<account_id>/<hash><ext>``. Writes
are atomic (temp file then ``os.replace``) so a crashed upload never leaves a
half-written file that looks complete.

Uploads are **streamed**: bytes are read in chunks, hashed incrementally, and
written straight to the temp file, so a large file never sits whole in memory.
A size cap is enforced mid-stream so an oversized upload is rejected before it
fills the disk.

`get_storage_root` is the single point that resolves the storage directory, so
tests can redirect it without touching settings.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

# Chunk size for streaming reads/writes (1 MiB).
_STREAM_CHUNK = 1024 * 1024


class Readable(Protocol):
    """A synchronous, chunk-readable byte stream (e.g. a spooled temp file)."""

    def read(self, size: int = ..., /) -> bytes: ...


class FileTooLargeError(Exception):
    """Raised when a streamed upload exceeds the configured byte limit."""

    def __init__(self, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        super().__init__(f"Upload exceeds the {limit_bytes}-byte limit.")


@dataclass(frozen=True)
class StoredFile:
    file_hash: str
    storage_path: str
    byte_size: int


def get_storage_root() -> Path:
    """Absolute root directory for raw files (override target for tests)."""
    return get_settings().storage_path


def compute_hash(content: bytes) -> str:
    """SHA-256 hex digest of `content` — the content-address / dedup key."""
    return hashlib.sha256(content).hexdigest()


def save_stream(
    stream: Readable,
    account_id: uuid.UUID,
    ext: str,
    *,
    max_bytes: int,
    storage_root: Path | None = None,
) -> StoredFile:
    """Stream `stream` to content-addressed storage for `account_id`.

    Reads in chunks (never buffering the whole body), hashing as it goes, and
    rejects the upload with `FileTooLargeError` the moment it exceeds
    `max_bytes`. On success the temp file is atomically renamed to its
    ``<hash><ext>`` path; on any failure the temp file is removed. Idempotent by
    construction: identical bytes map to the same path. `ext` includes the
    leading dot and is cosmetic only.
    """
    root = storage_root or get_storage_root()
    account_dir = root / str(account_id)
    account_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    tmp_path = account_dir / f".upload.{uuid.uuid4().hex}{ext}.tmp"
    try:
        with tmp_path.open("wb") as tmp:
            while True:
                chunk = stream.read(_STREAM_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(max_bytes)
                digest.update(chunk)
                tmp.write(chunk)
        file_hash = digest.hexdigest()
        final_path = account_dir / f"{file_hash}{ext}"
        os.replace(tmp_path, final_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return StoredFile(file_hash=file_hash, storage_path=str(final_path), byte_size=size)
