"""Install the pinned public GodotSteam Android ARM64 binaries when needed."""

from __future__ import annotations

import hashlib
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

from steamworks_tools import is_android_arm64_library


GODOTSTEAM_VERSION = "4.23.1"
GODOTSTEAM_COMMIT = "87e9456ed0922d861d352cda823ee1bde682c987"
GODOTSTEAM_ASSET_URL = "https://godotengine.org/asset-library/asset/2445"
GODOTSTEAM_ARCHIVE_URL = (
    "https://codeberg.org/godotsteam/godotsteam/archive/"
    f"{GODOTSTEAM_COMMIT}.zip"
)
GODOTSTEAM_ARCHIVE_SHA256 = "0271ab46929363a186c147408e763b1f8b28acff7a36b6aebc4592e68a2739a5"
ANDROID_FILES = (
    "libgodotsteam.android.template_debug.arm64.so",
    "libgodotsteam.android.template_release.arm64.so",
    "libsteam_api.so",
)
PACKAGE_ROOT = "godotsteam/addons/godotsteam/androidarm64/"
MAX_ANDROID_LIBRARY_SIZE = 32 * 1024 * 1024


def package_cache_paths(cache_root: Path) -> tuple[Path, Path]:
    root = cache_root / "godotsteam" / GODOTSTEAM_VERSION
    return root, root / f"godotsteam-{GODOTSTEAM_COMMIT}.zip"


def has_verified_package_cache(cache_root: Path) -> bool:
    _root, archive = package_cache_paths(cache_root)
    if not archive.is_file():
        return False
    try:
        return _sha256_file(archive) == GODOTSTEAM_ARCHIVE_SHA256
    except OSError:
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_archive(destination: Path, progress) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        GODOTSTEAM_ARCHIVE_URL,
        headers={"User-Agent": "AVS03-Android-Builder/1.0", "Accept": "application/zip"},
    )
    received = 0
    last_update = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                received += len(block)
                now = time.monotonic()
                if now - last_update >= 0.8 or (total and received >= total):
                    if total:
                        progress(f"Downloading GodotSteam Android package: {received * 100 // total}%")
                    else:
                        progress(f"Downloading GodotSteam Android package: {received / (1024 * 1024):.0f} MiB")
                    last_update = now
        actual_hash = _sha256_file(partial)
        if actual_hash != GODOTSTEAM_ARCHIVE_SHA256:
            raise RuntimeError(
                "The downloaded GodotSteam package did not match its pinned SHA-256 checksum. "
                "It was discarded; retry later or inspect the build log."
            )
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def _validate_gdextension(project_dir: Path) -> None:
    descriptor = project_dir / "addons" / "godotsteam" / "godotsteam.gdextension"
    if not descriptor.is_file():
        raise RuntimeError("The recovered project is missing addons/godotsteam/godotsteam.gdextension.")
    text = descriptor.read_text(encoding="utf-8", errors="replace")
    if 'compatibility_minimum = "4.4"' not in text:
        raise RuntimeError(
            f"The public GodotSteam {GODOTSTEAM_VERSION} package targets Godot 4.4 or newer, "
            "but the recovered extension descriptor does not declare the expected 4.4 compatibility. "
            "No plugin files were replaced."
        )
    for filename in ANDROID_FILES:
        expected = f"res://addons/godotsteam/androidarm64/{filename}"
        if expected not in text:
            raise RuntimeError(
                f"The recovered GodotSteam descriptor does not declare {expected}. "
                "The public package cannot be installed safely into this project."
            )


def install_public_android_libraries(project_dir: Path, cache_root: Path, progress) -> list[Path]:
    """Install only the public package's three declared Android ARM64 binaries.

    A complete valid existing set is retained. If any file is missing or invalid,
    the three files are installed together to keep their versions matched. The
    archive is pinned by commit and SHA-256; no game files or non-Android package
    contents are uploaded or copied.
    """
    project_dir = project_dir.resolve()
    _validate_gdextension(project_dir)
    android_dir = project_dir / "addons" / "godotsteam" / "androidarm64"
    destinations = {name: android_dir / name for name in ANDROID_FILES}
    invalid = [name for name, path in destinations.items() if not is_android_arm64_library(path)]
    if not invalid:
        progress("Recovered project already has all valid Android ARM64 GodotSteam libraries.")
        return []

    package_root, archive_path = package_cache_paths(cache_root)
    package_root.mkdir(parents=True, exist_ok=True)
    if archive_path.is_file() and not has_verified_package_cache(cache_root):
        archive_path.unlink()
    if not archive_path.is_file():
        progress(f"Downloading pinned public GodotSteam {GODOTSTEAM_VERSION} package from Codeberg…")
        _download_archive(archive_path, progress)

    package_license: bytes | None = None
    installed: list[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            archive_path.unlink(missing_ok=True)
            raise RuntimeError(f"GodotSteam package archive failed its ZIP integrity check ({bad_member}).")
        for filename in ANDROID_FILES:
            member_name = PACKAGE_ROOT + filename
            try:
                member = archive.getinfo(member_name)
            except KeyError as exc:
                raise RuntimeError(f"Public GodotSteam package is missing {member_name}.") from exc
            if member.file_size <= 0 or member.file_size > MAX_ANDROID_LIBRARY_SIZE:
                raise RuntimeError(f"Public GodotSteam package has an invalid size for {filename}.")
            destination = destinations[filename]
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".download")
            try:
                with archive.open(member) as source, temporary.open("wb") as target:
                    shutil.copyfileobj(source, target)
                if not is_android_arm64_library(temporary):
                    raise RuntimeError(f"Public package file {filename} is not a 64-bit Android ARM64 ELF library.")
                temporary.replace(destination)
                installed.append(destination)
            finally:
                temporary.unlink(missing_ok=True)
        try:
            package_license = archive.read("godotsteam/addons/godotsteam/license.md")
        except KeyError:
            package_license = None

    if package_license:
        license_path = project_dir / "addons" / "godotsteam" / "license.md"
        if not license_path.exists():
            license_path.write_bytes(package_license)
    progress(
        f"Installed {len(installed)} Android ARM64 GodotSteam library file(s) "
        f"from public package {GODOTSTEAM_VERSION}."
    )
    return installed
