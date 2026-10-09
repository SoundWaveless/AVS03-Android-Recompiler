"""Secure, OS-aware GitHub release checks and in-place builder updates."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable


REPOSITORY = "SoundWaveless/AVS03-Android-Recompiler"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
APP_VERSION = "0.1.3"
MAX_ARCHIVE_BYTES = 300 * 1024 * 1024
MAX_EXPANDED_BYTES = 600 * 1024 * 1024


class UpdateError(RuntimeError):
    pass


def parse_version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise UpdateError(f"Unsupported release version format: {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def current_platform_asset_name(system: str | None = None, machine: str | None = None, sdk_downloader: bool = False) -> str:
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == "Windows":
        suffix = "Windows-SDK-Downloader-Source.zip" if sdk_downloader else "Windows-Source.zip"
        return f"AVS03-Android-Builder-{suffix}"
    if system == "Linux":
        if machine not in {"x86_64", "amd64"}:
            raise UpdateError(f"No Linux builder package is available for {machine or 'this architecture'}.")
        return "AVS03-Android-Builder-Linux-SDK-Downloader.zip" if sdk_downloader else "AVS03-Android-Builder-Linux-x86_64.zip"
    raise UpdateError(f"Automatic updates are not available for {system}.")


def check_latest_release(
    current_version: str = APP_VERSION,
    sdk_downloader: bool = False,
    api_url: str = LATEST_RELEASE_API,
) -> dict[str, object]:
    request = urllib.request.Request(
        api_url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "AVS03-Compiler-Updater"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateError(f"Could not check GitHub for updates: {exc}") from exc
    tag = str(data.get("tag_name", ""))
    latest_tuple = parse_version(tag)
    current_tuple = parse_version(current_version)
    asset_name = current_platform_asset_name(sdk_downloader=sdk_downloader)
    assets = data.get("assets", [])
    asset = next((entry for entry in assets if entry.get("name") == asset_name), None)
    if latest_tuple > current_tuple and asset is None:
        raise UpdateError(f"Release {tag} does not include the package for this operating system and edition ({asset_name}).")
    digest = str(asset.get("digest", "")) if asset else ""
    if latest_tuple > current_tuple and not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise UpdateError(f"Release {tag} does not provide a verifiable SHA-256 digest for {asset_name}.")
    return {
        "current_version": current_version,
        "latest_version": tag.removeprefix("v"),
        "available": latest_tuple > current_tuple,
        "release_url": str(data.get("html_url", f"https://github.com/{REPOSITORY}/releases/latest")),
        "asset_name": asset_name,
        "download_url": str(asset.get("browser_download_url", "")) if asset else "",
        "sha256": digest.removeprefix("sha256:").lower(),
        "size": int(asset.get("size", 0)) if asset else 0,
    }


def download_release_asset(update: dict[str, object], destination: Path, progress: Callable[[int, int], None] | None = None) -> Path:
    expected_size = int(update.get("size", 0))
    if expected_size <= 0 or expected_size > MAX_ARCHIVE_BYTES:
        raise UpdateError("The release asset has an invalid or unsafe download size.")
    request = urllib.request.Request(
        str(update["download_url"]),
        headers={"Accept": "application/octet-stream", "User-Agent": "AVS03-Compiler-Updater"},
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=30) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_ARCHIVE_BYTES:
                    raise UpdateError("The release download exceeded the allowed size.")
                digest.update(chunk)
                output.write(chunk)
                if progress:
                    progress(downloaded, expected_size)
        if downloaded != expected_size:
            raise UpdateError(f"The download size did not match GitHub's metadata ({downloaded} of {expected_size} bytes).")
        if digest.hexdigest() != str(update["sha256"]).lower():
            raise UpdateError("The downloaded update failed SHA-256 verification. No files were installed.")
        temporary.replace(destination)
        return destination
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def get_install_directory(script_file: str | Path | None = None, executable: str | Path | None = None, frozen: bool | None = None) -> Path:
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        return Path(executable or sys.executable).resolve().parent
    return Path(script_file or __file__).resolve().parent


def detect_sdk_downloader(install_dir: Path, executable: str | Path | None = None) -> bool:
    config = install_dir / "edition_config.py"
    try:
        source = config.read_text(encoding="utf-8")
        match = re.search(r"SDK_DOWNLOADER_EDITION\s*=\s*(True|False)", source)
        if match:
            return match.group(1) == "True"
    except OSError:
        pass
    name = Path(executable or sys.executable).name.lower()
    return "sdk-downloader" in name or "sdk_downloader" in name


def get_installed_version(install_dir: Path, fallback: str = APP_VERSION) -> str:
    try:
        version = (install_dir / "VERSION").read_text(encoding="utf-8").strip()
        parse_version(version)
        return version.removeprefix("v")
    except OSError:
        return fallback.removeprefix("v")


def install_release_package(archive: Path, install_dir: Path) -> list[Path]:
    """Verify package layout and atomically replace package files, rolling back on errors."""
    install_dir = install_dir.resolve()
    if not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise UpdateError("The update archive is missing or exceeds the allowed size.")
    install_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".avs03-update-", dir=install_dir))
    replaced: list[tuple[Path, Path | None]] = []
    installed: list[Path] = []
    try:
        with zipfile.ZipFile(archive) as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            if not infos or sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
                raise UpdateError("The update archive is empty or expands beyond the safety limit.")
            expected_root = str(update_package_root(infos[0].filename))
            if not expected_root or any(str(update_package_root(info.filename)) != expected_root for info in infos):
                raise UpdateError("The update archive has an unexpected folder structure.")
            payload = stage / "payload"
            payload.mkdir()
            for info in infos:
                relative = safe_archive_path(info.filename, expected_root)
                if relative is None:
                    continue
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode and (mode & 0o170000) == 0o120000:
                    raise UpdateError("The update archive contains a symbolic link, which is not allowed.")
                destination = payload.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                if mode & 0o111:
                    destination.chmod(destination.stat().st_mode | 0o111)
        files = [path for path in payload.rglob("*") if path.is_file()]
        if not files:
            raise UpdateError("The update archive did not contain installable files.")
        backup = stage / "backup"
        for source in files:
            relative = source.relative_to(payload)
            destination = install_dir / relative
            if install_dir not in destination.resolve().parents:
                raise UpdateError("An update path would leave the application folder.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            old_copy: Path | None = None
            if destination.exists():
                if not destination.is_file() or destination.is_symlink():
                    raise UpdateError(f"Refusing to replace a non-regular application path: {destination}")
                old_copy = backup / relative
                old_copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, old_copy)
            temporary = destination.with_name(destination.name + ".avs03-new")
            shutil.copy2(source, temporary)
            try:
                os.replace(temporary, destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            replaced.append((destination, old_copy))
            installed.append(destination)
        return installed
    except Exception as exc:
        rollback_errors = []
        for destination, old_copy in reversed(replaced):
            try:
                if old_copy is None:
                    destination.unlink(missing_ok=True)
                else:
                    restore = destination.with_name(destination.name + ".avs03-restore")
                    shutil.copy2(old_copy, restore)
                    os.replace(restore, destination)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if isinstance(exc, UpdateError):
            detail = str(exc)
        else:
            detail = f"Could not install the update: {exc}"
        if rollback_errors:
            detail += "\nSome files could not be restored: " + "; ".join(rollback_errors)
        raise UpdateError(detail) from exc
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def update_package_root(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    return PurePosixPath(path.parts[0]) if path.parts else PurePosixPath("")


def safe_archive_path(name: str, root: str) -> PurePosixPath | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != root:
        raise UpdateError("The update archive contains an unsafe file path.")
    relative = PurePosixPath(*path.parts[1:])
    return relative if relative.parts else None
