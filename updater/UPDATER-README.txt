AVS03 Compiler Updater for existing 0.1.2 installations

This standalone utility updates the AVS03 compiler application only. It does not update Antivirus Survivors 2003 Professional or change game files, APKs, or saves. It checks GitHub for the newest release, selects the matching operating system and edition package, verifies SHA-256, and asks for your approval before downloading or installing. Nothing is downloaded or installed without your approval.

Linux x86-64: extract this ZIP and copy AVS03-Compiler-Updater beside AVS03-Android-Builder or AVS03-Android-Builder-SDK-Downloader. Run AVS03-Compiler-Updater.

Windows source builder: extract the Windows updater ZIP into the folder containing avs03_wrapper_builder.py, merging the files. Run Run-Compiler-Updater.bat. Python 3 with Tkinter is required.

Close the compiler before updating and store it in a folder writable by your account. If the user declines an update or GitHub cannot be reached, the installed compiler starts. The updater does not target the game installation, APKs, saves, build-tool caches, or AVS03 user data.
