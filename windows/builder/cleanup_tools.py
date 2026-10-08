"""Safely remove AVS03-managed downloads and generated recovery workspaces."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from tool_setup import TOOLS_ROOT


DOWNLOAD_DIRS = ("gdre", "jdk17", "godot", "godot-config", "godot-data", "godotsteam")


def _size(path: Path) -> int:
    if path.is_symlink():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    if path.is_dir():
        for current, dirs, files in os.walk(path, followlinks=False):
            current_path = Path(current)
            for name in files:
                try:
                    total += (current_path / name).lstat().st_size
                except OSError:
                    pass
            for name in dirs:
                child = current_path / name
                if child.is_symlink():
                    try:
                        total += child.lstat().st_size
                    except OSError:
                        pass
    return total


def cleanup_inventory(include_managed_sdk: bool = False) -> list[tuple[str, list[Path], int]]:
    """Return named, known AVS03-owned locations and their current sizes."""
    categories: list[tuple[str, list[Path]]] = [
        ("Downloaded build tools and public GodotSteam package cache", [TOOLS_ROOT / name for name in DOWNLOAD_DIRS]),
        ("Recovered game project workspaces", [TOOLS_ROOT / "workspaces"]),
        ("Temporary Godot and GDRE profiles", [Path(tempfile.gettempdir()) / "avs03-godot-builder-profile", Path(tempfile.gettempdir()) / "avs03-gdre-profile"]),
    ]
    if include_managed_sdk:
        categories.append(("Android SDK in the AVS03-managed folder", [TOOLS_ROOT / "android-sdk"]))
    result = []
    for title, paths in categories:
        existing = [path for path in paths if path.exists() or path.is_symlink()]
        result.append((title, existing, sum(_size(path) for path in existing)))
    return result


def remove_managed_files(
    *,
    remove_downloads: bool,
    remove_workspaces: bool,
    remove_temp_profiles: bool = False,
    remove_managed_sdk: bool = False,
) -> tuple[int, list[str]]:
    """Remove only fixed AVS03-owned paths beneath TOOLS_ROOT; never follows symlinks."""
    allowed_parents = {TOOLS_ROOT.resolve(), Path(tempfile.gettempdir()).resolve()}
    selected: list[Path] = []
    if remove_downloads:
        selected.extend(TOOLS_ROOT / name for name in DOWNLOAD_DIRS)
    if remove_workspaces:
        selected.append(TOOLS_ROOT / "workspaces")
    if remove_temp_profiles:
        selected.extend((Path(tempfile.gettempdir()) / "avs03-godot-builder-profile", Path(tempfile.gettempdir()) / "avs03-gdre-profile"))
    if remove_managed_sdk:
        selected.append(TOOLS_ROOT / "android-sdk")
    removed_bytes = 0
    errors: list[str] = []
    for path in selected:
        if path.parent.resolve() not in allowed_parents:
            errors.append(f"Skipped unexpected path outside builder data folder: {path}")
            continue
        if not path.exists() and not path.is_symlink():
            continue
        removed_bytes += _size(path)
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        except OSError as exc:
            errors.append(f"Could not remove {path}: {exc}")
    if remove_managed_sdk:
        sdk_record = TOOLS_ROOT / "android-sdk-path.txt"
        if sdk_record.is_file():
            try:
                recorded = Path(sdk_record.read_text(encoding="utf-8").strip()).expanduser().resolve()
                managed = (TOOLS_ROOT / "android-sdk").resolve()
                if recorded == managed:
                    removed_bytes += sdk_record.stat().st_size
                    sdk_record.unlink()
            except (OSError, RuntimeError):
                pass
    return removed_bytes, errors


def format_bytes(size: int) -> str:
    amount = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} TB"
