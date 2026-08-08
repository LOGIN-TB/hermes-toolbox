#!/usr/bin/env python3
"""Generate GymPilot PNG app icons using only the Python standard library."""
from __future__ import annotations

import binascii
from pathlib import Path
import struct
import zlib

OUT = Path(__file__).resolve().parent.parent / "assets" / "web" / "icons"


def chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)


def inside_round_rect(x: int, y: int, size: int) -> bool:
    radius = size * 0.22
    if radius <= x < size - radius or radius <= y < size - radius:
        return True
    cx = radius if x < radius else size - radius - 1
    cy = radius if y < radius else size - radius - 1
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def icon(size: int) -> bytes:
    bg = (17, 18, 23, 255)
    transparent = (0, 0, 0, 0)
    violet = (141, 137, 255, 255)
    white = (245, 247, 250, 255)
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            color = bg if inside_round_rect(x, y, size) else transparent
            scale = size / 512
            # Bar and four plates, proportionally matching the source SVG.
            if abs(y - size / 2) <= 18 * scale and 84 * scale <= x <= 428 * scale:
                color = violet
            for cx, half_height, half_width in ((104, 50, 18), (64, 14, 18), (408, 50, 18), (448, 14, 18)):
                if abs(x - cx * scale) <= half_width * scale and abs(y - size / 2) <= half_height * scale:
                    color = violet
            if (x - size / 2) ** 2 + (y - size / 2) ** 2 <= (48 * scale) ** 2:
                color = white
            row.extend(color)
        rows.append(bytes(row))
    raw = b"".join(rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512),
                       ("apple-touch-icon.png", 180), ("favicon-32.png", 32)):
        (OUT / name).write_bytes(icon(size))


if __name__ == "__main__":
    main()
