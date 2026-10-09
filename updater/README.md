# AVS03 Compiler Updater for 0.1.2 installations

These standalone packages add a compiler-only updater to the existing 0.1.2 build. They do not update the game or modify game files, APKs, or saves.

## Linux

1. Extract `AVS03-Compiler-Updater-Linux-x86_64.zip`.
2. Copy `AVS03-Compiler-Updater` into the directory containing the Linux builder executable.
3. Close the compiler and run `AVS03-Compiler-Updater`.

## Windows source

1. Extract `AVS03-Compiler-Updater-Windows-Source.zip` into the directory containing `avs03_wrapper_builder.py`, merging the files.
2. Close the compiler and run `Run-Compiler-Updater.bat`. Python 3 with Tkinter is required.

The utility checks GitHub for the latest compiler release, chooses the matching OS/edition package, verifies its SHA-256 digest, asks for your approval before downloading or installing, and starts the compiler when finished. The 0.1.3 packages bundle this updater; use `Run-Builder` to launch those. See [`docs/UPDATER.md`](../docs/UPDATER.md) for details.
