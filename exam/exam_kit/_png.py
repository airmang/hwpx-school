"""합성 PNG(RGB, 무압축 필터 0) — 프리뷰 세척·테스트 픽스처용."""

from __future__ import annotations

import struct
import zlib


def png(폭: int = 1, 높이: int = 1, 색: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    def 청크(태그: bytes, 몸통: bytes) -> bytes:
        return struct.pack(">I", len(몸통)) + 태그 + 몸통 + struct.pack(">I", zlib.crc32(태그 + 몸통) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(색) * 폭 for _ in range(높이))
    return (b"\x89PNG\r\n\x1a\n" + 청크(b"IHDR", struct.pack(">IIBBBBB", 폭, 높이, 8, 2, 0, 0, 0))
            + 청크(b"IDAT", zlib.compress(raw)) + 청크(b"IEND", b""))
