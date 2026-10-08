# Launch Requirements

> **Unofficial fan project:** This builder is not affiliated with or endorsed by the game developer/publisher, Valve/Steam, or Godot. The official Steam pages are [the full game](https://store.steampowered.com/app/3832490/Antivirus_Survivors_2003_Professional/) and [the demo](https://store.steampowered.com/app/4320630/Antivirus_Survivors_2003_Professional_Demo/).

This document separates requirements for opening the desktop builder from requirements for using it to export an APK. Windows and Linux releases contain only their target-OS launcher/compiler artifacts; the Windows source ZIP omits Linux shell scripts.

The application includes a **Quick Start** popup tailored to the detected operating system and a **View Disclaimer** popup that opens the included project terms.

The original builder code and project documentation are licensed under MIT in `../LICENSE`; this license does not cover the game or third-party tools. The project terms in `DISCLAIMER-ACKNOWLEDGMENT.md` describe user and maintainer responsibilities and project risks, without adding a field-of-use restriction to the MIT license. Maintainer contact for project, licensing, or third-party tool concerns: [GitHub profile](https://github.com/SoundWaveless).

## Packaged Linux builder

Download the ready-to-run binary from [the standard Linux package](../linux/downloads/AVS03-Android-Builder-Linux-x86_64.zip) or [the Linux SDK Downloader package](../linux/downloads/AVS03-Android-Builder-Linux-SDK-Downloader.zip).

- 64-bit x86 Linux with a graphical desktop session (X11 or Wayland with the normal desktop compatibility layer).
- A compatible glibc system. The executable was built on a current Linux host; its binary references glibc symbols no newer than `GLIBC_2.14`, but it has only been packaged on this host, not verified across Linux distributions.
- About 13 MB for the executable plus temporary space while the one-file program unpacks itself at launch.
- Make the executable runnable if necessary: `chmod +x AVS03-Android-Builder`.

The packaged file includes the Python runtime and builder code. It does not include Godot, GDRE Tools, Java, or the Android SDK. The builder downloads/caches its recovery and Godot/JDK tools as needed, but never downloads or installs Android SDK packages.

## Windows source builder

The Windows downloads are [the standard source package](../windows/downloads/AVS03-Android-Builder-Windows-Source.zip) and [the SDK Downloader source package](../windows/downloads/AVS03-Android-Builder-Windows-SDK-Downloader-Source.zip); each includes `Run-Builder.bat` and `Build-Windows-Exe.bat`. A native Windows `.exe` must be built on Windows.

- Windows 10 or later, 64-bit.
- Python 3.10 or later with Tcl/Tk installed and the `py` launcher available on PATH.
- Internet access to install PyInstaller if building the standalone `.exe`.
- To create the standalone `.exe`, run `Build-Windows-Exe.bat` on Windows. It creates `dist\AVS03-Android-Builder.exe`.

The Windows build path has been confirmed to compile an APK. Testing that Windows-produced APK on an Android device is still pending.

## Launch from source on Linux

- 64-bit Linux desktop environment.
- Python 3.10 or later with Tkinter.
- `python3-venv` and pip to run the included one-command packaging script.
- To launch without packaging, run `python3 avs03_wrapper_builder.py`; no third-party Python packages are required for normal runtime.

On Debian or Ubuntu, install the source-launch requirements with:

```bash
sudo apt update
sudo apt install python3 python3-tk python3-venv
```

## Requirements to build an APK

The standard/manual-SDK editions use an SDK the user installs and selects. They do not download or install SDK components or accept SDK licenses.

1. Install [Android Studio from the official Android Developers site](https://developer.android.com/studio).
2. Open Android Studio → **Tools → SDK Manager**. Note the **Android SDK Location** at the top.
3. In **SDK Platforms**, install **Android 15 / API 35** (`platforms;android-35`).
4. In **SDK Tools**, install **Android SDK Platform-Tools**, **Android SDK Build-Tools 35.0.1**, **CMake 3.10.2.4988404**, and **NDK (Side by side) 28.1.13356709**. Use **Show Package Details** to select the required exact versions.
5. Review and accept Google's SDK component licenses in Android Studio only if you agree to them.
6. Launch the builder, select the SDK root shown in Android Studio, and build. The builder validates the selected SDK; it will report any missing folders before starting recovery.

### SDK Downloader edition

The separate SDK Downloader editions can install the same required SDK packages from Google's official repositories. They do not include SDK files. If the selected SDK is incomplete, the GUI shows a consent dialog linking to Google's current terms and explains the packages/storage required. Choosing **Yes** authorizes that build to download the official command-line tools, install the listed SDK packages locally, and confirm their license prompts. The downloader uses Google's current `android sdk install` command and slash-separated package IDs; it falls back to `sdkmanager` only when the Android CLI is unavailable. Choosing **No** performs no SDK download or license acceptance. Users can also select a complete SDK they already installed, in which case no SDK download is needed.

The builder downloads/caches these recovery and Godot/JDK tools per user and operating system:

- GDRE Tools for Windows or Linux, to recover the Godot project from the local executable/PCK.
- A Godot editor version matching the recovered project's Godot version, plus the corresponding Android export templates.
- Eclipse Temurin OpenJDK 17.
- An internet connection for first-time downloads of GDRE Tools, Godot/editor templates, and OpenJDK, plus free disk space for those tools, the recovered project, and build intermediates.
- A local Steam installation of the game and its associated PCK/game data. The builder does not download the game.

The exported APK targets ARM64 Android devices. The builder does not intentionally remove or bypass Steamworks/DRM checks and preserves the recovered Steamworks autoload and extension descriptor. If the game's original DRM or Steamworks integration has no Android-compatible implementation, export or runtime may fail. Since protections may be unknown, this builder cannot guarantee every DRM mechanism survives recovery and export; it is not a DRM removal tool.

The recovered project’s descriptor requires three Android ARM64 files: the debug and release GodotSteam GDExtension libraries plus `libsteam_api.so`. If any are missing or invalid, the builder asks before downloading the public GodotSteam 4.23.1 archive from its pinned Codeberg commit. It verifies a hard-coded SHA-256 digest, extracts only those three expected files, and checks each as a 64-bit little-endian ARM64 ELF before placing them in the private recovered project. The archive is cached under the builder’s tool folder. The Godot Asset Library listing identifies the addon as MIT-licensed and targets Godot 4.4 or newer; the recovered descriptor must match its expected Android resource paths. Review the package’s included notices and upstream terms before continuing. This download adds platform-specific Android plugin binaries where the Steam desktop installation has only Linux binaries; it does not send, package, or publish the user’s game files. It does not prove Steam account ownership or grant rights to use or redistribute the game.

Selecting local game files is a build input, not a Steam account ownership verification. The builder does not authenticate a Steam user or verify an entitlement. Reliable web ownership checks require the game publisher’s authorized server-side integration and secret key; a client-side check or mere file presence cannot establish ownership.

## Optional features

- **Include desktop saves in APK:** automatically detects the desktop game's `AntivirusSurvivors` data folder and bundles its latest profile/settings for first-launch import.
- **Transfer Saves…:** creating a ZIP works without a connected device. Sending it to a phone requires Android Debug Bridge (`adb`), USB debugging, and device authorization. Direct in-app transfer is intended for this builder's debug build.

## File locations

- Builder source and scripts: `linux/builder/` or `windows/builder/`. Download packages: the corresponding OS folder's `downloads/` subfolder.
- APK build log: next to the chosen APK, with suffix `.build.log`. **View / Copy Build Log → Copy All Log Text** copies the complete log shown in the viewer and reports the copied character count.
- Recovered workspaces and downloaded non-SDK tools: under the user's app-data directory in `AVS03-Android-Port-Builder/tools/`.
- Selected Android SDK path: `android-sdk-path.txt` under that same tools directory; this file stores only the folder path. Downloader edition SDK packages and accepted license records live under `tools/android-sdk/` on that user's computer.
- Android game saves and settings: app-private writable storage, exposed by Godot as `user://`.

## Clean up builder files

Use **Clean Up Space…** in the GUI to review the size and remove selected AVS03-managed downloads (GDRE Tools, Godot, Android templates, OpenJDK, and the cached public GodotSteam archive) or recovered project workspaces. If an Android SDK exists in the AVS03-managed location, it is shown as a separate selectable item. This removes only the SDK at that managed path; SDKs installed elsewhere are not touched. APKs, save archives, build logs, and the original Steam installation remain outside the cleanup targets.
