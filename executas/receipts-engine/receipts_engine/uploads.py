"""In-memory buffer for chunked CV uploads.

A 2 MB PDF is 2.7 MB of base64 — past the host reader's 2 MiB line cap and far
past the 64 KB argument cap on async invokes, so the file arrives as a sequence
of ``upload_chunk`` calls on the synchronous channel
(``docs/api-notes.md §6``).

Chunks are held in memory and never written to disk. That is a privacy
decision, not a performance one: ``CLAUDE.md`` rule 5 says CV content lives in
the user's storage and nowhere else, and a temp file is somewhere else.
"""

from __future__ import annotations

import base64
import binascii
import threading
import time
from dataclasses import dataclass, field
from typing import Final

from .errors import EngineError

#: Matches ``parse/cv.py``'s ceiling — checked here too so an oversized upload
#: is rejected on the first chunk instead of after the last.
MAX_UPLOAD_BYTES: Final[int] = 2 * 1024 * 1024

#: The UI slices at 128 KiB of base64; allow a little slack for a client that
#: rounds differently, but not enough to approach the 512 KiB frame cap.
MAX_CHUNK_B64: Final[int] = 192 * 1024

#: An abandoned upload (user closed the window mid-file) frees itself.
UPLOAD_TTL_S: Final[float] = 600.0

#: Bounds the damage a misbehaving client can do to plugin memory.
MAX_CONCURRENT_UPLOADS: Final[int] = 4


@dataclass
class _Upload:
    total: int
    filename: str | None
    started_at: float
    chunks: list[bytes] = field(default_factory=list)
    size: int = 0


class UploadBuffer:
    """Reassembles chunked uploads keyed by an id the UI generates."""

    def __init__(self, *, ttl_s: float = UPLOAD_TTL_S) -> None:
        self._ttl = ttl_s
        self._lock = threading.Lock()
        self._uploads: dict[str, _Upload] = {}

    def add_chunk(
        self,
        *,
        upload_id: str,
        index: int,
        total: int,
        data_b64: str,
        filename: str | None = None,
    ) -> dict[str, int | bool]:
        """Append one chunk. Chunks must arrive in order, starting at 0."""
        if not upload_id or not isinstance(upload_id, str) or len(upload_id) > 64:
            raise EngineError("invalid_args", "upload_id must be a short string")
        if total <= 0 or index < 0 or index >= total:
            raise EngineError("invalid_args", "chunk index out of range")
        if len(data_b64) > MAX_CHUNK_B64:
            raise EngineError("file_too_large", details={"chunk_b64": len(data_b64)})

        try:
            payload = base64.b64decode(data_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise EngineError("invalid_args", "chunk is not valid base64") from exc

        with self._lock:
            self._expire_locked()
            upload = self._uploads.get(upload_id)

            if index == 0:
                if len(self._uploads) >= MAX_CONCURRENT_UPLOADS and upload is None:
                    oldest = min(self._uploads, key=lambda key: self._uploads[key].started_at)
                    self._uploads.pop(oldest, None)
                upload = _Upload(total=total, filename=filename, started_at=time.monotonic())
                self._uploads[upload_id] = upload
            elif upload is None:
                raise EngineError("upload_expired", details={"index": index})
            elif len(upload.chunks) != index:
                raise EngineError(
                    "invalid_args",
                    "chunks must arrive in order",
                    details={"expected": len(upload.chunks), "got": index},
                )

            assert upload is not None  # narrowed by the branches above
            upload.size += len(payload)
            if upload.size > MAX_UPLOAD_BYTES:
                self._uploads.pop(upload_id, None)
                raise EngineError("file_too_large", details={"bytes": upload.size})
            upload.chunks.append(payload)

            return {
                "received": len(upload.chunks),
                "total": upload.total,
                "bytes": upload.size,
                "complete": len(upload.chunks) == upload.total,
            }

    def take(self, upload_id: str) -> tuple[bytes, str | None]:
        """Consume a completed upload. The buffer is cleared either way."""
        with self._lock:
            self._expire_locked()
            upload = self._uploads.pop(upload_id, None)
        if upload is None:
            raise EngineError("upload_expired")
        if len(upload.chunks) != upload.total:
            raise EngineError(
                "invalid_args",
                "upload is incomplete",
                details={"received": len(upload.chunks), "total": upload.total},
            )
        return b"".join(upload.chunks), upload.filename

    def discard(self, upload_id: str) -> bool:
        with self._lock:
            return self._uploads.pop(upload_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            self._expire_locked()
            return len(self._uploads)

    def _expire_locked(self) -> None:
        now = time.monotonic()
        for key in [k for k, v in self._uploads.items() if now - v.started_at > self._ttl]:
            self._uploads.pop(key, None)
