"""Update bootstrapper: checks GitHub, offers the matching package, then launches AVS03."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from update_manager import (
    APP_VERSION,
    UpdateError,
    check_latest_release,
    detect_sdk_downloader,
    download_release_asset,
    get_install_directory,
    get_installed_version,
    install_release_package,
)


class Updater(tk.Tk):
    def __init__(self, target: Path, auto_launch: bool = True) -> None:
        super().__init__()
        self.target = target.resolve()
        self.auto_launch = auto_launch
        self.current_version = get_installed_version(self.target, APP_VERSION)
        self.sdk_downloader = detect_sdk_downloader(self.target)
        self.latest: dict[str, object] | None = None
        self._busy = False
        self.title("AVS03 Compiler Updater")
        self.geometry("600x330")
        self.minsize(400, 280)
        self.resizable(True, True)

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="AVS03 Compiler Updater", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self.version_var = tk.StringVar(value=f"Installed version: {self.current_version}")
        ttk.Label(body, textvariable=self.version_var).pack(anchor="w", pady=(8, 0))
        self.description_label = ttk.Label(body, text="Checks the official GitHub release and selects the package for this OS and edition. Nothing is downloaded or installed without your approval. Game files, APKs, and saves are not included or changed.", wraplength=540)
        self.description_label.pack(anchor="w", fill="x", pady=(8, 10))
        self.status_var = tk.StringVar(value="Checking GitHub for updates…")
        self.status_label = ttk.Label(body, textvariable=self.status_var, wraplength=540)
        self.status_label.pack(anchor="w", fill="x")
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(12, 10))
        actions = ttk.Frame(body)
        actions.pack(fill="x")
        self.update_button = ttk.Button(actions, text="Download and Install", command=lambda: self.install_update(consented=True), state="disabled")
        self.launch_button = ttk.Button(actions, text="Launch Builder", command=self.launch_builder, state="disabled")
        self.close_button = ttk.Button(actions, text="Close", command=self.destroy)
        self._action_buttons = (self.update_button, self.launch_button, self.close_button)
        self._actions_layout = None
        actions.bind("<Configure>", self._layout_action_buttons)
        body.bind("<Configure>", self._resize_text)
        self._layout_action_buttons()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(100, self.check)

    def _resize_text(self, event) -> None:
        width = max(180, event.width - 40)
        self.description_label.configure(wraplength=width)
        self.status_label.configure(wraplength=width)

    def _layout_action_buttons(self, event=None) -> None:
        width = event.width if event is not None else self.winfo_width()
        required_row_width = sum(button.winfo_reqwidth() for button in self._action_buttons) + 18
        layout = "stacked" if width < required_row_width else "row"
        if layout == self._actions_layout:
            return
        self._actions_layout = layout
        actions = self._action_buttons[0].master
        for column in range(3):
            actions.columnconfigure(column, weight=0)
        for button in self._action_buttons:
            button.grid_forget()
        if layout == "stacked":
            for row, button in enumerate(self._action_buttons):
                button.grid(row=row, column=0, sticky="ew", pady=(0, 5))
            actions.columnconfigure(0, weight=1)
        else:
            for column, button in enumerate(self._action_buttons):
                button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0))
                actions.columnconfigure(column, weight=1)

    def check(self) -> None:
        self.status_var.set("Checking the latest GitHub release…")
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self) -> None:
        try:
            info = check_latest_release(self.current_version, self.sdk_downloader)
            self.after(0, lambda: self._show_check(info, None))
        except Exception as exc:
            self.after(0, lambda detail=str(exc): self._show_check(None, detail))

    def _show_check(self, info: dict[str, object] | None, error: str | None) -> None:
        if not self.winfo_exists():
            return
        if error:
            self.status_var.set("Could not check GitHub. Launching the installed version…")
            self.launch_button.configure(state="normal")
            if self.auto_launch:
                self.after(1200, self.launch_builder)
            return
        self.latest = info
        assert info is not None
        if bool(info["available"]):
            self.status_var.set(f"Version {info['latest_version']} is available for this OS and edition.")
            self.update_button.configure(state="normal")
            self.launch_button.configure(state="normal")
            if self.auto_launch:
                self.after(100, self._offer_update)
        else:
            self.status_var.set(f"You have the latest release (v{info['latest_version']}).")
            self.launch_button.configure(state="normal")
            if self.auto_launch:
                self.after(900, self.launch_builder)

    def _offer_update(self) -> None:
        if not self.winfo_exists() or self.latest is None:
            return
        if messagebox.askyesno(
            "AVS03 update available",
            f"Version {self.latest['latest_version']} is available. Do you want to download and install the matching compiler package now? Choose No to keep the current build and launch it unchanged.",
            parent=self,
        ):
            self.install_update(consented=True)
        elif self.auto_launch:
            self.launch_builder()

    def install_update(self, consented: bool = False) -> None:
        if not consented or self._busy or self.latest is None:
            return
        self._busy = True
        self.update_button.configure(state="disabled")
        self.launch_button.configure(state="disabled")
        self.status_var.set(f"Downloading {self.latest['asset_name']}…")
        threading.Thread(target=self._install_worker, args=(self.latest,), daemon=True).start()

    def _install_worker(self, info: dict[str, object]) -> None:
        archive = self.target / ".avs03-update-download.zip"
        try:
            download_release_asset(info, archive, lambda done, total: self.after(0, self._set_progress, done, total))
            self.after(0, lambda: self.status_var.set("Verified download. Installing builder files…"))
            installed = install_release_package(archive, self.target)
            self.after(0, lambda: self._installed(info, len(installed)))
        except Exception as exc:
            self.after(0, lambda detail=str(exc): self._install_failed(detail))
        finally:
            archive.unlink(missing_ok=True)

    def _set_progress(self, done: int, total: int) -> None:
        if self.winfo_exists():
            self.progress.configure(value=100.0 * done / max(total, 1))
            self.status_var.set(f"Downloading update… {round(100.0 * done / max(total, 1))}%")

    def _installed(self, info: dict[str, object], count: int) -> None:
        self._busy = False
        if not self.winfo_exists():
            return
        self.status_var.set(f"Updated to v{info['latest_version']} ({count} files). Launching the builder…")
        self.after(900, self.launch_builder)

    def _install_failed(self, detail: str) -> None:
        self._busy = False
        if not self.winfo_exists():
            return
        self.status_var.set("Update could not be installed. Your existing files were preserved where possible.")
        self.launch_button.configure(state="normal")
        messagebox.showerror("AVS03 update failed", detail, parent=self)

    def launch_builder(self) -> None:
        if self._busy:
            return
        try:
            command = self._builder_command()
            subprocess.Popen(command, cwd=self.target, close_fds=True)
            self.destroy()
        except Exception as exc:
            self.status_var.set("Could not locate or start the builder.")
            messagebox.showerror("AVS03 updater", str(exc), parent=self)

    def _builder_command(self) -> list[str]:
        source = self.target / "avs03_wrapper_builder.py"
        if source.is_file():
            interpreter = sys.executable
            if getattr(sys, "frozen", False):
                interpreter = shutil.which("py" if sys.platform == "win32" else "python3") or shutil.which("python") or ""
            if interpreter:
                return [interpreter, str(source)]
            raise UpdateError("A Python runtime is needed to launch this source-based Windows builder.")
        executable_names = (
            ("AVS03-Android-Builder-SDK-Downloader.exe", "AVS03-Android-Builder-SDK-Downloader")
            if self.sdk_downloader else ("AVS03-Android-Builder.exe", "AVS03-Android-Builder")
        )
        for name in executable_names:
            candidate = self.target / name
            if candidate.is_file():
                return [str(candidate)]
        raise UpdateError(f"No AVS03 builder launcher was found in:\n{self.target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check GitHub for AVS03 builder updates, then launch the builder.")
    parser.add_argument("--target", type=Path, help="Builder installation folder; defaults to this updater's folder.")
    parser.add_argument("--no-auto-launch", action="store_true", help="Keep the updater open after checking without launching the builder.")
    args = parser.parse_args()
    target = args.target or get_install_directory(__file__)
    app = Updater(target, auto_launch=not args.no_auto_launch)
    app.mainloop()


if __name__ == "__main__":
    main()
