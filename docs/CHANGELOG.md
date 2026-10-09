# Release notes

## 0.1.3

See [the 0.1.3 release notes](releases/v0.1.3.md).

- Bundled the compiler updater with all four platform/edition packages. Launching `Run-Builder` checks GitHub first; the compiler also offers **Check for Compiler Updates**. Updates require the user to click Download and Install or approve the Yes/No prompt; there is no silent installation. Downloads are verified by SHA-256, and only compiler files are updated.
- Added a README icon that opens the bundled README inside a scrollable compiler window.
- Made the updater window resize with the display: explanatory text wraps to the available width, and buttons rearrange vertically when there is not enough horizontal space.
- Updated platform packages and documentation for the current controller, input visibility, path memory, APK update, and save-transfer behavior. APK updates do not import newer desktop saves.

### Migrating from 0.1.2

The 0.1.2 release has no bundled updater. Install the matching standalone updater asset from the v0.1.2 GitHub release beside the 0.1.2 builder, then run `AVS03-Compiler-Updater` on Linux or `Run-Compiler-Updater.bat` on Windows. It can download and install the matching 0.1.3 package. See [the updater guide](UPDATER.md).

## 0.1.2

See [the 0.1.2 updater instructions](releases/v0.1.2-updater.md) for installing the separately distributed compiler updater.

- Added digital Xbox-style controller input and physical gamepad/keyboard-driven virtual control visibility.
- Added the APK update build mode and remembered selected paths. APK updates preserve existing phone saves and do not import newer desktop saves.
- Added the compiler updater as a separate optional download for existing 0.1.2 installations; see [the updater guide](UPDATER.md).
