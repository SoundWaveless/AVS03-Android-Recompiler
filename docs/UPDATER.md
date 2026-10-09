# AVS03 Compiler Updater

The updater changes AVS03 compiler files only. It does not update Antivirus Survivors 2003 Professional, game files, APKs, or saves. It checks the latest GitHub release, chooses the package for the current operating system and edition, verifies the asset's SHA-256 digest, and asks for your approval before downloading or installing. Nothing is downloaded or installed without your approval.

## Existing 0.1.2 installations

Version 0.1.2 predates the integrated updater. Download the separate updater package for your platform from the [v0.1.2 GitHub release](https://github.com/SoundWaveless/AVS03-Android-Recompiler/releases/tag/v0.1.2). Close the compiler first.

### Linux x86-64

1. Download `AVS03-Compiler-Updater-Linux-x86_64.zip` from the v0.1.2 release and extract it.
2. Copy `AVS03-Compiler-Updater` into the same folder as `AVS03-Android-Builder` (or `AVS03-Android-Builder-SDK-Downloader`).
3. Run `AVS03-Compiler-Updater`. It checks for a compiler release, offers any newer matching package, and then starts the compiler.

### Windows source builder

1. Download `AVS03-Compiler-Updater-Windows-Source.zip` from the v0.1.2 release.
2. Extract its contents into the folder containing `avs03_wrapper_builder.py`, merging the files.
3. Run `Run-Compiler-Updater.bat`. Python 3 with Tkinter is required, as with the source builder.

For either platform, keep the compiler in a folder your account can write to. The updater only replaces files supplied by the builder release package; it preserves unrelated files in the folder and never targets the game install, APKs, saves, build-tool caches, or AVS03 user data. If an update is declined or GitHub is unavailable, it starts the installed compiler.

## Version 0.1.3 and later

The 0.1.3 packages bundle the compiler updater. Start `Run-Builder.sh` on Linux or `Run-Builder.bat` on Windows to check for compiler updates before the GUI opens. The compiler also has **Check for Compiler Updates** for a manual check. Linux packages include a standalone `AVS03-Compiler-Updater`; Windows source packages include the Python updater.

Updates replace compiler package files only. An APK update is a separate builder operation; it preserves app data on the phone and does not import newer desktop saves. To include newer saves, rebuild a full APK with the save option or use **Transfer Saves…** with ADB and USB debugging.
