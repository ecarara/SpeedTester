# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Build Windows ICO and macOS ICNS files from versioned PNG icon sizes.

The generated containers keep PNG payloads, so this script only needs Python's
standard library and remains usable in minimal CI runners.
"""
from __future__ import annotations

from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
PNG_ROOT = ROOT / "assets" / "icons" / "hicolor"
WINDOWS_OUTPUT = ROOT / "assets" / "packaging" / "windows" / "SpeedTester.ico"
MACOS_OUTPUT = ROOT / "assets" / "packaging" / "macos" / "SpeedTester.icns"


def png_path(size: int) -> Path:
    return PNG_ROOT / str(size) / "apps" / "speedtester.png"


def png_dimensions(payload: bytes) -> tuple[int, int]:
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError("arquivo não é um PNG com cabeçalho válido")
    return struct.unpack(">II", payload[16:24])


def build_ico() -> None:
    sizes = (16, 32, 48, 64, 128, 256)
    payloads = [png_path(size).read_bytes() for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(payloads))
    entries = bytearray()
    offset = 6 + 16 * len(payloads)
    for payload in payloads:
        width, height = png_dimensions(payload)
        entries.extend(
            struct.pack(
                "<BBBBHHII",
                0 if width == 256 else width,
                0 if height == 256 else height,
                0,
                0,
                1,
                32,
                len(payload),
                offset,
            )
        )
        offset += len(payload)
    WINDOWS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    WINDOWS_OUTPUT.write_bytes(header + entries + b"".join(payloads))


def icns_chunk(kind: str, payload: bytes) -> bytes:
    return struct.pack(">4sI", kind.encode("ascii"), len(payload) + 8) + payload


def build_icns() -> None:
    chunks = []
    for kind, size in (
        ("icp4", 16),
        ("icp5", 32),
        ("icp6", 48),
        ("ic07", 128),
        ("ic08", 256),
        ("ic09", 512),
        ("ic10", 1024),
    ):
        path = png_path(size) if size != 1024 else ROOT / "assets" / "packaging" / "macos" / "speedtester.iconset" / "icon_512x512@2x.png"
        chunks.append(icns_chunk(kind, path.read_bytes()))
    body = b"".join(chunks)
    MACOS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MACOS_OUTPUT.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> None:
    build_ico()
    build_icns()
    print(f"generated {WINDOWS_OUTPUT.relative_to(ROOT)}")
    print(f"generated {MACOS_OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
