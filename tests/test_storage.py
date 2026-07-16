"""Streaming storage: content-addressing, hash equivalence, and the size cap."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest

from app.services import storage


def test_save_stream_is_content_addressed(tmp_path) -> None:
    content = b"hello filemindr " * 100
    stored = storage.save_stream(
        io.BytesIO(content), uuid.uuid4(), ".pdf", max_bytes=10_000, storage_root=tmp_path
    )
    assert stored.byte_size == len(content)
    assert Path(stored.storage_path).read_bytes() == content
    assert Path(stored.storage_path).name == f"{stored.file_hash}.pdf"


def test_save_stream_hash_matches_full_bytes(tmp_path) -> None:
    # The incremental hash must equal hashing the whole body at once (dedup key).
    content = b"some bytes that get streamed in chunks for hashing"
    stored = storage.save_stream(
        io.BytesIO(content), uuid.uuid4(), ".bin", max_bytes=10_000, storage_root=tmp_path
    )
    assert stored.file_hash == storage.compute_hash(content)


def test_save_stream_rejects_oversized_and_cleans_up(tmp_path) -> None:
    account_id = uuid.uuid4()
    with pytest.raises(storage.FileTooLargeError):
        storage.save_stream(
            io.BytesIO(b"x" * 5000), account_id, ".pdf", max_bytes=1000, storage_root=tmp_path
        )
    # Neither a temp nor a final file is left behind.
    account_dir = tmp_path / str(account_id)
    leftovers = list(account_dir.iterdir()) if account_dir.exists() else []
    assert leftovers == []
