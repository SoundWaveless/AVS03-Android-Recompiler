"""Validate Android ARM64 ELF libraries used by the GodotSteam package installer."""

from __future__ import annotations

import struct
from pathlib import Path


def is_android_arm64_library(path: Path) -> bool:
    """Check for a 64-bit little-endian ELF shared library for AArch64."""
    try:
        with path.open("rb") as stream:
            header = stream.read(20)
    except OSError:
        return False
    return (
        len(header) >= 20
        and header[:4] == b"\x7fELF"
        and header[4] == 2  # ELFCLASS64
        and header[5] == 1  # ELFDATA2LSB
        and struct.unpack_from("<H", header, 18)[0] == 183  # EM_AARCH64
    )

