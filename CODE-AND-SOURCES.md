# Code and Sources

> **UNOFFICIAL FAN PROJECT.** This project is not affiliated with, authorized by, or endorsed by Shaun Hammond Business Solutions Limited, Valve, Steam, or Godot. Official listings: [full game](https://store.steampowered.com/app/3832490/Antivirus_Survivors_2003_Professional/) · [demo](https://store.steampowered.com/app/4320630/Antivirus_Survivors_2003_Professional_Demo/).

This document records what the AVS03 Android Recompiler contains, what was added for this project, and the public technical references used for the build workflow.

## Project code

| File | Purpose |
|---|---|
| `avs03_wrapper_builder.py` | Python/Tkinter desktop GUI. Selects the local game executable and APK output, runs recovery/build steps, detects desktop saves, creates save archives, optionally transfers saves using ADB, records build logs, and provides OS-specific Quick Start, in-app project terms, and a log viewer with a Copy All Log Text button. The form and action footer resize with the window; the window close action shuts down open dialogs and pending callbacks. |
| `tool_setup.py` | Downloads/caches GDRE Tools, Godot, Godot Android export templates, and Eclipse Temurin JDK 17. It validates a selected local SDK; the separate downloader edition can fetch official Google command-line tools and install SDK packages after explicit user consent. |
| `edition_config.py` | Selects the release mode: manual SDK selection or the separate consent-based SDK Downloader edition. |
| `android_builder.py` | Applies touch/save changes to a recovered Godot project, configures the Android export preset, imports Android-compatible textures, validates Android GDExtension dependencies, and exports the APK. It preserves the recovered Steamworks autoload and extension descriptor. |
| `steamworks_tools.py` | Validates that downloaded Android native libraries are 64-bit little-endian AArch64 ELF files. |
| `godotsteam_package.py` | Downloads a pinned public GodotSteam archive from Codeberg after user consent, checks its SHA-256 and ZIP integrity, and copies only its three Android ARM64 libraries into the recovered project. |
| `cleanup_tools.py` | Lists and removes only known AVS03-managed download, cache, and recovered-workspace paths; it never follows directory symlinks. |
| `android_patch/android_touch_controls.gd` | Adds the Android/touchscreen control layer and connects the runtime touch surface. |
| `android_patch/touch_surface.gd` | Draws and handles the Xbox-style virtual controller: analog movement or D-pad, A/B/X, LT, and Pause. Captures touch zones so controller touches do not become in-game mouse clicks. Includes classic/custom layouts, drag positioning, and two-finger pinch resizing for individual controls. |
| `android_patch/save_transfer_importer.gd` | Imports the optional ZIP archive into writable Android `user://` storage, maps Steam-ID profile folders to the Android local profile folder, and records an import checksum. |
| `Run-Builder.bat` | Launch the Python GUI from the Windows source package. |
| `Build-Windows-Exe.bat` | Build a standalone Windows GUI executable with PyInstaller on Windows, embedding the project terms, README, and MIT license. The ready-to-run Linux release is built on Linux and shipped separately. |
| `Build-Linux-App.sh` | Repository-source-only Linux packaging script; it is not included in the Windows source ZIP. It embeds the project terms, README, and MIT license in the Linux standalone app. |
| `LICENSE` | MIT license for the project's original builder code, Android patches, and documentation; it does not cover the game or third-party materials. |

The GUI and Godot patch code were created or adapted for this project from the user's requirements. The APK is generated from the user's local Steam installation and recovered project. The compiler packages do not include the game executable, game PCK, recovered game assets, or a prebuilt game APK. The Android patch does not install a no-op Steamworks replacement or delete the recovered extension descriptor. When Android libraries are absent, the builder can fetch a public GodotSteam package after user consent. The package archive is pinned to commit `87e9456ed0922d861d352cda823ee1bde682c987` and SHA-256 `0271ab46929363a186c147408e763b1f8b28acff7a36b6aebc4592e68a2739a5`; only its Android ARM64 debug/release GDExtension libraries and `libsteam_api.so` are copied into the user’s private recovered workspace. They are architecture-checked, and other declared Android libraries remain subject to preflight validation. This supplies missing platform binaries while leaving the recovered game scripts, assets, and Steamworks descriptor in place. The tool does not authenticate a Steam account or verify file ownership. It does not intentionally bypass DRM, but cannot guarantee preservation of unknown protections.

The UI progress bar now uses a percentage estimate across recovery, tool setup, import, and APK export. The build log records tool output and post-export checks. A prior failure where export succeeded but a stale variable caused the builder to report failure has been corrected: the final check uses the actual Godot exit code and confirms the APK exists. The Windows build path has been confirmed to produce an APK; testing that Windows-produced APK on an Android device remains pending.

The original code and project documentation are offered under the [MIT License](LICENSE). That permissive license does not extend to the game, game assets, Steamworks files, or independently licensed third-party tools. The maintainer's public contact for project, licensing, or third-party tool concerns is [GitHub profile](https://github.com/SoundWaveless). See [DISCLAIMER-ACKNOWLEDGMENT.md](DISCLAIMER-ACKNOWLEDGMENT.md) for project notices, user and uploader responsibilities, risk notice, and contact guidance.

## External tools used by the builder

The builder obtains recovery and Godot/JDK tools at runtime from their upstream projects rather than shipping those toolchains in the packages. Both release editions leave SDK files out of the package: the manual edition uses a user-installed SDK, while the downloader edition fetches it directly from Google to the user's computer after explicit consent and confirms package license prompts only for the requested packages. It uses Google's current Android CLI, with the legacy `sdkmanager` interface as a fallback:

- **GDRE Tools** recovers Godot project resources from the selected local game executable/PCK.
- **Godot Engine and its Android export templates** import the recovered project and generate the Android APK.
- **Eclipse Temurin OpenJDK 17** supplies Java for Android export.
- **Android SDK** is user-installed or installed by the separate downloader edition after consent. Required components are platform-tools, Android platform 35, build-tools 35.0.1, CMake 3.10.2.4988404, and NDK 28.1.13356709.
- **PyInstaller** packages the desktop Python GUI into the Linux executable and can build a Windows executable when run on Windows.

The game save data is the game's own JSON profile/settings format. The builder selects the newest detected profile, flattens the Steam-ID directory for Android's local profile layout, and lets the game's own save code perform version migration. Android app data is written in the app-private writable directory exposed by Godot as `user://`.

## Public technical sources

- [GodotSteam Android package in the Godot Asset Library](https://godotengine.org/asset-library/asset/2445) and [pinned upstream Codeberg archive](https://codeberg.org/godotsteam/godotsteam/archive/87e9456ed0922d861d352cda823ee1bde682c987.zip) — public package source/version; the builder downloads after consent and verifies SHA-256 `0271ab46929363a186c147408e763b1f8b28acff7a36b6aebc4592e68a2739a5`.
- [Godot documentation: Exporting for Android](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_android.html) — Android export setup and export templates.
- [Godot Engine official releases](https://github.com/godotengine/godot/releases) — the builder finds a Godot release matching the recovered project's feature version.
- [Godot Engine license](https://godotengine.org/license/) — Godot is MIT-licensed; follow its notice requirements when redistributing a Godot-based artifact.
- [GDRE Tools source project](https://github.com/GDRETools/gdsdecomp) and [official releases](https://github.com/GDRETools/gdsdecomp/releases) — recovery tool and release binaries.
- [Android CLI SDK management](https://developer.android.com/tools/agents/android-cli/commands/sdk_install) and [Android CLI release notes](https://developer.android.com/tools/agents/android-cli/release-notes) — current official package install interface and license compatibility details.
- [Android SDK command-line tools](https://developer.android.com/tools) and [sdkmanager documentation](https://developer.android.com/tools/sdkmanager) — Google's legacy command-line package manager, retained as a fallback.
- [Android Studio download](https://developer.android.com/studio) and [SDK Manager documentation](https://developer.android.com/studio/intro/update) — official installation and SDK package management.
- [Android SDK License Agreement](https://developer.android.com/studio/terms) — users must accept the applicable terms; this project does not bundle or redistribute SDK files.
- [Android app-specific storage](https://developer.android.com/training/data-storage/app-specific) — basis for placing imported Android saves in app-private writable storage.
- [Eclipse Temurin installation and API information](https://adoptium.net/installation) and [Adoptium API examples](https://github.com/adoptium/api.adoptium.net/blob/main/docs/cookbook.adoc) — source of the OpenJDK 17 runtime download.
- [PyInstaller manual](https://www.pyinstaller.org/en/stable/) and [usage reference](https://pyinstaller.org/en/stable/usage.html) — one-file GUI packaging and the requirement to build separately on each target operating system.
- [PyInstaller licensing terms](https://pyinstaller.org/en/stable/license.html) — applicable to the packaging tool and its bootloader/hooks.
- [Python Tkinter documentation](https://docs.python.org/3/library/tkinter.html) — GUI toolkit used by the desktop builder.
- [Steam Subscriber Agreement](https://store.steampowered.com/subscriber_agreement/) — current Steam terms to review for restrictions and any applicable permissions/exceptions related to software accessed through Steam.
- [Steamworks ISteamApps API](https://partner.steamgames.com/doc/api/ISteamApps) — includes in-client subscription/ownership checks, which require the game to initialize Steamworks and are client-side checks.
- [Steamworks User Authentication and Ownership](https://partner.steamgames.com/doc/features/auth) and [ISteamUser Web API](https://partner.steamgames.com/doc/webapi/ISteamUser) — secure ownership verification uses a publisher key and a trusted server; the key must not be embedded in the builder or APK.
- [GitHub DMCA Takedown Policy](https://docs.github.com/en/site-policy/content-removal-policies/dmca-takedown-policy) — GitHub's process if a rights holder submits a copyright complaint.
- [GitHub documentation on licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) — explains that a public repository without a license does not grant general permission to reproduce, distribute, or make derivative works, subject to GitHub's service terms.
- [Open Source Definition](https://opensource.org/osd) — requires open-source licenses to allow use across fields of endeavor; a project-specific use ban should not be added to an OSI-approved code license.
- [MIT License text at Open Source Initiative](https://opensource.org/license/mit) — the license selected for original project code.
- [Antivirus Survivors 2003 Professional on Steam](https://store.steampowered.com/app/3832490/Antivirus_Survivors_2003_Professional/) and [its Steam demo](https://store.steampowered.com/app/4320630/Antivirus_Survivors_2003_Professional_Demo/) — official game listings; included for reference, not as an endorsement or affiliation.

## Licensing and attribution notes

- This project includes original builder/patch code plus the Android patch files listed above. It does not bundle the user's Steam game files in the compiler packages.
- GodotSteam is listed as MIT-licensed in the Godot Asset Library; the builder fetches its Android package from the public upstream Codeberg archive after user consent and does not redistribute that archive in compiler packages. The package includes Steamworks API redistributable binaries; users must review applicable upstream notices and terms.
- GDRE Tools is MIT-licensed according to its upstream repository. Godot Engine is MIT-licensed. PyInstaller and the Python/Tcl/Tk runtime have their own license terms and notices; the Linux standalone executable is generated by PyInstaller from the system Python/Tk installation.
- Android SDK components are installed by the end user from Google's official distribution. GDRE Tools, Godot, export templates, and OpenJDK are obtained from upstream providers; review each upstream license and retain required notices before redistributing generated components, APKs, or other artifacts.
- The user's game license and rights remain separate from the licenses for these open-source tools. This document describes the compiler's technical inputs and does not grant rights to redistribute game files.
- Steam's agreement contains restrictions on reverse engineering, decompiling, modifying, and distributing Steam content, subject to its stated exceptions and applicable law. Whether those terms or legal exceptions permit a particular use depends on the facts and jurisdiction; this source list is not a legal conclusion.
