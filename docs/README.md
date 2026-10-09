# AVS03 Android Recompiler

> **UNOFFICIAL FAN PROJECT.** This project is not affiliated with, authorized by, or endorsed by Shaun Hammond Business Solutions Limited, Valve, Steam, or the Godot project. It is a community tool, not an official mobile release. The builder does not include the game or grant rights to game content. The official listings are [Antivirus Survivors 2003 Professional on Steam](https://store.steampowered.com/app/3832490/Antivirus_Survivors_2003_Professional/) and its [Steam demo](https://store.steampowered.com/app/4320630/Antivirus_Survivors_2003_Professional_Demo/).

**By downloading, installing, or using this builder, you acknowledge the [project terms and disclaimer](DISCLAIMER-ACKNOWLEDGMENT.md).** Those terms explain user and maintainer responsibilities and project risks; they do not add a field-of-use restriction to the MIT license for the original project code. Maintainer contact: [GitHub profile](https://github.com/SoundWaveless). Legal enforceability of any terms depends on applicable law.

AVS03 Android Recompiler is a desktop GUI builder for making an ARM64 Android APK from a user's local Steam installation of *Antivirus Survivors 2003 Professional*. It recovers the local Godot project, applies the Android control and save patches, then exports an APK. It does not run or emulate the desktop game.

The builder processes the user's local game files. Keep the recovered project, APKs that contain personal save data, and any other game assets private. The builder packages do not include the game itself.

The builder does not intentionally remove, replace, or bypass Steamworks/DRM checks. It preserves the recovered Steamworks autoload and extension descriptor. The Android export may fail if the game's original Steamworks/DRM components do not support Android. This tool cannot identify or guarantee preservation of every unknown protection in a recovered build; it is not a DRM removal tool.

When Android libraries are missing, the builder offers a consent prompt and downloads the public GodotSteam 4.23.1 archive from a pinned Codeberg commit. It verifies the archive checksum, then copies only the Android ARM64 debug/release extension libraries and `libsteam_api.so` into the private recovered project. The project descriptor, game scripts, and assets are preserved. The [Godot Asset Library lists the package as MIT licensed](https://godotengine.org/asset-library/asset/2445); review the package notices and upstream terms before accepting. The builder does not include this package or any game files in its release archives.

Having the game files on disk is not a verified Steam account ownership check and does not grant rights to use or redistribute them. The builder does not sign in to Steam or contact a publisher ownership service.

The **Quick Start** link in the application opens a guide tailored to the operating system running the builder. **View Disclaimer** opens the included project terms inside the application.

The main form scrolls vertically on smaller displays, while the progress bar, status, and four action buttons stay in a fixed footer. The buttons resize into a two-column layout as the window narrows. Guide, disclaimer, save-transfer, and log windows size themselves to fit the available screen area. The window close control cancels pending callbacks and closes its dialogs.

Before a build, the app shows a download notice with links to the tool sources and terms; webpages open only when selected. Separate consent dialogs appear when public GodotSteam Android libraries or Google SDK packages need downloading. The build bar reports a monotonic percentage using download progress and recovery/import/export stages; some stages provide finer progress than others, so the overall percentage is an estimate.

## Packages

The platform folders contain the source builder files and downloadable packages for that OS:

- **[Linux folder](../linux/):** [Linux x86-64](../linux/downloads/AVS03-Android-Builder-Linux-x86_64.zip) and [Linux SDK Downloader](../linux/downloads/AVS03-Android-Builder-Linux-SDK-Downloader.zip). Each ZIP contains a ready-to-launch executable and the documentation.
- **[Windows folder](../windows/):** [Windows Source](../windows/downloads/AVS03-Android-Builder-Windows-Source.zip) and [Windows SDK Downloader Source](../windows/downloads/AVS03-Android-Builder-Windows-SDK-Downloader-Source.zip). Each contains the Python GUI, Windows launcher/build scripts, required modules, Android patch files, and documentation. Run `Run-Builder.bat` to launch with Python, or `Build-Windows-Exe.bat` to build a standalone `.exe` on Windows.

The SDK Downloader editions use Google's current Android CLI to install missing SDK packages after explicit user consent. They download SDK contents to the user's computer; they do not bundle or redistribute them. The Windows source package excludes Linux executables and shell scripts.

PyInstaller does not cross-compile. The Linux executable was built on Linux. A Windows executable must be built on Windows; this Linux host cannot produce or verify a native `.exe`.

See [LAUNCH-REQUIREMENTS.md](LAUNCH-REQUIREMENTS.md) for platform prerequisites and [CODE-AND-SOURCES.md](CODE-AND-SOURCES.md) for an inventory of project code and external sources.
[DISCLAIMER-ACKNOWLEDGMENT.md](DISCLAIMER-ACKNOWLEDGMENT.md) contains the project's intended user terms and risk notice. It is not legal advice or a guarantee of permission.

## Launch the source builder

### Windows

1. Install Python 3.10 or later with Tcl/Tk.
2. Extract the Windows source ZIP.
3. Double-click `Run-Builder.bat`, or open Command Prompt in the folder and run `py avs03_wrapper_builder.py`.
4. To create a standalone Windows executable, double-click `Build-Windows-Exe.bat`. PyInstaller is installed by the script.

### Linux

Use the packaged executable above, or install Python 3, Tkinter, and venv. On Debian or Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-tk python3-venv
```

In the repository, the Linux source files are in `linux/builder/`. Open a terminal there and run `./Run-Builder.sh`. To build the standard standalone Linux executable, run `./Build-Linux-App.sh`; to build the SDK Downloader edition, run `./Build-Linux-SDK-Downloader.sh`. The Windows packages contain only Windows launch/build scripts; Linux shell scripts are not included there.

## Build an Android APK

1. Install the game through Steam and start the builder.
2. Select the game's executable from its Steam install folder. The builder remembers this path, the Android SDK folder, and the selected APK output path after you close and reopen it. Keep the companion `.pck` file beside the executable when the game installation has one. If Android Steamworks libraries are missing from the recovered project, the builder asks before downloading the public GodotSteam package.
3. Choose an APK output path. **Include desktop saves in this APK** is optional; it includes the detected desktop settings and newest profile slots in the APK.
4. Choose **Build Android APK**. The manual-SDK edition uses the SDK you selected without downloading SDK packages. The separate SDK Downloader edition can install missing Google packages only after its consent prompt. You can also install the SDK in Android Studio first.
5. The builder recovers the project, downloads/caches GDRE Tools, a matching Godot editor/templates, and OpenJDK, applies the Android patch, imports assets, and exports the APK. Initial setup needs an internet connection and several gigabytes of free space. The Windows build path has been confirmed to compile an APK; device testing of the Windows-produced APK is still pending.
6. After a full build recovers the game once, turn on the **Update mode** toggle to switch the main button to **Build APK Update** for later mobile-control changes. The toggle is enabled when a cached project is available and its selection is remembered. Update mode reuses the last recovered project and cached Godot imports, skips GDRE recovery, applies the latest included Android patch, and exports a new complete APK. It always excludes the optional desktop-save archive, even if that checkbox is selected. This preserves the phone's existing saves, but newer desktop saves will not be imported by this update. To import newer desktop saves, either turn off Update mode and make a full APK with **Include desktop saves** enabled, or use **Transfer Saves…** with ADB and USB debugging. Update mode does not create a small differential APK patch; Android still installs a new APK. Turn off Update mode when the Steam game files need to be recovered afresh. The cached project remains in AVS03's private workspace until you remove it with **Clean Up Space…**.
7. Install the new APK as an update over the existing app. With the same package ID and signing identity, Android normally retains the app's private save data; this update path does not uninstall the app or clear that data. Do not uninstall first if you need to keep saves.
8. Use **Clean Up Space…** later to remove AVS03-managed downloads and recovered workspaces. Removing the recovered workspace also disables **Build APK Update** until the next full build. An SDK in the AVS03-managed folder is shown as a separate cleanup choice; SDKs installed elsewhere are not removed.

The builder downloads/caches GDRE Tools, a matching Godot editor and Android export templates, Eclipse Temurin OpenJDK 17, and—after consent when needed—the public Android GodotSteam package. Install [Android Studio from Google](https://developer.android.com/studio), then install the required Android SDK packages through its SDK Manager. The manual-SDK edition uses only the SDK folder you select; it does not download SDK packages. The separate SDK Downloader edition uses Google's current Android CLI to install missing packages after an explicit consent dialog that links Google's terms. See [LAUNCH-REQUIREMENTS.md](LAUNCH-REQUIREMENTS.md) for versions and steps.

## Mobile controls

On a touchscreen device, open **Settings → Controls → Mobile**:

- Choose **Classic** to keep the existing control layout, or **Custom** to set each control's position and size.
- Choose **Arrange** to enter the editor. Drag a control to move it. Hold a control with one finger and move a second finger outward or inward to resize it. Tap **Done** to save and exit.
- A, B, X, LT, Pause, and the movement control can be arranged independently. Movement can use the analog joystick or digital D-pad.
- The D-pad supports up, down, left, right, and all four diagonal directions. Diagonal touches send the two matching Xbox D-pad directions together.
- Pair a Bluetooth gamepad in Android Settings first, then launch the game. The virtual buttons send Godot joypad events using an Xbox-style button and axis layout; Android does not use the Windows XInput API. Physical controllers are handled when Android/Godot reports them as connected gamepads.
- When a physical gamepad is connected, the virtual controls hide automatically. They reappear after the last gamepad disconnects, or as soon as the player touches the screen. Any connected gamepad is treated the same; Android/Godot does not report whether it uses Bluetooth or USB here.
- A physical keyboard key press hides the virtual controls. Since this script-only Godot build does not expose Android keyboard attach/detach events, keyboard activity is treated as active for 8 seconds; the controls then return unless a gamepad is connected. Touching the screen brings them back immediately.
- Existing options for control size/opacity, analog deadzone, classic position offsets, and classic pause placement remain available.
- Position and individual size values persist in the game's settings file on the phone.

## Save transfer

Desktop save inclusion is optional. When enabled for a full APK build, the builder finds the desktop `AntivirusSurvivors` user-data folder, picks the newest profile directory and its slots, and maps Steam-ID-nested files into Android's `user://profiles/` layout. Existing Android slots with the same number are replaced during import. **Build APK Update** never includes this archive, so it will not import newer PC saves; use a full APK build with the option enabled if you want the APK to carry those saves.

Alternatively, choose **Transfer Saves…** in the builder to make a separate ZIP or send the saves directly to the phone over ADB. Direct transfer requires Android platform-tools (`adb` installed), USB debugging enabled, and the computer authorized on the phone. The archive is placed in the app's transfer inbox and imported the next time the game starts; close and restart the game if it is already running. Treat save archives as private because they contain personal game progress and settings.

## Logs and troubleshooting

The builder writes a `.build.log` beside the selected APK output. **Clean Up Space…** removes selected AVS03-managed tools, the public GodotSteam cache, and recovered project workspaces. It leaves the Steam install, APKs, save archives, build logs, and SDK folders outside the builder-managed location untouched. Choose **View / Copy Build Log**, then **Copy All Log Text** to copy the entire text shown in the log window. The window reports the copied character count. The full recovered project and GDRE recovery log are retained in the builder's application data folder.

To request help, use the project's [GitHub Issues page](https://github.com/SoundWaveless/AVS03-Android-Recompiler/issues/new?template=build-log.yml) and paste **only the plain-text build log** into the log field. Review it first for private information such as your computer username or local file paths. Do not attach or upload the game executable, PCK, recovered project or assets, APK, save files, signing keys, or any other files. The project does not accept game or APK uploads.

- **Builder will not open on Linux:** use a 64-bit desktop session; confirm the executable bit (`chmod +x AVS03-Android-Builder`) and launch from a terminal to inspect operating-system errors.
- **Python GUI will not open:** install Python's Tkinter package (`python3-tk` on Debian/Ubuntu).
- **APK build cannot download tools:** check network access, free disk space, and the build log. Downloads are cached and retried on later launches.
- **Game recovery fails:** select the executable from the complete Steam installation and keep its matching PCK nearby.
- **Save is absent:** confirm the save option was enabled, then inspect the build log and first-launch Android log output for save-import messages.
- **Direct phone save transfer fails:** install `adb`, enable USB debugging, authorize the computer on the device, and install a debug-signed APK.

## Standalone package details

The Linux executable is a PyInstaller one-file x86-64 build. It was generated on a Linux host and requires a graphical desktop. The Windows source package can launch from Python or build a native Windows executable locally. The two platforms' compiled executables are not interchangeable.

### Physical input visibility

Connected gamepads are read with Godot's `Input.get_connected_joypads()` and their add/remove transitions. This detects gamepads independently of connection transport and hides the overlay while one is connected. A screen touch overrides that hidden state; disconnecting the last gamepad also restores the overlay. Physical keyboard input hides the overlay for an 8-second inactivity window. Android's `InputManager` has device-added/removed callbacks, but using those for a keyboard requires a native Android plugin and Gradle integration; this release does not include that plugin.

The Android export uses Godot's Android export workflow. The builder selects ARM64 and uses Android SDK platform 35, build-tools 35.0.1, and the Android NDK version configured in `tool_setup.py`. More details and links are in [CODE-AND-SOURCES.md](CODE-AND-SOURCES.md).
