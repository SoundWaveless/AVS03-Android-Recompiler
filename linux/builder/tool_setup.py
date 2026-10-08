"""Download and cache the official tools needed for AVS03 Android exports."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


if platform.system() == "Windows":
    _data_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
else:
    _data_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
TOOLS_ROOT = _data_root / "AVS03-Android-Port-Builder" / "tools"
ANDROID_PACKAGES = {
    "platform-tools": "platform-tools",
    "build-tools": "build-tools/35.0.1",
    "platform": "platforms/android-35",
    "cmake": "cmake/3.10.2.4988404",
    "ndk": "ndk/28.1.13356709",
}
ANDROID_CLI_PACKAGE_IDS = (
    "platform-tools",
    "build-tools/35.0.1",
    "platforms/android-35",
    "cmake/3.10.2.4988404",
    "ndk/28.1.13356709",
)
ANDROID_SDKMANAGER_PACKAGE_IDS = (
    "platform-tools",
    "build-tools;35.0.1",
    "platforms;android-35",
    "cmake;3.10.2.4988404",
    "ndk;28.1.13356709",
)


def _request(url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": "AVS03-Android-Port-Builder", "Accept": accept})


def _download(url: str, destination: Path, progress) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = _request(url, "application/octet-stream")
    with urllib.request.urlopen(request, timeout=45) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0"))
        received = 0
        last_reported_at = time.monotonic()
        started_at = last_reported_at
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            received += len(chunk)
            now = time.monotonic()
            if now - last_reported_at >= 0.8 or (total and received >= total):
                elapsed = max(now - started_at, 0.001)
                transferred = received / (1024 * 1024)
                speed = transferred / elapsed
                if total:
                    total_mib = total / (1024 * 1024)
                    percent = received * 100 // total
                    progress(f"Downloading {destination.name}: {percent}% ({transferred:.0f}/{total_mib:.0f} MiB at {speed:.1f} MiB/s)")
                else:
                    progress(f"Downloading {destination.name}: {transferred:.0f} MiB received at {speed:.1f} MiB/s")
                last_reported_at = now


def _safe_extract_zip(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if target != base and base not in target.parents:
                raise RuntimeError(f"Unsafe path in downloaded archive: {member.filename}")
        archive.extractall(destination)


def _safe_extract_tar(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != base and base not in target.parents:
                raise RuntimeError(f"Unsafe path in downloaded archive: {member.name}")
            if member.issym():
                link_target = (target.parent / member.linkname).resolve()
                if link_target != base and base not in link_target.parents:
                    raise RuntimeError(f"Unsafe symbolic link in downloaded archive: {member.name}")
            elif member.islnk():
                link_target = (base / member.linkname).resolve()
                if link_target != base and base not in link_target.parents:
                    raise RuntimeError(f"Unsafe hard link in downloaded archive: {member.name}")
        archive.extractall(destination)


def _github_release(repo: str, tag: str | None = None) -> dict:
    suffix = f"/tags/{tag}" if tag else "/latest"
    with urllib.request.urlopen(_request(f"https://api.github.com/repos/{repo}/releases{suffix}"), timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _asset(release: dict, predicate, description: str) -> dict:
    found = [item for item in release.get("assets", []) if predicate(item.get("name", "").lower())]
    if not found:
        raise RuntimeError(f"The official release did not provide a compatible {description} download.")
    return found[0]


def _install_gdre(progress) -> Path:
    windows = platform.system() == "Windows"
    platform_word = "windows" if windows else "linux"
    root = TOOLS_ROOT / "gdre"
    candidates = list(root.rglob("gdre_tools.exe" if windows else "gdre_tools.x86_64")) if root.exists() else []
    if candidates:
        return candidates[0]
    progress("Finding the official GDRE Tools release…")
    release = _github_release("GDRETools/gdsdecomp")
    asset = _asset(release, lambda name: "gdre_tools" in name and platform_word in name and name.endswith(".zip"), "GDRE Tools")
    with tempfile.TemporaryDirectory(prefix="avs03-gdre-") as temp:
        archive = Path(temp) / asset["name"]
        _download(asset["browser_download_url"], archive, progress)
        _safe_extract_zip(archive, root)
    candidates = list(root.rglob("gdre_tools.exe" if windows else "gdre_tools.x86_64"))
    if not candidates and not windows:
        candidates = [path for path in root.rglob("gdre_tools*") if path.is_file() and os.access(path, os.X_OK)]
    if not candidates:
        raise RuntimeError("GDRE Tools downloaded, but its command-line executable was not found.")
    if not windows:
        candidates[0].chmod(candidates[0].stat().st_mode | 0o111)
    return candidates[0]


def _install_jdk(progress) -> Path:
    windows = platform.system() == "Windows"
    root = TOOLS_ROOT / "jdk17"
    java_name = "java.exe" if windows else "java"
    candidates = list(root.rglob(java_name)) if root.exists() else []
    if candidates:
        return candidates[0].parent.parent
    os_name = "windows" if windows else "linux"
    arch = "x64"
    url = f"https://api.adoptium.net/v3/binary/latest/17/ga/{os_name}/{arch}/jdk/hotspot/normal/eclipse"
    suffix = ".zip" if windows else ".tar.gz"
    with tempfile.TemporaryDirectory(prefix="avs03-jdk-") as temp:
        archive = Path(temp) / f"jdk17{suffix}"
        progress("Downloading OpenJDK 17…")
        _download(url, archive, progress)
        if windows:
            _safe_extract_zip(archive, root)
        else:
            _safe_extract_tar(archive, root)
    candidates = list(root.rglob(java_name))
    if not candidates:
        raise RuntimeError("OpenJDK 17 downloaded, but java was not found in the archive.")
    if not windows:
        candidates[0].chmod(candidates[0].stat().st_mode | 0o111)
    return candidates[0].parent.parent


def detect_android_sdk() -> Path | None:
    """Find a locally installed Android SDK without downloading or modifying it."""
    candidates = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")]
    if platform.system() == "Windows":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        candidates.append(str(local_app_data / "Android" / "Sdk"))
    else:
        candidates.append(str(Path.home() / "Android" / "Sdk"))
    for candidate in candidates:
        if candidate:
            path = Path(candidate).expanduser()
            if path.is_dir():
                return path
    return None


def validate_android_sdk(sdk: Path) -> list[str]:
    """Return missing required components for the selected, user-managed SDK."""
    sdk = sdk.expanduser().resolve()
    if not sdk.is_dir():
        return [f"SDK folder does not exist: {sdk}"]
    missing = [label for label, relative in ANDROID_PACKAGES.items() if not (sdk / relative).is_dir()]
    return missing


def _install_android_sdk(progress, accept_licenses: bool, jdk: Path) -> Path:
    """Download the official Google command-line tools, then install selected packages."""
    if not accept_licenses:
        raise RuntimeError("SDK installation was not authorized by the user.")
    sdk = TOOLS_ROOT / "android-sdk"
    windows = platform.system() == "Windows"
    tool_bin = sdk / "cmdline-tools" / "latest" / "bin"
    android_cli = next(
        (candidate for candidate in (tool_bin / "android.exe", tool_bin / "android.bat", tool_bin / "android") if candidate.exists()),
        tool_bin / ("android.exe" if windows else "android"),
    )
    sdkmanager = tool_bin / ("sdkmanager.bat" if windows else "sdkmanager")
    if not android_cli.exists() and not sdkmanager.exists():
        progress("Finding the official Android command-line tools package…")
        with urllib.request.urlopen(_request("https://dl.google.com/android/repository/repository2-1.xml", "application/xml"), timeout=45) as response:
            xml_root = ET.fromstring(response.read())
        host = "windows" if windows else "linux"
        package = next((node for node in xml_root.findall(".//{*}remotePackage") if node.attrib.get("path") == "cmdline-tools;latest"), None)
        archive_info = None
        if package is not None:
            for archive in package.findall("./{*}archives/{*}archive"):
                host_os = archive.findtext("{*}host-os")
                complete = archive.find("{*}complete")
                url_node = complete.find("{*}url") if complete is not None else None
                if host_os == host and url_node is not None:
                    archive_info = url_node.text
                    break
        if not archive_info:
            raise RuntimeError("Google's Android repository did not list command-line tools for this operating system.")
        with tempfile.TemporaryDirectory(prefix="avs03-android-cli-") as temp:
            archive = Path(temp) / "android-commandline-tools.zip"
            _download("https://dl.google.com/android/repository/" + archive_info, archive, progress)
            staging = Path(temp) / "unpacked"
            _safe_extract_zip(archive, staging)
            source = staging / "cmdline-tools"
            if not source.is_dir():
                raise RuntimeError("Android command-line tools archive did not contain cmdline-tools/.")
            tool_bin.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, sdk / "cmdline-tools" / "latest", dirs_exist_ok=True)
        android_cli = next(
            (candidate for candidate in (tool_bin / "android.exe", tool_bin / "android.bat", tool_bin / "android") if candidate.exists()),
            tool_bin / ("android.exe" if windows else "android"),
        )
        sdkmanager = tool_bin / ("sdkmanager.bat" if windows else "sdkmanager")
    if not windows and sdkmanager.exists():
        for launcher in sdkmanager.parent.iterdir():
            if launcher.is_file():
                launcher.chmod(launcher.stat().st_mode | 0o111)
    env = os.environ.copy()
    env["ANDROID_HOME"] = str(sdk)
    env["ANDROID_SDK_ROOT"] = str(sdk)
    env["JAVA_HOME"] = str(jdk)
    env["PATH"] = str(jdk / "bin") + os.pathsep + env.get("PATH", "")
    if android_cli.exists():
        progress("Installing the approved Android SDK packages with Google's Android CLI…")
        install_args = [str(android_cli), f"--sdk={sdk}", "--no-metrics", "sdk", "install", *ANDROID_CLI_PACKAGE_IDS]
        install_input = "y\n" * 40
    else:
        progress("Accepting Android SDK package licenses you approved in the download prompt…")
        license_args = [str(sdkmanager), f"--sdk_root={sdk}", "--licenses"]
        license_cmd = subprocess.list2cmdline(license_args) if windows else license_args
        license_process = subprocess.run(license_cmd, shell=windows, input=("y\n" * 40), text=True, capture_output=True, env=env)
        if license_process.returncode != 0:
            raise RuntimeError("Android SDK license setup failed.\n" + license_process.stdout[-2500:] + license_process.stderr[-2500:])
        progress("Installing approved Android SDK packages with sdkmanager…")
        install_args = [str(sdkmanager), f"--sdk_root={sdk}", "--install", *ANDROID_SDKMANAGER_PACKAGE_IDS]
        install_input = None
    install = subprocess.Popen(
        subprocess.list2cmdline(install_args) if windows else install_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        stdin=subprocess.PIPE if install_input is not None else None,
        env=env,
        shell=windows,
    )
    assert install.stdout is not None
    output_lines = []
    if install_input is not None and install.stdin is not None:
        try:
            install.stdin.write(install_input)
            install.stdin.close()
        except BrokenPipeError:
            pass
    for line in install.stdout:
        output_lines.append(line)
        if line.strip():
            progress(line.strip()[:180])
    if install.wait() != 0:
        raise RuntimeError("Android SDK package installation failed.\n" + "".join(output_lines)[-4000:])
    missing = validate_android_sdk(sdk)
    if missing:
        details = "".join(output_lines)[-3000:]
        raise RuntimeError(
            "Android SDK installation finished but these components are still missing: "
            + ", ".join(missing)
            + ("\n\nAndroid CLI output:\n" + details if details else "")
        )
    return sdk


def _godot_release(minor: str) -> dict:
    releases = []
    page = 1
    while page <= 3:
        url = f"https://api.github.com/repos/godotengine/godot/releases?per_page=100&page={page}"
        with urllib.request.urlopen(_request(url), timeout=45) as response:
            batch = json.loads(response.read().decode("utf-8"))
        releases.extend(batch)
        matches = [release for release in releases if re.fullmatch(rf"{re.escape(minor)}\.\d+-stable", release.get("tag_name", ""))]
        if matches:
            def patch_number(release):
                return int(release["tag_name"].split(".")[-1].split("-")[0])
            return max(matches, key=patch_number)
        if len(batch) < 100:
            break
        page += 1
    raise RuntimeError(f"No stable Godot release for project version {minor}.x was found.")


def _install_godot(project_dir: Path, progress) -> tuple[Path, str]:
    config = (project_dir / "project.godot").read_text(encoding="utf-8", errors="replace")
    feature_line = re.search(r'(?m)^config/features=.*?"(\d+\.\d+)"', config)
    minor = feature_line.group(1) if feature_line else "4.7"
    release = _godot_release(minor)
    version = release["tag_name"].removesuffix("-stable")
    editor_root = TOOLS_ROOT / "godot" / version
    windows = platform.system() == "Windows"
    executable = editor_root / (f"Godot_v{version}-stable_win64.exe" if windows else f"Godot_v{version}-stable_linux.x86_64")
    if not executable.exists():
        asset = _asset(
            release,
            lambda name: name.startswith(f"godot_v{version}-stable_") and (("win64.exe.zip" in name) if windows else ("linux.x86_64.zip" in name)),
            "Godot editor",
        )
        with tempfile.TemporaryDirectory(prefix="avs03-godot-") as temp:
            archive = Path(temp) / asset["name"]
            progress(f"Downloading Godot {version} editor…")
            _download(asset["browser_download_url"], archive, progress)
            _safe_extract_zip(archive, editor_root)
    if not executable.exists():
        candidates = list(editor_root.rglob("Godot_v*.exe" if windows else "Godot_v*linux.x86_64"))
        if not candidates:
            raise RuntimeError(f"Godot {version} was downloaded, but its editor executable was not found.")
        executable = candidates[0]
    if not windows:
        executable.chmod(executable.stat().st_mode | 0o111)

    templates = _asset(release, lambda name: name.endswith("_export_templates.tpz"), "Godot export templates")
    if windows:
        templates_root = TOOLS_ROOT / "godot-config" / "Godot" / "export_templates" / f"{version}.stable"
    else:
        templates_root = TOOLS_ROOT / "godot-data" / "godot" / "export_templates" / f"{version}.stable"
    if not (templates_root / "android_debug.apk").exists():
        with tempfile.TemporaryDirectory(prefix="avs03-templates-") as temp:
            archive = Path(temp) / templates["name"]
            progress(f"Downloading Godot {version} Android export templates…")
            _download(templates["browser_download_url"], archive, progress)
            _safe_extract_zip(archive, Path(temp) / "unzipped")
            source = Path(temp) / "unzipped" / "templates"
            if not source.is_dir():
                raise RuntimeError("Godot export template archive did not contain templates/.")
            shutil.copytree(source, templates_root, dirs_exist_ok=True)
    return executable, version


def ensure_gdre_tool(progress) -> Path:
    """Ensure GDRE Tools is installed and return its CLI executable."""
    TOOLS_ROOT.mkdir(parents=True, exist_ok=True)
    return _install_gdre(progress)


def setup_export_tools(
    project_dir: Path,
    progress,
    android_sdk: Path,
    allow_sdk_download: bool = False,
    accepted_sdk_licenses: bool = False,
) -> dict[str, Path | str]:
    """Prepare export tools, optionally installing the Android SDK after user consent."""
    TOOLS_ROOT.mkdir(parents=True, exist_ok=True)
    jdk = _install_jdk(progress)
    missing = validate_android_sdk(android_sdk)
    if missing:
        if allow_sdk_download and accepted_sdk_licenses:
            progress("Installing the Android SDK from Google's official package repositories…")
            android_sdk = _install_android_sdk(progress, accepted_sdk_licenses, jdk)
        else:
            required = ", ".join(missing)
            raise RuntimeError(
                "The selected Android SDK is incomplete. Install these packages in Android Studio's SDK Manager, "
                f"then select the SDK root again: {required}"
            )
    godot, version = _install_godot(project_dir, progress)
    return {"jdk": jdk, "sdk": android_sdk.expanduser().resolve(), "godot": godot, "godot_version": version}


def godot_environment(paths: dict[str, Path | str]) -> dict[str, str]:
    env = os.environ.copy()
    env["JAVA_HOME"] = str(paths["jdk"])
    env["ANDROID_HOME"] = str(paths["sdk"])
    env["ANDROID_SDK_ROOT"] = str(paths["sdk"])
    if platform.system() == "Windows":
        env["APPDATA"] = str(TOOLS_ROOT / "godot-config")
        env["LOCALAPPDATA"] = str(TOOLS_ROOT / "godot-config")
    else:
        env["XDG_DATA_HOME"] = str(TOOLS_ROOT / "godot-data")
        env["XDG_CONFIG_HOME"] = str(TOOLS_ROOT / "godot-config")
    java_bin = Path(paths["jdk"]) / "bin"
    env["PATH"] = str(java_bin) + os.pathsep + env.get("PATH", "")
    return env
