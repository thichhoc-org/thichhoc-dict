"""dictzip writer — gzip with a random-access index.

A ``.dict.dz`` is a normal gzip file whose FEXTRA field carries an 'RA'
subfield listing the compressed length of every fixed-size chunk of the
original data. A reader seeking to offset N inflates only the one chunk that
contains it instead of the whole 40 MB dictionary — which is the difference
between an instant lookup and a multi-second stall on a Kindle's CPU.

Any gzip tool can still decompress the result; the index is purely additive.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

#: The de-facto standard chunk size, as used by the reference dictzip. Readers
#: take it from the header, but staying conventional avoids surprises.
CHUNK_SIZE = 58315

_GZIP_MAGIC = b"\x1f\x8b"
_DEFLATE = 8
_FEXTRA = 0x04
_FNAME = 0x08
_OS_UNIX = 3

#: The extra field length is a 16-bit value, and the 'RA' header costs 10 bytes
#: on top of 2 bytes per chunk.
MAX_CHUNKS = (0xFFFF - 10) // 2


def compress(data: bytes, *, filename: str = "", mtime: int = 0, level: int = 9) -> bytes:
    """Compress ``data`` into dictzip format.

    ``mtime`` defaults to 0 rather than the current time so that building the
    same corpus twice produces byte-identical output.
    """
    chunk_count = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE or 1
    if chunk_count > MAX_CHUNKS:
        raise ValueError(
            f"{len(data)} bytes needs {chunk_count} chunks, but a single dictzip "
            f"member holds at most {MAX_CHUNKS}"
        )

    # One deflate stream, with a full flush at each chunk boundary so that each
    # chunk can be inflated independently. Compressing chunks as separate
    # streams would also work but costs ~5% ratio.
    compressor = zlib.compressobj(level, zlib.DEFLATED, -zlib.MAX_WBITS)
    parts: list[bytes] = []
    sizes: list[int] = []
    for offset in range(0, len(data), CHUNK_SIZE) or [0]:
        piece = compressor.compress(data[offset : offset + CHUNK_SIZE])
        piece += compressor.flush(zlib.Z_FULL_FLUSH)
        parts.append(piece)
        sizes.append(len(piece))
    tail = compressor.flush(zlib.Z_FINISH)

    if not parts:  # empty input still needs one (empty) chunk
        parts, sizes = [b""], [0]
    # The final deflate trailer belongs to the last chunk's byte range.
    parts[-1] += tail
    sizes[-1] += len(tail)

    if any(size > 0xFFFF for size in sizes):
        raise ValueError("a chunk compressed to more than 64 KiB; lower CHUNK_SIZE")

    # 'RA' subfield: version(2) chunk_len(2) chunk_count(2) then the sizes.
    ra = struct.pack("<HHH", 1, CHUNK_SIZE, len(sizes))
    ra += b"".join(struct.pack("<H", size) for size in sizes)
    extra = b"RA" + struct.pack("<H", len(ra)) + ra

    flags = _FEXTRA | (_FNAME if filename else 0)
    header = _GZIP_MAGIC + bytes([_DEFLATE, flags])
    header += struct.pack("<I", mtime)
    header += bytes([2, _OS_UNIX])  # XFL=2 (best compression), OS=Unix
    header += struct.pack("<H", len(extra)) + extra
    if filename:
        header += filename.encode("utf-8") + b"\x00"

    trailer = struct.pack("<II", zlib.crc32(data) & 0xFFFFFFFF, len(data) & 0xFFFFFFFF)
    return header + b"".join(parts) + trailer


def write(path: Path, data: bytes, *, level: int = 9) -> Path:
    """Write ``data`` to ``path`` (which should end in ``.dz``)."""
    path.write_bytes(compress(data, filename=path.stem, level=level))
    return path


__all__ = ["compress", "write", "CHUNK_SIZE"]
