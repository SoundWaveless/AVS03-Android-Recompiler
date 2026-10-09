"""Recover a local AVS03 Godot project and build a touch-enabled Android APK."""

from __future__ import annotations

import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
import json
import zipfile
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from android_builder import export_android_apk
from cleanup_tools import cleanup_inventory, format_bytes, remove_managed_files
from edition_config import SDK_DOWNLOADER_EDITION
from godotsteam_package import (
    GODOTSTEAM_ARCHIVE_URL,
    GODOTSTEAM_ASSET_URL,
    GODOTSTEAM_VERSION,
    has_verified_package_cache,
    install_public_android_libraries,
)
from tool_setup import TOOLS_ROOT, detect_android_sdk, ensure_gdre_tool, setup_export_tools, validate_android_sdk
from update_manager import APP_VERSION, check_latest_release, download_release_asset, get_install_directory, install_release_package


APP_TITLE = "AVS03 Android Recompiler" + (" — SDK Downloader Edition" if SDK_DOWNLOADER_EDITION else "")
ANDROID_PACKAGE = "org.avs03.android"
SAVE_TRANSFER_NAME = "AVS03-Save-Transfer.zip"
STEAM_GAME_URL = "https://store.steampowered.com/app/3832490/Antivirus_Survivors_2003_Professional/"
STEAM_DEMO_URL = "https://store.steampowered.com/app/4320630/Antivirus_Survivors_2003_Professional_Demo/"
ANDROID_SDK_TERMS_URL = "https://developer.android.com/studio/terms"
ANDROID_CLI_DOCS_URL = "https://developer.android.com/tools/agents/android-cli/commands/sdk_install"
GDRE_RELEASES_URL = "https://github.com/GDRETools/gdsdecomp/releases"
GODOT_RELEASES_URL = "https://github.com/godotengine/godot/releases"
TEMURIN_URL = "https://adoptium.net/temurin/releases/"
SKIP_DIRS = {".git", "__pycache__", "shadercache"}


def desktop_path(filename: str) -> Path:
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home()
    return desktop / filename


def find_godot_packs(folder: Path) -> list[Path]:
    packs: list[Path] = []
    for current, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
        packs.extend(Path(current) / name for name in files if name.lower().endswith(".pck"))
    return sorted(packs, key=lambda p: p.name.lower())


def find_companion_pack(game_executable: Path) -> Path | None:
    """Find a matching or unambiguous sidecar PCK next to the selected game executable."""
    for folder in (game_executable.parent, game_executable.parent.parent, game_executable.parent.parent.parent):
        candidates = find_godot_packs(folder)
        matching = [path for path in candidates if path.stem.lower() == game_executable.stem.lower()]
        if matching:
            return max(matching, key=lambda path: path.stat().st_size)
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_size)
    return None


def detect_save_folder() -> Path | None:
    """Find the game's Godot user:// directory on this desktop OS."""
    candidates: list[Path] = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "AntivirusSurvivors")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "AntivirusSurvivors")
    else:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        candidates.append(data_home / "AntivirusSurvivors")
    return next((path for path in candidates if path.is_dir()), None)


def collect_save_transfer_files(save_root: Path) -> dict[str, Path]:
    """Flatten the active Steam profile folder to Android's Steam-free layout."""
    if not save_root.is_dir():
        raise ValueError("Select the Antivirus Survivors user data folder.")
    profiles = save_root / "profiles"
    profile_candidates = []
    if profiles.is_dir():
        for folder in [profiles, *(p for p in profiles.iterdir() if p.is_dir())]:
            slots = [folder / f"slot_{slot}.json" for slot in range(1, 4)]
            existing = [path for path in slots if path.is_file()]
            if existing:
                profile_candidates.append((max(p.stat().st_mtime for p in existing), folder, existing))
    if not profile_candidates:
        raise ValueError("No profile saves were found. Expected profiles/slot_1.json (or slot_2/slot_3.json) in the selected folder.")
    _modified, profile_folder, slots = max(profile_candidates, key=lambda row: row[0])
    files: dict[str, Path] = {}
    settings = save_root / "settings.cfg"
    if settings.is_file():
        files["settings.cfg"] = settings
    for slot_path in slots:
        files[f"profiles/{slot_path.name}"] = slot_path
        backup = slot_path.with_name(slot_path.name + ".bak")
        if backup.is_file():
            files[f"profiles/{backup.name}"] = backup
    state = profile_folder / "state.json"
    if state.is_file():
        files["profiles/state.json"] = state
    return files


def create_save_transfer_archive(save_root: Path, archive_path: Path) -> tuple[Path, int]:
    files = collect_save_transfer_files(save_root)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for relative_name, path in files.items():
            archive.write(path, relative_name)
        archive.writestr(
            "README-IMPORT.txt",
            "AVS03 save transfer\n\n"
            "Copy this ZIP to the Android app with AVS03 Android Builder's Send to Phone action, "
            "or place it in the app's save-transfer-inbox folder. Start the game to import it. "
            "Imported profile slots replace same-numbered slots on the phone.\n",
        )
    return archive_path, len(files)


def send_save_archive_to_phone(archive_path: Path, package_name: str, device_serial: str = "") -> str:
    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("Android Debug Bridge (adb) was not found. Install Android platform-tools and add adb to PATH.")
    devices_result = subprocess.run([adb, "devices"], capture_output=True, text=True, check=True)
    devices = [line.split()[0] for line in devices_result.stdout.splitlines()[1:] if len(line.split()) >= 2 and line.split()[1] == "device"]
    if device_serial:
        if device_serial not in devices:
            raise RuntimeError(f"ADB device {device_serial} is not connected or has not authorized this computer.")
        serial = device_serial
    elif len(devices) == 1:
        serial = devices[0]
    elif not devices:
        raise RuntimeError("No authorized Android phone was found. Connect it by USB, enable USB debugging, and accept the debugging prompt.")
    else:
        raise RuntimeError("More than one ADB device is connected. Enter the target device serial in the Save Transfer window.")
    command = [adb, "-s", serial, "shell", "run-as", package_name, "sh", "-c", "mkdir -p files/save-transfer-inbox && cat > files/save-transfer-inbox/save-transfer.zip"]
    result = subprocess.run(command, input=archive_path.read_bytes(), capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise RuntimeError("Could not copy the archive into the app. Install the debug APK built by this builder first.\n" + detail)
    return serial


class Builder(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        initial_width = min(820, max(420, screen_width - 40))
        initial_height = min(680, max(380, screen_height - 80))
        self.geometry(f"{initial_width}x{initial_height}")
        self.minsize(min(560, initial_width), min(430, initial_height))
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._closed = False
        self._busy = False
        self._process_events_after_id = None
        self._quickstart_after_id = None
        self._scrollregion_after_id = None
        self._readme_tooltip = None
        self.user_settings = self._load_builder_settings()
        self.game_executable_var = tk.StringVar()
        self.cached_project_path = self._read_cached_project()
        self.game_executable_var.set(str(self.user_settings.get("game_executable", "")))
        self.android_sdk_var = tk.StringVar(value=self._load_sdk_path())
        self.apk_var = tk.StringVar(value=str(self.user_settings.get("apk_output", desktop_path("AVS03-Android.apk"))))
        self.include_saves_var = tk.BooleanVar(value=False)
        self.update_mode_var = tk.BooleanVar(value=bool(self.user_settings.get("update_mode", False)) and self.cached_project_path is not None)
        self.update_check_running = False
        self.game_executable_var.trace_add("write", self._save_builder_settings)
        self.apk_var.trace_add("write", self._save_builder_settings)
        self.android_sdk_var.trace_add("write", self._save_sdk_path)
        self.status_var = tk.StringVar(value="Select the game's Windows or Linux executable, then build the Android APK.")
        self.build_log_path: Path | None = None
        self.save_transfer_window = None
        self.save_root_var = None
        self.save_archive_var = None
        self.save_send_var = None
        self.save_serial_var = None
        self.save_package_var = None
        self.build_progress_value = 0.0
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self._process_events_after_id = self.after(120, self._process_events)
        self._quickstart_after_id = self.after(350, self.open_quickstart)

    def _show_readme_tooltip(self, event) -> None:
        self._hide_readme_tooltip()
        tooltip = tk.Toplevel(self)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 14}")
        ttk.Label(tooltip, text="Click to open the README in a new window", padding=(7, 4), relief="solid").pack()
        self._readme_tooltip = tooltip

    def _hide_readme_tooltip(self, _event=None) -> None:
        if self._readme_tooltip is not None:
            try:
                self._readme_tooltip.destroy()
            except tk.TclError:
                pass
            self._readme_tooltip = None

    def open_readme(self) -> None:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        readme_candidates = [
            base / "docs" / "README.md",
            base.parent / "docs" / "README.md",
            base.parent.parent / "docs" / "README.md",
            base.parent.parent.parent / "docs" / "README.md",
            Path(sys.executable).resolve().parent / "docs" / "README.md",
        ]
        readme_path = next((path for path in readme_candidates if path.is_file()), None)
        if readme_path is None:
            messagebox.showerror(APP_TITLE, "Could not find the bundled README file.", parent=self)
            return
        try:
            readme = readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not read the bundled README file.\n\n{exc}", parent=self)
            return
        window = tk.Toplevel(self)
        window.title("AVS03 Compiler README")
        self._fit_dialog(window, 820, 680, 520, 400)
        window.transient(self)
        body = ttk.Frame(window, padding=14)
        body.pack(fill="both", expand=True)
        text_box = tk.Text(body, wrap="word", height=28, width=96, font=("Segoe UI", 10), padx=10, pady=10, spacing1=1, spacing3=3)
        text_box.tag_configure("h1", font=("Segoe UI", 18, "bold"), foreground="#243b53", spacing1=12, spacing3=8)
        text_box.tag_configure("h2", font=("Segoe UI", 14, "bold"), foreground="#243b53", spacing1=10, spacing3=5)
        text_box.tag_configure("h3", font=("Segoe UI", 12, "bold"), foreground="#334e68", spacing1=8, spacing3=4)
        text_box.tag_configure("quote", foreground="#7b1e1e", lmargin1=12, lmargin2=12)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text_box.yview)
        text_box.configure(yscrollcommand=scrollbar.set)
        text_box.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for line in readme.splitlines():
            heading = re.match(r"^(#{1,3})\s+(.*)$", line)
            tag = None
            if heading:
                tag = f"h{len(heading.group(1))}"
                line = heading.group(2)
            elif line.startswith("> "):
                tag, line = "quote", line[2:]
            elif line.startswith("- "):
                line = "• " + line[2:]
            line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", line)
            line = re.sub(r"\*\*(.*?)\*\*", r"\1", line).replace("`", "")
            text_box.insert("end", line + "\n", tag or ())
        text_box.configure(state="disabled")
        ttk.Button(window, text="Close", command=window.destroy).pack(anchor="e", padx=14, pady=(0, 12))

    def _read_cached_project(self) -> Path | None:
        metadata = TOOLS_ROOT / "last-recovered-project.json"
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
            project = Path(data["project_path"]).expanduser().resolve()
            project.relative_to((TOOLS_ROOT / "workspaces").resolve())
            return project if (project / "project.godot").is_file() else None
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _load_builder_settings(self) -> dict[str, object]:
        try:
            settings = json.loads((TOOLS_ROOT / "builder-settings.json").read_text(encoding="utf-8"))
            return settings if isinstance(settings, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _save_builder_settings(self, *_args) -> None:
        try:
            TOOLS_ROOT.mkdir(parents=True, exist_ok=True)
            settings = {
                "game_executable": self.game_executable_var.get().strip(),
                "apk_output": self.apk_var.get().strip(),
                "update_mode": bool(self.update_mode_var.get()) if hasattr(self, "update_mode_var") else False,
            }
            path = TOOLS_ROOT / "builder-settings.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            pass

    def _save_sdk_path(self, *_args) -> None:
        try:
            TOOLS_ROOT.mkdir(parents=True, exist_ok=True)
            (TOOLS_ROOT / "android-sdk-path.txt").write_text(self.android_sdk_var.get().strip(), encoding="utf-8")
        except OSError:
            pass

    def _refresh_update_button(self) -> None:
        valid_cache = bool(self.cached_project_path and (self.cached_project_path / "project.godot").is_file())
        if hasattr(self, "update_mode_toggle"):
            self.update_mode_toggle.configure(state="normal" if valid_cache and not self._busy else "disabled")
        if not valid_cache and self.update_mode_var.get():
            self.update_mode_var.set(False)
            self._save_builder_settings()
        if hasattr(self, "build_button"):
            self.build_button.configure(text="Build APK Update" if self.update_mode_var.get() else "Build Android APK")

    def on_update_mode_changed(self) -> None:
        self._save_builder_settings()
        self._refresh_update_button()

    def check_for_updates(self) -> None:
        if self._busy or self.update_check_running:
            return
        self.update_check_running = True
        self._set_busy(True, "Checking GitHub for builder updates…", indeterminate=True)
        threading.Thread(target=self._update_check_worker, daemon=True).start()

    def _update_check_worker(self) -> None:
        try:
            update = check_latest_release(APP_VERSION, SDK_DOWNLOADER_EDITION)
            self.events.put(("update-check", (update, None)))
        except Exception as exc:
            self.events.put(("update-check", (None, str(exc))))

    def _install_update(self, update: dict[str, object]) -> None:
        self._set_busy(True, f"Downloading version {update['latest_version']}…")
        threading.Thread(target=self._update_install_worker, args=(update,), daemon=True).start()

    def _update_install_worker(self, update: dict[str, object]) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="avs03-update-") as temporary_directory:
                archive = Path(temporary_directory) / str(update["asset_name"])
                download_release_asset(update, archive, lambda done, total: self.events.put(("update-progress", (done, total))))
                installed = install_release_package(archive, get_install_directory(__file__))
            self.events.put(("update-installed", (str(update["latest_version"]), len(installed))))
        except Exception as exc:
            self.events.put(("update-failed", str(exc)))

    def close_app(self) -> None:
        """Close the main window and any transient windows opened by the builder."""
        if self._closed:
            return
        self._closed = True
        for after_id in (self._process_events_after_id, self._quickstart_after_id, self._scrollregion_after_id):
            if after_id:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
        # The wheel handlers are registered on the application-wide bindtag.
        # Remove them before tearing down the canvas so no callback can keep
        # referring to destroyed widgets during shutdown.
        try:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except tk.TclError:
            pass
        self.quit()
        self.destroy()

    def _fit_dialog(self, window: tk.Toplevel, width: int, height: int, min_width: int, min_height: int) -> None:
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        actual_width = min(width, max(420, screen_width - 40))
        actual_height = min(height, max(320, screen_height - 80))
        window.geometry(f"{actual_width}x{actual_height}")
        window.minsize(min(min_width, actual_width), min(min_height, actual_height))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        footer = ttk.Frame(root)
        footer.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        scroll_area = ttk.Frame(root)
        scroll_area.grid(row=0, column=0, sticky="nsew")
        scroll_area.columnconfigure(0, weight=1)
        scroll_area.rowconfigure(0, weight=1)
        canvas = tk.Canvas(scroll_area, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(scroll_area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        outer = ttk.Frame(canvas, padding=10)
        canvas_window = canvas.create_window((0, 0), window=outer, anchor="nw")

        last_scroll_region = (0, 0, 0, 0)

        def update_scroll_region() -> None:
            nonlocal last_scroll_region
            self._scrollregion_after_id = None
            if not canvas.winfo_exists():
                return
            bounds = canvas.bbox("all")
            if bounds and tuple(bounds) != last_scroll_region:
                last_scroll_region = tuple(bounds)
                canvas.configure(scrollregion=bounds)

        def schedule_scroll_region(_event=None) -> None:
            if self._scrollregion_after_id is None:
                self._scrollregion_after_id = canvas.after_idle(update_scroll_region)

        def fit_content_width(event) -> None:
            if event.width <= 1:
                return
            current_width = canvas.itemcget(canvas_window, "width")
            if not current_width or abs(int(float(current_width)) - event.width) > 1:
                canvas.itemconfigure(canvas_window, width=event.width)

        def mousewheel(event):
            widget = self.winfo_containing(event.x_root, event.y_root)
            inside_canvas = False
            while widget is not None:
                if widget == canvas:
                    inside_canvas = True
                    break
                widget = getattr(widget, "master", None)
            if not inside_canvas:
                return
            if getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-event.delta / 120), "units")

        outer.bind("<Configure>", schedule_scroll_region)
        canvas.bind("<Configure>", fit_content_width)
        self.bind_all("<MouseWheel>", mousewheel)
        self.bind_all("<Button-4>", mousewheel)
        self.bind_all("<Button-5>", mousewheel)
        title_row = ttk.Frame(outer)
        title_row.pack(anchor="w", fill="x")
        readme_icon = tk.Canvas(title_row, width=30, height=30, highlightthickness=0, borderwidth=0, cursor="hand2")
        readme_icon.pack(side="left", padx=(0, 7))
        readme_icon.create_rectangle(7, 3, 23, 26, fill="#ffffff", outline="#455a64", width=2)
        readme_icon.create_line(17, 3, 17, 9, 23, 9, fill="#455a64", width=2)
        readme_icon.create_line(10, 13, 20, 13, fill="#1976a5", width=2)
        readme_icon.create_line(10, 17, 20, 17, fill="#1976a5", width=2)
        readme_icon.create_line(10, 21, 18, 21, fill="#1976a5", width=2)
        readme_icon.bind("<Button-1>", lambda _event: self.open_readme())
        readme_icon.bind("<Enter>", self._show_readme_tooltip)
        readme_icon.bind("<Leave>", self._hide_readme_tooltip)
        ttk.Label(title_row, text="AVS03 Android Recompiler", font=("Segoe UI", 18, "bold")).pack(side="left", anchor="w")
        ttk.Label(outer, text="UNOFFICIAL FAN PROJECT — NOT AFFILIATED WITH OR ENDORSED BY THE DEVELOPER, PUBLISHER, OR STEAM.", font=("Segoe UI", 9, "bold"), foreground="#9b1c1c", wraplength=770).pack(anchor="w", pady=(3, 2))
        contact_notice = ttk.Label(
            outer,
            text="By downloading, installing, or using this builder, you acknowledge the project terms and risk notices in View Disclaimer. Original project code and documentation: MIT License. Maintainer contact: github.com/SoundWaveless.",
            wraplength=770,
            foreground="#444",
            cursor="hand2",
        )
        contact_notice.pack(anchor="w", pady=(2, 5))
        contact_notice.bind("<Button-1>", lambda _event: webbrowser.open("https://github.com/SoundWaveless"))
        links = ttk.Frame(outer)
        links.pack(anchor="w", pady=(0, 9))
        for label, url in (("Official Steam game page", STEAM_GAME_URL), ("Official Steam demo page", STEAM_DEMO_URL)):
            link = ttk.Label(links, text=label, foreground="#145da0", cursor="hand2")
            link.pack(side="left", padx=(0, 16))
            link.bind("<Button-1>", lambda _event, target=url: webbrowser.open(target))
        quickstart_link = ttk.Label(links, text="Quick Start", foreground="#145da0", cursor="hand2")
        quickstart_link.pack(side="left", padx=(0, 16))
        quickstart_link.bind("<Button-1>", lambda _event: self.open_quickstart())
        disclaimer_link = ttk.Label(links, text="View Disclaimer", foreground="#145da0", cursor="hand2")
        disclaimer_link.pack(side="left")
        disclaimer_link.bind("<Button-1>", lambda _event: self.open_disclaimer())
        sdk_setup_text = (
            "Choose the game executable and Android SDK folder. If packages are missing, this edition can download them from Google after you review and accept the SDK terms."
            if SDK_DOWNLOADER_EDITION else
            "Choose the game executable and your locally installed Android SDK. This edition does not install or download Android SDK components."
        )
        ttk.Label(outer, text=sdk_setup_text, wraplength=710).pack(anchor="w", pady=(5, 16))
        self._path_row(outer, "Game executable from your Steam install", self.game_executable_var, self.pick_game_executable)
        self.update_mode_toggle = ttk.Checkbutton(
            outer,
            text="Update mode — reuse the last recovered project",
            variable=self.update_mode_var,
            command=self.on_update_mode_changed,
        )
        self.update_mode_toggle.pack(anchor="w", pady=(6, 0))
        ttk.Label(outer, text="Build APK Update reuses the last recovered project to speed up control changes. Build Android APK again to recover updated game files.", wraplength=710, foreground="#444").pack(anchor="w", pady=(4, 0))
        package_info = ttk.Frame(outer)
        package_info.pack(fill="x", pady=(8, 0))
        ttk.Label(
            package_info,
            text=f"Android Steamworks support: public GodotSteam {GODOTSTEAM_VERSION} ARM64 files are downloaded only when needed and installed in the private recovered project.",
            wraplength=670,
        ).pack(side="left", fill="x", expand=True)
        package_link = ttk.Label(package_info, text="Package details", foreground="#145da0", cursor="hand2")
        package_link.pack(side="right", padx=(8, 0))
        package_link.bind("<Button-1>", lambda _event: webbrowser.open(GODOTSTEAM_ASSET_URL))
        sdk_label = "Android SDK root (managed download target)" if SDK_DOWNLOADER_EDITION else "Android SDK root (install with Android Studio first)"
        self._path_row(outer, sdk_label, self.android_sdk_var, self.pick_android_sdk)
        self._path_row(outer, "Android APK output file", self.apk_var, self.pick_apk_output)
        save_box = ttk.Frame(outer, padding=10, relief="groove")
        save_box.pack(fill="x", pady=(14, 4))
        self.save_checkbutton = ttk.Checkbutton(save_box, text="Include desktop saves in this APK (optional)", variable=self.include_saves_var)
        self.save_checkbutton.pack(anchor="w")
        ttk.Label(
            save_box,
            text="Full builds can include desktop saves for first launch. Build APK Update always skips this archive so an update cannot import desktop saves over the phone's existing data.",
            wraplength=670,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(outer, text="DRM / Steamworks: The builder does not intentionally remove or replace Steamworks integration. An Android export can fail if the original DRM or Steamworks components do not support Android; this tool does not bypass those checks.", wraplength=770, foreground="#444").pack(anchor="w", pady=(7, 0))
        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=100, value=0)
        self.progress.pack(fill="x", pady=(18, 8))
        status_label = ttk.Label(footer, textvariable=self.status_var, wraplength=710)
        status_label.pack(anchor="w", fill="x")

        def fit_status_text(event) -> None:
            wraplength = max(200, event.width - 12)
            if int(status_label.cget("wraplength")) != wraplength:
                status_label.configure(wraplength=wraplength)

        status_label.bind("<Configure>", fit_status_text)
        buttons = ttk.Frame(footer)
        buttons.pack(fill="x", pady=(8, 0))
        buttons.columnconfigure(0, weight=1, uniform="actions")
        buttons.columnconfigure(1, weight=1, uniform="actions")
        self.build_button = ttk.Button(buttons, text="Build Android APK", command=self.start_selected_build)
        self.build_button.grid(row=0, column=0, columnspan=2, sticky="ew", pady=2)
        self._refresh_update_button()
        self.save_button = ttk.Button(buttons, text="Transfer Saves…", command=self.open_save_transfer)
        self.save_button.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=2)
        self.cleanup_button = ttk.Button(buttons, text="Clean Up Space…", command=self.open_cleanup_dialog)
        self.cleanup_button.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)
        self.log_button = ttk.Button(buttons, text="View / Copy Build Log", command=self.open_build_log, state="disabled")
        self.log_button.grid(row=2, column=0, columnspan=2, sticky="ew", pady=2)
        self.check_updates_button = ttk.Button(buttons, text="Check for Compiler Updates", command=self.check_for_updates)
        self.check_updates_button.grid(row=3, column=0, columnspan=2, sticky="ew", pady=2)

    def _path_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).pack(anchor="w", pady=(8, 4))
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=command).pack(side="left", padx=(8, 0))

    def open_quickstart(self) -> None:
        system = platform.system()
        if system == "Windows":
            os_requirements = (
                "Windows requirements:\n"
                "• Windows 10 or later, 64-bit.\n"
                "• This release is the Windows source package: install Python 3.10+ with Tcl/Tk. "
                "Run Run-Builder.bat. Build-Windows-Exe.bat creates a Windows executable on Windows.\n"
                "• Internet access and several GB of free space for recovery, Godot/export templates, Java, "
                "and the public Android GodotSteam package if it is missing."
            )
        elif system == "Linux":
            os_requirements = (
                "Linux requirements:\n"
                "• 64-bit x86 Linux with a graphical desktop session and compatible glibc.\n"
                "• The Linux release is a ready-to-run app. If launching the project source tree, install "
                "Python 3, Tkinter, and venv.\n"
                "• Internet access and several GB of free space for recovery, Godot/export templates, Java, "
                "and the public Android GodotSteam package if it is missing."
            )
        else:
            os_requirements = (
                f"Detected operating system: {system or 'unknown'}. Use a supported 64-bit Windows or Linux "
                "desktop package with a graphical environment."
            )
        sdk_requirements = (
            "Android SDK: select a locally installed SDK that contains platform 35, build-tools 35.0.1, "
            "platform-tools, CMake 3.10.2.4988404, and NDK 28.1.13356709. Install them in Android Studio first."
            if not SDK_DOWNLOADER_EDITION else
            "Android SDK: select an existing SDK or let this SDK Downloader edition install the required "
            "Google packages after reviewing the SDK terms and accepting the download prompt."
        )
        text = (
            "UNOFFICIAL FAN PROJECT — not affiliated with or endorsed by the game developer, publisher, Valve, or Steam.\n\n"
            + os_requirements
            + "\n\nWhat you need for an Android build:\n"
            "• A local Steam installation of the game, including the executable and its companion PCK when present.\n"
            f"• {sdk_requirements}\n"
            "• An ARM64 Android device for installation.\n"
            "• A first-run internet connection to obtain GDRE Tools, the matching Godot editor/templates, OpenJDK, "
            "and—after consent—the pinned public Android GodotSteam package when required.\n\n"
            "Quick steps:\n"
            "1. Select the game's executable from its Steam install folder.\n"
            "2. Choose an APK output path; desktop save inclusion is optional.\n"
            "3. Build the APK. The game files stay on this computer; the builder does not publish or include them "
            "in its release packages.\n"
            "4. Use Clean Up Space… to remove selected builder downloads or recovered workspaces when finished.\n\n"
            "The builder adds the Android controls/save-transfer layer and the required Android platform libraries "
            "without intentionally removing the recovered Steamworks descriptor or DRM checks."
        )
        window = tk.Toplevel(self)
        window.title("AVS03 Quick Start")
        self._fit_dialog(window, 760, 620, 500, 380)
        window.transient(self)
        body = ttk.Frame(window, padding=16)
        body.pack(fill="both", expand=True)
        text_box = tk.Text(body, wrap="word", height=26, width=90)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text_box.yview)
        text_box.configure(yscrollcommand=scrollbar.set)
        text_box.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        text_box.insert("1.0", text)
        text_box.configure(state="disabled")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom", pady=(10, 0))
        ttk.Button(buttons, text="Open Official Steam Page", command=lambda: webbrowser.open(STEAM_GAME_URL)).pack(side="left")
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")

    def open_disclaimer(self) -> None:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        disclaimer_candidates = [
            base / "docs" / "DISCLAIMER-ACKNOWLEDGMENT.md",
            base.parent.parent / "docs" / "DISCLAIMER-ACKNOWLEDGMENT.md",
            Path(sys.executable).resolve().parent / "docs" / "DISCLAIMER-ACKNOWLEDGMENT.md",
        ]
        disclaimer_path = next((path for path in disclaimer_candidates if path.is_file()), disclaimer_candidates[0])
        try:
            disclaimer = disclaimer_path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not open the bundled disclaimer text.\n\n{exc}", parent=self)
            return
        window = tk.Toplevel(self)
        window.title("Fan Project Disclaimer and Acknowledgment")
        self._fit_dialog(window, 760, 620, 500, 380)
        window.transient(self)
        body = ttk.Frame(window, padding=16)
        body.pack(fill="both", expand=True)
        text_box = tk.Text(body, wrap="word", height=26, width=90)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text_box.yview)
        text_box.configure(yscrollcommand=scrollbar.set)
        text_box.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        text_box.insert("1.0", disclaimer)
        text_box.configure(state="disabled")
        ttk.Button(body, text="Close", command=window.destroy).pack(anchor="e", pady=(10, 0))

    def _load_sdk_path(self) -> str:
        saved = TOOLS_ROOT / "android-sdk-path.txt"
        if saved.is_file():
            try:
                value = saved.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except OSError:
                pass
        managed = TOOLS_ROOT / "android-sdk"
        if SDK_DOWNLOADER_EDITION and managed.is_dir():
            return str(managed)
        detected = detect_android_sdk()
        return str(detected) if detected else ""

    def pick_android_sdk(self) -> None:
        selected = filedialog.askdirectory(title="Select Android SDK root", initialdir=self.android_sdk_var.get() or str(Path.home()), parent=self)
        if selected:
            self.android_sdk_var.set(selected)

    def pick_game_executable(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select the game's executable from its Steam folder",
            filetypes=[
                ("Windows executable", "*.exe"),
                ("Linux game executable", "*"),
                ("All files", "*.*"),
            ],
            parent=self,
        )
        if selected:
            self.game_executable_var.set(selected)

    def pick_apk_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Choose APK output path",
            parent=self,
            initialfile="AVS03-Android.apk",
            defaultextension=".apk",
            filetypes=[("Android APK", "*.apk")],
        )
        if selected:
            self.apk_var.set(selected)

    def open_cleanup_dialog(self) -> None:
        inventory = cleanup_inventory(include_managed_sdk=(TOOLS_ROOT / "android-sdk").exists())
        present = [(title, paths, size) for title, paths, size in inventory if paths]
        window = tk.Toplevel(self)
        window.title("Clean Up Builder Files")
        self._fit_dialog(window, 650, 440, 500, 320)
        window.transient(self)
        body = ttk.Frame(window, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Free space used by the builder", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="Choose AVS03-managed downloads or recovered workspaces to remove. Workspaces contain recovered copies of game files and any edits made to those copies.",
            wraplength=600,
        ).pack(anchor="w", pady=(5, 12))
        selections: dict[str, tk.BooleanVar] = {}
        for title, _paths, size in present:
            selected = tk.BooleanVar(value=True)
            selections[title] = selected
            ttk.Checkbutton(body, text=f"{title}  ({format_bytes(size)})", variable=selected).pack(anchor="w", pady=4)
        if not any("Android SDK" in title for title, _paths, _size in present):
            ttk.Label(body, text="No builder-managed Android SDK was found. Externally installed SDK folders are never removed.", wraplength=600).pack(anchor="w", pady=(2, 4))
        ttk.Label(
            body,
            text="This does not remove your Steam game, APKs, save archives, build logs, or SDKs installed outside the builder's managed folder. Removing downloaded tools means they may need to download again for the next build.",
            wraplength=600,
            foreground="#444",
        ).pack(anchor="w", pady=(12, 0))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom", pady=(16, 0))
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")

        def remove_selected() -> None:
            selected_categories = [title for title, variable in selections.items() if variable.get()]
            if not selected_categories:
                messagebox.showinfo(APP_TITLE, "Select at least one category to remove.", parent=window)
                return
            summary = "\n".join(
                f"• {title}: {format_bytes(size)}"
                for title, _paths, size in present
                if title in selected_categories
            )
            if not messagebox.askyesno(
                APP_TITLE,
                "Permanently remove these AVS03-managed files? Recovered workspaces may contain edits.\n\n" + summary,
                parent=window,
            ):
                return
            window.destroy()
            self._set_busy(True, "Cleaning up selected builder files…", indeterminate=True)
            threading.Thread(
                target=self._cleanup_worker,
                args=(
                    "Downloaded build tools and public GodotSteam package cache" in selected_categories,
                    "Recovered game project workspaces" in selected_categories,
                    "Temporary Godot and GDRE profiles" in selected_categories,
                    "Android SDK in the AVS03-managed folder" in selected_categories,
                ),
                daemon=True,
            ).start()

        ttk.Button(buttons, text="Remove Selected Files", command=remove_selected).pack(side="right", padx=(0, 8))

    def _cleanup_worker(self, remove_downloads: bool, remove_workspaces: bool, remove_temp_profiles: bool, remove_sdk: bool) -> None:
        try:
            freed, errors = remove_managed_files(
                remove_downloads=remove_downloads,
                remove_workspaces=remove_workspaces,
                remove_temp_profiles=remove_temp_profiles,
                remove_managed_sdk=remove_sdk,
            )
            self.events.put(("cleanup-result", (freed, errors)))
        except Exception as exc:
            self.events.put(("cleanup-result", (0, [str(exc)])))

    def _set_busy(self, busy: bool, status: str, indeterminate: bool = False) -> None:
        self._busy = busy
        self.build_button.configure(state="disabled" if busy else "normal")
        self._refresh_update_button()
        self.save_button.configure(state="disabled" if busy else "normal")
        self.cleanup_button.configure(state="disabled" if busy else "normal")
        self.save_checkbutton.configure(state="disabled" if busy else "normal")
        if hasattr(self, "check_updates_button"):
            self.check_updates_button.configure(state="disabled" if busy or self.update_check_running else "normal")
        self.status_var.set(status)
        if busy:
            if indeterminate:
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
            else:
                self.progress.stop()
                self.progress.configure(mode="determinate", maximum=100, value=0)
                self.build_progress_value = 0.0
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100, value=self.build_progress_value)

    def _ask_download_consent(
        self,
        title: str,
        details: str,
        web_pages: tuple[tuple[str, str], ...],
        accept_label: str = "Accept and Continue",
    ) -> bool:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(True, True)
        self._fit_dialog(dialog, 700, 560, 560, 380)
        result = {"accepted": False}
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 10))
        ttk.Label(body, text=details, justify="left", wraplength=640).pack(anchor="w", fill="x")
        ttk.Label(body, text="Review these webpages if you want to read the source information or terms before continuing:").pack(anchor="w", pady=(16, 6))
        links = ttk.Frame(body)
        links.pack(anchor="w", fill="x")
        for label, url in web_pages:
            link = ttk.Label(links, text=label, foreground="#145da0", cursor="hand2")
            link.pack(anchor="w", pady=2)
            link.bind("<Button-1>", lambda _event, target=url: webbrowser.open(target))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom", pady=(18, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text=accept_label,
            command=lambda: (result.update(accepted=True), dialog.destroy()),
        ).pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        dialog.focus_set()
        self.wait_window(dialog)
        return result["accepted"]

    def start_android_export(self) -> None:
        self._start_android_export(use_cached_project=False)

    def start_android_update(self) -> None:
        self._start_android_export(use_cached_project=True)

    def start_selected_build(self) -> None:
        self._start_android_export(use_cached_project=self.update_mode_var.get())

    def _start_android_export(self, use_cached_project: bool) -> None:
        game_text = self.game_executable_var.get().strip()
        game_executable = Path(game_text).expanduser() if game_text else None
        cached_project = self.cached_project_path if use_cached_project else None
        output = Path(self.apk_var.get()).expanduser()
        if use_cached_project and (cached_project is None or not (cached_project / "project.godot").is_file()):
            self.cached_project_path = None
            self._refresh_update_button()
            messagebox.showerror(APP_TITLE, "The cached recovered project is unavailable. Run Build Android APK once to recover the game again.", parent=self)
            return
        if not use_cached_project and (game_executable is None or not game_executable.is_file()):
            messagebox.showerror(APP_TITLE, "Select an existing game executable.", parent=self)
            return
        if not output.name.lower().endswith(".apk"):
            messagebox.showerror(APP_TITLE, "Choose an output filename ending in .apk.", parent=self)
            return
        if game_executable is not None and game_executable.resolve() == output.resolve():
            messagebox.showerror(APP_TITLE, "The APK output cannot overwrite the game executable.", parent=self)
            return
        if not self._ask_download_consent(
            "Before this build downloads tools",
            ("This update reuses the last recovered project and skips game recovery. Godot, Java, export templates, Android SDK components, or public GodotSteam libraries may still need setup if they are missing. All files stay on this computer; no game files are uploaded. No webpage will open unless you select one below."
             if use_cached_project else
             "A first build may download GDRE Tools to recover the local project, Godot and its Android export templates, and Eclipse Temurin Java. If needed, the builder will ask separately before downloading public GodotSteam Android libraries and—on the SDK Downloader edition—Google Android SDK packages. Downloads are stored on this computer; your game files are not uploaded. No webpage will open unless you select one below."),
            (
                ("GDRE Tools releases", GDRE_RELEASES_URL),
                ("Godot releases", GODOT_RELEASES_URL),
                ("Eclipse Temurin releases", TEMURIN_URL),
                ("GodotSteam Asset Library listing", GODOTSTEAM_ASSET_URL),
                ("GodotSteam upstream package", GODOTSTEAM_ARCHIVE_URL),
                ("Google Android SDK terms", ANDROID_SDK_TERMS_URL),
                ("Google Android CLI package install documentation", ANDROID_CLI_DOCS_URL),
            ),
            accept_label="Continue to Build",
        ):
            return
        package_cache_verified = has_verified_package_cache(TOOLS_ROOT)
        public_package_consent = package_cache_verified
        if not package_cache_verified:
            if not self._ask_download_consent(
                "Public GodotSteam Android package",
                f"The recovered project may need Android ARM64 Steamworks libraries. This builder can download the public GodotSteam {GODOTSTEAM_VERSION} package, verify its pinned SHA-256 checksum, and copy only the three required Android ARM64 library files into the private recovered project. The archive is cached in this computer's AVS03 tool folder. No game files are uploaded. Review the included package notices and applicable upstream terms before continuing.\n\nContinue with this package download?",
                (("Godot Asset Library listing", GODOTSTEAM_ASSET_URL), ("Upstream Codeberg package", GODOTSTEAM_ARCHIVE_URL)),
            ):
                return
            public_package_consent = True
        sdk = Path(self.android_sdk_var.get()).expanduser()
        missing_sdk_parts = validate_android_sdk(sdk)
        allow_sdk_download = False
        accepted_sdk_licenses = False
        if missing_sdk_parts:
            missing = "\n".join(f"• {item}" for item in missing_sdk_parts)
            if SDK_DOWNLOADER_EDITION:
                accepted_sdk_licenses = self._ask_download_consent(
                    "Android SDK download and license consent",
                    "The selected SDK is missing required packages. This edition can download Google's official command-line tools and SDK components into this computer's AVS03 tool folder. SDK files are not included in the release. The download may be several gigabytes.\n\nBy choosing Accept and Continue, you authorize this build to download the listed packages and accept their package license prompts. Review Google's terms before agreeing.\n\nMissing from the selected folder:\n" + missing,
                    (("Android SDK terms", ANDROID_SDK_TERMS_URL), ("Android CLI install documentation", ANDROID_CLI_DOCS_URL)),
                )
                if not accepted_sdk_licenses:
                    messagebox.showinfo(APP_TITLE, "No SDK downloads or license acceptances were performed. Install the SDK through Android Studio or select an existing SDK folder.", parent=self)
                    return
                sdk = TOOLS_ROOT / "android-sdk"
                allow_sdk_download = True
            else:
                messagebox.showerror(
                    APP_TITLE,
                    "Select a complete Android SDK root. Install the required components in Android Studio → Tools → SDK Manager, then select the SDK Location shown there.\n\nMissing or invalid components:\n" + missing,
                    parent=self,
                )
                return
        try:
            TOOLS_ROOT.mkdir(parents=True, exist_ok=True)
            (TOOLS_ROOT / "android-sdk-path.txt").write_text(str(sdk.resolve()), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not save the selected SDK path.\n\n{exc}", parent=self)
            return
        include_saves = self.include_saves_var.get() and not use_cached_project
        build_log = output.with_suffix(".build.log")
        try:
            build_log.parent.mkdir(parents=True, exist_ok=True)
            build_log.write_text(
                "AVS03 Android Recompiler build log\n"
                f"Started: {time.strftime('%Y-%m-%d %H:%M:%S %z')}\n"
                f"Operating system: {platform.platform()}\n"
                f"Python: {sys.version.split()[0]}\n"
                f"Game executable: {game_executable or '(cached recovered project)'}\n"
                f"Reuse cached recovered project: {use_cached_project}\n"
                f"GodotSteam package: public {GODOTSTEAM_VERSION} package ({GODOTSTEAM_ASSET_URL})\n"
                f"GodotSteam package download consent or verified prior cache: {public_package_consent}\n"
                f"Android SDK root: {sdk.resolve()}\n"
                f"SDK downloader edition: {SDK_DOWNLOADER_EDITION}\n"
                f"SDK download/license consent: {accepted_sdk_licenses}\n"
                f"APK output: {output}\n"
                f"Include desktop saves: {include_saves}"
                + (" (disabled for cached APK update to preserve phone data)\n\n" if use_cached_project else "\n\n"),
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not create the build log at:\n{build_log}\n\n{exc}", parent=self)
            return
        self.build_log_path = build_log
        self.log_button.configure(state="normal")
        self._set_busy(True, "Starting cached APK update…" if use_cached_project else "Starting recovery and Android build…")
        threading.Thread(
            target=self._build_pipeline_worker,
            args=(game_executable, output, include_saves, sdk.resolve(), allow_sdk_download, accepted_sdk_licenses, build_log, use_cached_project, cached_project),
            daemon=True,
        ).start()

    def _build_pipeline_worker(
        self,
        game_executable: Path | None,
        output: Path,
        include_saves: bool,
        android_sdk: Path,
        allow_sdk_download: bool,
        accepted_sdk_licenses: bool,
        build_log: Path,
        use_cached_project: bool,
        cached_project: Path | None,
    ) -> None:
        def write_log(message: str) -> None:
            with build_log.open("a", encoding="utf-8", errors="replace") as log:
                log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message.rstrip()}\n")

        progress_state = {"value": 0.0, "start": 0.0, "end": 0.0}
        last_progress_event = {"time": 0.0}

        def report_progress(value: float, message: str, force: bool = False) -> None:
            value = min(100.0, max(progress_state["value"], value))
            now = time.monotonic()
            if not force and value - progress_state["value"] < 0.35 and now - last_progress_event["time"] < 0.75:
                return
            progress_state["value"] = value
            last_progress_event["time"] = now
            self.events.put(("progress", (value, message)))

        def select_progress_stage(message: str, fallback_start: float, fallback_end: float) -> tuple[float, float]:
            lower = message.lower()
            if "recovering game files" in lower:
                return 8, 30
            if "godotsteam" in lower or "android arm64 libraries" in lower:
                return 30, 32
            if "setting up godot" in lower:
                return 32, 34
            if "gdre" in lower:
                return 0, 8
            if "openjdk" in lower or "jdk" in lower:
                return 34, 42
            if "installing the android sdk from" in lower or "finding the official android" in lower:
                return 42, 45
            if "downloading android-commandline" in lower or "command-line tools" in lower:
                return 45, 51
            if "installing the approved android sdk packages" in lower or "sdkmanager" in lower:
                return 51, 66
            if "android sdk" in lower or "sdk packages" in lower:
                return 42, 51
            if "export template" in lower:
                return 76, 82
            if "godot" in lower:
                return 66, 76
            if "optional desktop save" in lower:
                return 82, 84
            if "applying the digital controller" in lower or "exporting the apk" in lower:
                return 84, 86
            return fallback_start, fallback_end

        def progress(message: str) -> None:
            write_log(message)
            start, end = select_progress_stage(message, progress_state["start"], progress_state["end"])
            progress_state["start"], progress_state["end"] = start, end
            parsed = re.search(r"(?<![\d.])(\d{1,3})%(?!\d)", message)
            fraction = min(int(parsed.group(1)), 100) / 100 if parsed else 0.02
            report_progress(start + (end - start) * fraction, message, force=not parsed)

        try:
            if use_cached_project:
                recovered_project = cached_project
                if recovered_project is None or not (recovered_project / "project.godot").is_file():
                    raise RuntimeError("The cached recovered project is unavailable. Run a full build to recover the game again.")
                progress("Reusing the cached recovered game project…")
            else:
                if game_executable is None:
                    raise RuntimeError("Select the game's executable before recovering the project.")
                progress("Preparing GDRE Tools…")
                gdre = ensure_gdre_tool(progress)
                recovery_input = find_companion_pack(game_executable) or game_executable
                recovery_root = TOOLS_ROOT / "workspaces"
                recovery_root.mkdir(parents=True, exist_ok=True)
                safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", game_executable.stem).strip("._") or "game"
                recovered_project = recovery_root / f"{safe_stem}-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}"
                recovered_project.parent.mkdir(parents=True, exist_ok=True)
                progress(f"Recovering game files from {recovery_input.name}…")
                env = os.environ.copy()
                if sys.platform != "win32":
                    profile = Path(tempfile.gettempdir()) / "avs03-gdre-profile"
                    for name in ("data", "config", "cache"):
                        (profile / name).mkdir(parents=True, exist_ok=True)
                    env["XDG_DATA_HOME"] = str(profile / "data")
                    env["XDG_CONFIG_HOME"] = str(profile / "config")
                    env["XDG_CACHE_HOME"] = str(profile / "cache")
                recovery = subprocess.Popen(
                    [str(gdre), "--headless", f"--recover={recovery_input}", f"--output={recovered_project}"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors="replace",
                    bufsize=1,
                    cwd=str(recovery_root),
                    env=env,
                )
                recovery_lines = []
                recovery_range = (8.0, 11.0)
                if recovery.stdout is not None:
                    for line in recovery.stdout:
                        recovery_lines.append(line)
                        lower_line = line.lower()
                        if "loading import files" in lower_line:
                            recovery_range = (8.0, 12.0)
                        elif "loading gdscript cache" in lower_line:
                            recovery_range = (12.0, 16.0)
                        elif "reading pck archive" in lower_line:
                            recovery_range = (16.0, 21.0)
                        elif "exporting resources" in lower_line:
                            recovery_range = (21.0, 29.0)
                        elif "recovery finished" in lower_line:
                            report_progress(30, "Finishing game recovery…")
                        parsed = re.search(r"(?<![\d.])(\d{1,3})%(?!\d)", line)
                        if parsed:
                            percent = min(int(parsed.group(1)), 100)
                            start, end = recovery_range
                            report_progress(start + (end - start) * percent / 100, "Recovering game files…")
                recovery_code = recovery.wait()
                recovery_log = "".join(recovery_lines)
                write_log(f"GDRE exit code: {recovery_code}\n=== GDRE recovery output ===\n{recovery_log}\n=== End GDRE recovery output ===")
                if not (recovered_project / "project.godot").is_file():
                    raise RuntimeError("GDRE Tools could not recover a Godot project from that executable or its companion PCK. Select the game's executable from its complete Steam install.")
                (recovered_project / "gdre-cli-output.txt").write_text(recovery_log, encoding="utf-8", errors="replace")
                metadata = TOOLS_ROOT / "last-recovered-project.json"
                temporary_metadata = metadata.with_suffix(".tmp")
                temporary_metadata.write_text(json.dumps({"project_path": str(recovered_project.resolve())}, indent=2), encoding="utf-8")
                temporary_metadata.replace(metadata)
                self.events.put(("cached-project", recovered_project))
            write_log(f"Using recovered project: {recovered_project}")
            progress(f"Checking public GodotSteam {GODOTSTEAM_VERSION} Android ARM64 libraries…")
            installed = install_public_android_libraries(recovered_project, TOOLS_ROOT, progress)
            if installed:
                write_log("Installed public Android libraries: " + ", ".join(str(path) for path in installed))
            progress("Setting up Godot, export templates, OpenJDK, and Android SDK…")
            tools = setup_export_tools(recovered_project, progress, android_sdk, allow_sdk_download, accepted_sdk_licenses)
            report_progress(82, "Android tools are ready.", force=True)
            with tempfile.TemporaryDirectory(prefix="avs03-save-transfer-") as save_temp_dir:
                save_archive = None
                if include_saves:
                    save_root = detect_save_folder()
                    if not save_root:
                        raise RuntimeError("Include desktop saves is enabled, but the game's desktop save folder was not found. Turn the option off or use Transfer Saves to choose a save folder.")
                    save_archive, _ = create_save_transfer_archive(save_root, Path(save_temp_dir) / SAVE_TRANSFER_NAME)
                    progress("Preparing the optional desktop save transfer…")
                patch_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "android_patch"
                progress("Applying the digital controller changes and exporting the APK…")

                def export_progress(stage: str, percent: int, message: str) -> None:
                    if stage == "import":
                        report_progress(86 + 6 * percent / 100, message)
                    else:
                        report_progress(92 + 7 * percent / 100, message)

                apk = export_android_apk(
                    recovered_project,
                    Path(tools["godot"]),
                    output,
                    patch_dir,
                    tool_paths=tools,
                    save_archive=save_archive,
                    build_log_path=build_log,
                    progress_callback=export_progress,
                )
            report_progress(100, "APK build complete.", force=True)
            write_log(f"Build succeeded. APK: {apk}\nRecovered project: {recovered_project}")
            self.events.put(("build-result", (True, apk, build_log, recovered_project, include_saves)))
        except Exception as exc:
            write_log(f"BUILD FAILED: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            self.events.put(("build-result", (False, f"{exc}\n\nFull build log:\n{build_log}", build_log, None, include_saves)))

    def open_build_log(self) -> None:
        log_path = self.build_log_path
        if not log_path or not log_path.is_file():
            messagebox.showinfo(APP_TITLE, "The build log will appear here after the build starts.", parent=self)
            return
        window = tk.Toplevel(self)
        window.title("AVS03 Build Log")
        self._fit_dialog(window, 900, 620, 560, 400)
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        ttk.Label(body, text=f"Log file: {log_path}", wraplength=860).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        text = tk.Text(body, wrap="none", height=30, width=110)
        scroll_y = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        scroll_x = ttk.Scrollbar(body, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        text.grid(row=1, column=0, sticky="nsew")
        scroll_y.grid(row=1, column=1, sticky="ns")
        scroll_x.grid(row=2, column=0, sticky="ew")
        try:
            text.insert("1.0", log_path.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            text.insert("1.0", f"Could not read build log: {exc}")
        text.configure(state="disabled")
        actions = ttk.Frame(body)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_status = tk.StringVar(value="")
        ttk.Label(actions, textvariable=copy_status).grid(row=0, column=0, sticky="w")
        ttk.Button(
            actions,
            text="Copy All Log Text",
            command=lambda: self.copy_log_view(text, window, copy_status),
        ).grid(row=0, column=1, sticky="e")

    def copy_log_view(self, text_widget: tk.Text, window: tk.Toplevel, status: tk.StringVar) -> None:
        """Copy the complete text currently shown in the build log viewer."""
        try:
            contents = text_widget.get("1.0", "end-1c")
            window.clipboard_clear()
            window.clipboard_append(contents)
            window.update_idletasks()
            status.set(
                f"Copied all {len(contents):,} characters. Paste only this log text into the project's GitHub Issues page: https://github.com/SoundWaveless/AVS03-Android-Recompiler/issues/new?template=build-log.yml. Do not attach files."
            )
        except tk.TclError as exc:
            status.set(f"Could not copy the log text: {exc}")

    def copy_build_log(self, log_path: Path) -> None:
        try:
            contents = log_path.read_text(encoding="utf-8", errors="replace")
            self.clipboard_clear()
            self.clipboard_append(contents)
            self.update()
            messagebox.showinfo(
                APP_TITLE,
                "Build log copied. Paste only the log text into the project's GitHub Issues page: https://github.com/SoundWaveless/AVS03-Android-Recompiler/issues/new?template=build-log.yml. Do not attach files.",
                parent=self,
            )
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not read the build log:\n{exc}", parent=self)

    def open_save_transfer(self) -> None:
        if self.save_transfer_window is not None and self.save_transfer_window.winfo_exists():
            self.save_transfer_window.lift()
            return
        window = tk.Toplevel(self)
        window.title("Transfer Game Saves")
        self._fit_dialog(window, 720, 430, 560, 360)
        window.transient(self)
        self.save_transfer_window = window
        body = ttk.Frame(window, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Transfer desktop saves to Android", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="Create a ZIP from the game's Godot user data folder. The Android build imports it before loading profiles. Steam-ID folders are flattened to the game's local profile layout.",
            wraplength=660,
        ).pack(anchor="w", pady=(6, 10))
        detected = detect_save_folder()
        self.save_root_var = tk.StringVar(value=str(detected or Path.home()))
        self.save_archive_var = tk.StringVar(value=str(desktop_path(SAVE_TRANSFER_NAME)))
        self.save_send_var = tk.BooleanVar(value=True)
        self.save_serial_var = tk.StringVar()
        self.save_package_var = tk.StringVar(value=ANDROID_PACKAGE)
        self._save_path_row(body, "Desktop game data folder", self.save_root_var, self.pick_save_root)
        self._save_path_row(body, "Save transfer ZIP", self.save_archive_var, self.pick_save_archive)
        ttk.Checkbutton(body, text="Also send directly to a connected Android phone (USB debugging required)", variable=self.save_send_var).pack(anchor="w", pady=(10, 3))
        self._save_entry_row(body, "ADB device serial (leave blank if only one phone is connected)", self.save_serial_var)
        self._save_entry_row(body, "Android package name", self.save_package_var)
        self.save_transfer_status = tk.StringVar(value="Direct transfer requires the debug APK exported by this builder.")
        ttk.Label(body, textvariable=self.save_transfer_status, wraplength=660).pack(anchor="w", pady=(10, 0))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom", pady=(14, 0))
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")
        ttk.Button(buttons, text="Create Save Transfer", command=self.create_save_transfer).pack(side="right", padx=(0, 8))

    def _save_path_row(self, parent, label: str, variable, command) -> None:
        ttk.Label(parent, text=label).pack(anchor="w", pady=(6, 3))
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=command).pack(side="left", padx=(8, 0))

    def _save_entry_row(self, parent, label: str, variable) -> None:
        ttk.Label(parent, text=label).pack(anchor="w", pady=(6, 3))
        ttk.Entry(parent, textvariable=variable).pack(fill="x")

    def pick_save_root(self) -> None:
        selected = filedialog.askdirectory(title="Select Antivirus Survivors user data folder", parent=self.save_transfer_window)
        if selected:
            self.save_root_var.set(selected)

    def pick_save_archive(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Save Android transfer archive",
            parent=self.save_transfer_window,
            initialfile=SAVE_TRANSFER_NAME,
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip")],
        )
        if selected:
            self.save_archive_var.set(selected)

    def create_save_transfer(self) -> None:
        try:
            archive_path, file_count = create_save_transfer_archive(
                Path(self.save_root_var.get()).expanduser(), Path(self.save_archive_var.get()).expanduser()
            )
            sent_to = ""
            if self.save_send_var.get():
                if not messagebox.askyesno(
                    APP_TITLE,
                    "Send this save archive to the connected phone? On the next launch, imported slots replace same-numbered phone slots.",
                    parent=self.save_transfer_window,
                ):
                    self.save_transfer_status.set(f"Transfer archive ready ({file_count} save/config files): {archive_path}")
                    return
                serial = send_save_archive_to_phone(archive_path, self.save_package_var.get().strip(), self.save_serial_var.get().strip())
                sent_to = f"\nCopied to phone {serial}. Close the game fully and start it again to import the saves."
            self.save_transfer_status.set(f"Transfer archive ready ({file_count} save/config files): {archive_path}{sent_to}")
            messagebox.showinfo(
                APP_TITLE,
                f"Created save transfer ZIP:\n{archive_path}" + (f"\n\nSent to Android device {serial}. Restart the game to import the saves." if sent_to else ""),
                parent=self.save_transfer_window,
            )
        except Exception as exc:
            self.save_transfer_status.set("Save transfer could not be completed.")
            messagebox.showerror(APP_TITLE, str(exc), parent=self.save_transfer_window)

    def _process_events(self) -> None:
        if self._closed:
            return
        try:
            kind, payload = self.events.get_nowait()
        except queue.Empty:
            self._process_events_after_id = self.after(120, self._process_events)
            return
        if kind == "progress":
            percent, message = payload
            self.build_progress_value = max(self.build_progress_value, float(percent))
            self.progress.configure(value=self.build_progress_value)
            self.status_var.set(f"{round(self.build_progress_value)}% — {message}")
        elif kind == "build-result":
            self._set_busy(False, self.status_var.get())
            succeeded, result, log_path, recovered_project, included_saves = payload
            if succeeded:
                self.status_var.set(f"APK ready: {result}")
                detail = f"APK exported to:\n{result}\n\nRecovered project:\n{recovered_project}\n\nBuild log:\n{log_path}"
                if included_saves:
                    detail += "\n\nDesktop saves were included for first-launch import."
                messagebox.showinfo(APP_TITLE, detail + "\n\nUse View / Copy Build Log to copy the full log if needed.", parent=self)
            else:
                self.status_var.set("Build failed. See the error details.")
                messagebox.showerror(
                    APP_TITLE,
                    str(result)
                    + "\n\nUse View / Copy Build Log to copy the full log. For help, paste only the log text into the project's GitHub Issues page: https://github.com/SoundWaveless/AVS03-Android-Recompiler/issues/new?template=build-log.yml. Do not attach files.",
                    parent=self,
                )
        elif kind == "cached-project":
            self.cached_project_path = Path(payload)
            self._refresh_update_button()
        elif kind == "update-check":
            self.update_check_running = False
            self._set_busy(False, "Update check complete.")
            update, error = payload
            if error:
                self.status_var.set("Could not check for updates.")
                messagebox.showerror(APP_TITLE, str(error), parent=self)
            elif not update["available"]:
                self.status_var.set(f"Builder is up to date (v{update['latest_version']}).")
                messagebox.showinfo(APP_TITLE, f"You are using the latest builder release (v{update['latest_version']}).", parent=self)
            elif messagebox.askyesno(
                APP_TITLE,
                f"Version {update['latest_version']} is available for this operating system and edition.\n\nDownload and install it now? The installer verifies the archive's SHA-256 before replacing builder files.",
                parent=self,
            ):
                self._install_update(update)
            else:
                self.status_var.set(f"Version {update['latest_version']} is available.")
        elif kind == "update-progress":
            downloaded, total = payload
            percent = min(99.0, 100.0 * int(downloaded) / max(int(total), 1))
            self.progress.configure(value=percent)
            self.status_var.set(f"Downloading verified update… {round(percent)}%")
        elif kind == "update-installed":
            self._set_busy(False, "Update installed.")
            version, count = payload
            self.status_var.set(f"Update v{version} installed ({count} files).")
            if messagebox.askyesno(APP_TITLE, f"Version {version} is installed. Restart the builder now to use it?", parent=self):
                install_dir = get_install_directory(__file__)
                if getattr(sys, "frozen", False) and sys.platform == "win32":
                    python_launcher = shutil.which("py") or shutil.which("python")
                    source = install_dir / "avs03_wrapper_builder.py"
                    command = [python_launcher, str(source)] if python_launcher and source.is_file() else [sys.executable]
                else:
                    command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
                subprocess.Popen(command, cwd=install_dir, close_fds=True)
                self.close_app()
        elif kind == "update-failed":
            self._set_busy(False, "Update could not be installed.")
            messagebox.showerror(APP_TITLE, str(payload), parent=self)
        elif kind == "cleanup-result":
            self._set_busy(False, self.status_var.get())
            self.cached_project_path = self._read_cached_project()
            self._refresh_update_button()
            freed, errors = payload
            if errors:
                self.status_var.set("Cleanup finished with some files left behind.")
                messagebox.showwarning(
                    APP_TITLE,
                    f"Removed approximately {format_bytes(freed)}.\n\nSome files could not be removed:\n" + "\n".join(errors),
                    parent=self,
                )
            else:
                self.status_var.set(f"Cleanup complete: freed approximately {format_bytes(freed)}.")
                messagebox.showinfo(APP_TITLE, f"Cleanup complete. Freed approximately {format_bytes(freed)}.", parent=self)
        if not self._closed:
            self._process_events_after_id = self.after(120, self._process_events)


if __name__ == "__main__":
    Builder().mainloop()
