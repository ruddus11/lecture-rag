"""파일 저장소: UUID 파일명, DATA_DIR 하위 경로 검증, Range 읽기 (설계서 13장)."""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

CHUNK = 1024 * 1024


class FileTooLarge(Exception):
    pass


class FileStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.resolve()
        self.root = (data_dir / "files").resolve()
        self.tmp = self.root / "tmp"

    def ensure_dirs(self) -> None:
        self.tmp.mkdir(parents=True, exist_ok=True)

    def _inside(self, path: Path) -> Path:
        p = path.resolve()
        if p != self.data_dir and self.data_dir not in p.parents:
            raise ValueError("path escapes DATA_DIR")
        return p

    def path_for(self, document_id: str) -> Path:
        uuid.UUID(document_id)  # UUID 가 아니면 ValueError
        return self._inside(self.root / f"{document_id}.pdf")

    def save_temp(self, stream: BinaryIO, max_bytes: int) -> tuple[Path, str, int, bytes]:
        """임시 파일로 저장하며 sha256·크기를 계산한다. 반환: (임시경로, sha256, 크기, 선두 8바이트)."""
        self.ensure_dirs()
        tmp = self._inside(self.tmp / f"{uuid.uuid4()}.part")
        h = hashlib.sha256()
        size = 0
        head = b""
        try:
            with tmp.open("wb") as f:
                while True:
                    buf = stream.read(CHUNK)
                    if not buf:
                        break
                    if len(head) < 8:
                        head = (head + buf[: 8 - len(head)])[:8]
                    size += len(buf)
                    if size > max_bytes:
                        raise FileTooLarge()
                    h.update(buf)
                    f.write(buf)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return tmp, h.hexdigest(), size, head

    def commit(self, tmp: Path, document_id: str) -> Path:
        dest = self.path_for(document_id)
        os.replace(self._inside(tmp), dest)
        return dest

    def resolve_stored(self, storage_path: str) -> Path:
        return self._inside(Path(storage_path))

    def open_range(self, storage_path: str, start: int, end: int) -> Iterator[bytes]:
        """[start, end] (포함) 범위를 CHUNK 단위로 읽는다."""
        path = self.resolve_stored(storage_path)
        remaining = end - start + 1
        with path.open("rb") as f:
            f.seek(start)
            while remaining > 0:
                buf = f.read(min(CHUNK, remaining))
                if not buf:
                    break
                remaining -= len(buf)
                yield buf

    def delete(self, storage_path: str) -> None:
        self.resolve_stored(storage_path).unlink(missing_ok=True)

    def discard(self, tmp: Path) -> None:
        self._inside(tmp).unlink(missing_ok=True)
