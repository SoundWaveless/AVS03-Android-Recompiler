"""Apply the Android touch patch to a user's recovered project and export an APK."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

ANDROID_PRESET = '''[preset.{index}]

name="AVS03 Android ARM64"
platform="Android"
runnable=true
advanced_options=false
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter="android/save-transfer.zip"
exclude_filter=""
export_path=""
patches=PackedStringArray()
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.{index}.options]

custom_template/debug=""
custom_template/release=""
gradle_build/use_gradle_build=false
gradle_build/export_format=0
gradle_build/android_source_template=""
gradle_build/compress_native_libraries=false
gradle_build/min_sdk=""
gradle_build/target_sdk=""
gradle_build/custom_theme_attributes={{}}
architectures/armeabi-v7a=false
architectures/arm64-v8a=true
architectures/x86=false
architectures/x86_64=false
version/code=1
version/name="0.1.0-alpha"
package/unique_name="org.avs03.android"
package/name="Antivirus Survivors 2003 Professional"
package/signed=true
package/app_category=2
package/retain_data_on_uninstall=false
package/exclude_from_recents=false
package/show_in_android_tv=false
package/show_in_app_library=true
package/show_as_launcher_app=false
graphics/opengl_debug=false
xr_features/xr_mode=0
screen/immersive_mode=true
screen/edge_to_edge=false
screen/support_small=true
screen/support_normal=true
screen/support_large=true
screen/support_xlarge=true
screen/background_color=Color(0, 0, 0, 1)
user_data_backup/allow=false
command_line/extra_args=""
apk_expansion/enable=false
permissions/custom_permissions=PackedStringArray()
permissions/internet=false
permissions/vibrate=false
permissions/wake_lock=false
'''


SETTINGS_METHODS = '''
func cycle_touch_control_mode(direction: int) -> void:
	touch_control_mode = posmod(touch_control_mode + direction, 2)
	save_settings()


func get_touch_control_mode_text() -> String:
	return "D-pad" if touch_control_mode == TOUCH_CONTROL_DPAD else "Joystick"


func cycle_touch_control_layout() -> void:
	touch_control_layout = posmod(touch_control_layout + 1, 2)
	save_settings()


func get_touch_control_layout_text() -> String:
	return "Custom" if touch_control_layout == TOUCH_LAYOUT_CUSTOM else "Classic"


func get_touch_custom_position(control: String) -> Vector2:
	var position: Variant = touch_custom_positions.get(control, TOUCH_DEFAULT_POSITIONS.get(control, Vector2(0.5, 0.5)))
	return position if position is Vector2 else Vector2(0.5, 0.5)


func set_touch_custom_position(control: String, position: Vector2) -> void:
	if not TOUCH_DEFAULT_POSITIONS.has(control):
		return
	touch_custom_positions[control] = Vector2(clampf(position.x, 0.04, 0.96), clampf(position.y, 0.08, 0.92))
	save_settings()


func get_touch_custom_scale(control: String) -> float:
	var scale: Variant = touch_custom_scales.get(control, 1.0)
	if scale is float or scale is int:
		return clampf(float(scale), 0.4, 2.0)
	return 1.0


func set_touch_custom_scale(control: String, scale: float) -> void:
	if not TOUCH_DEFAULT_POSITIONS.has(control):
		return
	touch_custom_scales[control] = clampf(scale, 0.4, 2.0)
	save_settings()


func reset_touch_control_defaults() -> void:
	touch_control_mode = TOUCH_CONTROL_JOYSTICK
	touch_control_layout = TOUCH_LAYOUT_CLASSIC
	touch_custom_positions = TOUCH_DEFAULT_POSITIONS.duplicate(true)
	touch_custom_scales = {"move": 1.0, "a": 1.0, "b": 1.0, "x": 1.0, "pause": 1.0, "lt": 1.0}
	touch_control_deadzone = 12
	touch_control_scale = 100
	touch_control_opacity = 70
	touch_control_offset_x = 0
	touch_control_offset_y = 0
	touch_pause_button_top = false
	save_settings()


func set_touch_control_deadzone(value: int) -> void:
	touch_control_deadzone = clampi(value, 0, MAX_TOUCH_DEADZONE)
	save_settings()


func set_touch_control_scale(value: int) -> void:
	touch_control_scale = clampi(value, MIN_TOUCH_SCALE, MAX_TOUCH_SCALE)
	save_settings()


func set_touch_control_opacity(value: int) -> void:
	touch_control_opacity = clampi(value, MIN_TOUCH_OPACITY, MAX_TOUCH_OPACITY)
	save_settings()


func set_touch_control_offset_x(value: int) -> void:
	touch_control_offset_x = clampi(value, -MAX_TOUCH_OFFSET, MAX_TOUCH_OFFSET)
	save_settings()


func set_touch_control_offset_y(value: int) -> void:
	touch_control_offset_y = clampi(value, -MAX_TOUCH_OFFSET, MAX_TOUCH_OFFSET)
	save_settings()


func toggle_touch_pause_button_position() -> void:
	touch_pause_button_top = not touch_pause_button_top
	save_settings()


func get_touch_pause_button_position_text() -> String:
	return "Top" if touch_pause_button_top else "Bottom"

'''


MENU_TOUCH_METHODS = '''
func build_touch_settings_page() -> void:
	add_group("Mobile Controls")
	add_step_row("touch_layout", "Control Layout", Settings.get_touch_control_layout_text(), on_touch_layout_clicked, on_touch_layout_clicked, "Classic keeps the existing controller layout. Custom lets you drag each control to a new position.")
	add_step_row("touch_arrange", "Arrange Controls", "Arrange", on_touch_arrange_clicked, on_touch_arrange_clicked, "Drag controls to move them. Use two fingers on a control to resize it, then tap Done at the top of the screen.")
	add_step_row("touch_pause_position", "Pause Button", Settings.get_touch_pause_button_position_text(), on_touch_pause_position_clicked, on_touch_pause_position_clicked, "Choose whether the virtual pause button sits at the top or bottom of the screen.")
	add_slider_row("touch_deadzone", "Analog Deadzone", Settings.touch_control_deadzone, 0, Settings.MAX_TOUCH_DEADZONE, 2, on_touch_deadzone_slider, "%d%%", "Ignore small analog movements around the stick center.")
	add_slider_row("touch_scale", "Control Size", Settings.touch_control_scale, Settings.MIN_TOUCH_SCALE, Settings.MAX_TOUCH_SCALE, 5, on_touch_scale_slider, "%d%%", "Scale the on-screen controls.")
	add_slider_row("touch_opacity", "Control Opacity", Settings.touch_control_opacity, Settings.MIN_TOUCH_OPACITY, Settings.MAX_TOUCH_OPACITY, 5, on_touch_opacity_slider, "%d%%", "Change how visible the on-screen controls are.")
	add_slider_row("touch_offset_x", "Horizontal Position", Settings.touch_control_offset_x, -Settings.MAX_TOUCH_OFFSET, Settings.MAX_TOUCH_OFFSET, 10, on_touch_offset_x_slider, "%d", "Move the movement control inward or outward.")
	add_slider_row("touch_offset_y", "Vertical Position", Settings.touch_control_offset_y, -Settings.MAX_TOUCH_OFFSET, Settings.MAX_TOUCH_OFFSET, 10, on_touch_offset_y_slider, "%d", "Move the movement control up or down.")


func on_touch_control_mode_next() -> void:
	Settings.cycle_touch_control_mode(1)
	update_ui()


func on_touch_layout_clicked() -> void:
	Settings.cycle_touch_control_layout()
	update_ui()


func on_touch_arrange_clicked() -> void:
	if Settings.touch_control_layout != Settings.TOUCH_LAYOUT_CUSTOM:
		Settings.cycle_touch_control_layout()
	AndroidTouchControls.toggle_edit_mode()
	update_ui()


func on_touch_deadzone_slider(value: int) -> void:
	Settings.set_touch_control_deadzone(value)
	set_label("touch_deadzone", "%d%%" % value)


func on_touch_scale_slider(value: int) -> void:
	Settings.set_touch_control_scale(value)
	set_label("touch_scale", "%d%%" % value)


func on_touch_opacity_slider(value: int) -> void:
	Settings.set_touch_control_opacity(value)
	set_label("touch_opacity", "%d%%" % value)


func on_touch_offset_x_slider(value: int) -> void:
	Settings.set_touch_control_offset_x(value)
	set_label("touch_offset_x", "%d" % value)


func on_touch_offset_y_slider(value: int) -> void:
	Settings.set_touch_control_offset_y(value)
	set_label("touch_offset_y", "%d" % value)


func on_touch_pause_position_clicked() -> void:
	Settings.toggle_touch_pause_button_position()
	set_label("touch_pause_position", Settings.get_touch_pause_button_position_text())

'''


def _replace_once(text: str, old: str, new: str, filename: str) -> str:
    if old not in text:
        raise ValueError(f"Cannot apply Android touch patch: expected code was not found in {filename}.")
    return text.replace(old, new, 1)


def _patch_settings(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "TOUCH_CONTROL_JOYSTICK" not in text:
        text = _replace_once(
            text,
            "const MAX_CURSOR_SPEED: int = 250\n",
            "const MAX_CURSOR_SPEED: int = 250\n"
            "const TOUCH_CONTROL_JOYSTICK: int = 0\n"
            "const TOUCH_CONTROL_DPAD: int = 1\n"
            "const MIN_TOUCH_SCALE: int = 60\n"
            "const MAX_TOUCH_SCALE: int = 150\n"
            "const MIN_TOUCH_OPACITY: int = 10\n"
            "const MAX_TOUCH_OPACITY: int = 100\n"
            "const MAX_TOUCH_DEADZONE: int = 50\n"
            "const MAX_TOUCH_OFFSET: int = 100\n"
            "const TOUCH_LAYOUT_CLASSIC: int = 0\n"
            "const TOUCH_LAYOUT_CUSTOM: int = 1\n"
            "const TOUCH_DEFAULT_POSITIONS: Dictionary = {\"move\": Vector2(0.13, 0.78), \"a\": Vector2(0.87, 0.78), \"b\": Vector2(0.94, 0.64), \"x\": Vector2(0.80, 0.64), \"pause\": Vector2(0.50, 0.92), \"lt\": Vector2(0.05, 0.08)}\n",
            str(path),
        )
        text = _replace_once(
            text,
            '"controller_vibration", "locale"]',
            '"controller_vibration", "touch_control_mode", "touch_control_layout", "touch_custom_positions", "touch_custom_scales", "touch_control_deadzone", "touch_control_scale", "touch_control_opacity", "touch_control_offset_x", "touch_control_offset_y", "touch_pause_button_top", "locale"]',
            str(path),
        )
        text = _replace_once(
            text,
            "var controller_vibration: bool = true\n",
            "var controller_vibration: bool = true\n"
            "var touch_control_mode: int = TOUCH_CONTROL_JOYSTICK\n"
            "var touch_control_layout: int = TOUCH_LAYOUT_CLASSIC\n"
            "var touch_custom_positions: Dictionary = {\"move\": Vector2(0.13, 0.78), \"a\": Vector2(0.87, 0.78), \"b\": Vector2(0.94, 0.64), \"x\": Vector2(0.80, 0.64), \"pause\": Vector2(0.50, 0.92), \"lt\": Vector2(0.05, 0.08)}\n"
            "var touch_custom_scales: Dictionary = {\"move\": 1.0, \"a\": 1.0, \"b\": 1.0, \"x\": 1.0, \"pause\": 1.0, \"lt\": 1.0}\n"
            "var touch_control_deadzone: int = 12\n"
            "var touch_control_scale: int = 100\n"
            "var touch_control_opacity: int = 70\n"
            "var touch_control_offset_x: int = 0\n"
            "var touch_control_offset_y: int = 0\n"
            "var touch_pause_button_top: bool = false\n",
            str(path),
        )
        text = _replace_once(
            text,
            "\tcontroller_vibration = config.get_value(SECTION, \"controller_vibration\", controller_vibration)\n",
            "\tcontroller_vibration = config.get_value(SECTION, \"controller_vibration\", controller_vibration)\n"
            "\ttouch_control_mode = clampi(config.get_value(SECTION, \"touch_control_mode\", touch_control_mode), TOUCH_CONTROL_JOYSTICK, TOUCH_CONTROL_DPAD)\n"
            "\ttouch_control_layout = clampi(config.get_value(SECTION, \"touch_control_layout\", touch_control_layout), TOUCH_LAYOUT_CLASSIC, TOUCH_LAYOUT_CUSTOM)\n"
            "\tvar loaded_touch_positions: Variant = config.get_value(SECTION, \"touch_custom_positions\", touch_custom_positions)\n"
            "\tif loaded_touch_positions is Dictionary:\n"
            "\t\tfor control: String in TOUCH_DEFAULT_POSITIONS:\n"
            "\t\t\tvar saved_position: Variant = loaded_touch_positions.get(control, TOUCH_DEFAULT_POSITIONS[control])\n"
            "\t\t\tif saved_position is Vector2:\n"
            "\t\t\t\ttouch_custom_positions[control] = Vector2(clampf(saved_position.x, 0.04, 0.96), clampf(saved_position.y, 0.08, 0.92))\n"
            "\tvar loaded_touch_scales: Variant = config.get_value(SECTION, \"touch_custom_scales\", touch_custom_scales)\n"
            "\tif loaded_touch_scales is Dictionary:\n"
            "\t\tfor control: String in TOUCH_DEFAULT_POSITIONS:\n"
            "\t\t\ttouch_custom_scales[control] = clampf(float(loaded_touch_scales.get(control, 1.0)), 0.4, 2.0)\n"
            "\ttouch_control_deadzone = clampi(config.get_value(SECTION, \"touch_control_deadzone\", touch_control_deadzone), 0, MAX_TOUCH_DEADZONE)\n"
            "\ttouch_control_scale = clampi(config.get_value(SECTION, \"touch_control_scale\", touch_control_scale), MIN_TOUCH_SCALE, MAX_TOUCH_SCALE)\n"
            "\ttouch_control_opacity = clampi(config.get_value(SECTION, \"touch_control_opacity\", touch_control_opacity), MIN_TOUCH_OPACITY, MAX_TOUCH_OPACITY)\n"
            "\ttouch_control_offset_x = clampi(config.get_value(SECTION, \"touch_control_offset_x\", touch_control_offset_x), -MAX_TOUCH_OFFSET, MAX_TOUCH_OFFSET)\n"
            "\ttouch_control_offset_y = clampi(config.get_value(SECTION, \"touch_control_offset_y\", touch_control_offset_y), -MAX_TOUCH_OFFSET, MAX_TOUCH_OFFSET)\n"
            "\ttouch_pause_button_top = bool(config.get_value(SECTION, \"touch_pause_button_top\", touch_pause_button_top))\n",
            str(path),
        )
        text = _replace_once(
            text,
            "\tconfig.set_value(SECTION, \"controller_vibration\", controller_vibration)\n",
            "\tconfig.set_value(SECTION, \"controller_vibration\", controller_vibration)\n"
            "\tconfig.set_value(SECTION, \"touch_control_mode\", touch_control_mode)\n"
            "\tconfig.set_value(SECTION, \"touch_control_layout\", touch_control_layout)\n"
            "\tconfig.set_value(SECTION, \"touch_custom_positions\", touch_custom_positions)\n"
            "\tconfig.set_value(SECTION, \"touch_custom_scales\", touch_custom_scales)\n"
            "\tconfig.set_value(SECTION, \"touch_control_deadzone\", touch_control_deadzone)\n"
            "\tconfig.set_value(SECTION, \"touch_control_scale\", touch_control_scale)\n"
            "\tconfig.set_value(SECTION, \"touch_control_opacity\", touch_control_opacity)\n"
            "\tconfig.set_value(SECTION, \"touch_control_offset_x\", touch_control_offset_x)\n"
            "\tconfig.set_value(SECTION, \"touch_control_offset_y\", touch_control_offset_y)\n"
            "\tconfig.set_value(SECTION, \"touch_pause_button_top\", touch_pause_button_top)\n",
            str(path),
        )
        text = _replace_once(text, "func restore_defaults(keys: Array[String]", SETTINGS_METHODS + "func restore_defaults(keys: Array[String]", str(path))
        path.write_text(text, encoding="utf-8")


def _patch_settings_menu(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "touch_settings_page_button" not in text:
        text = _replace_once(text, "var row_host: VBoxContainer\n", "var row_host: VBoxContainer\nvar touch_control_button: StandardButton\nvar touch_settings_page_button: StandardButton\n", str(path))
        text = _replace_once(
            text,
            "\tExpandIntScaler.zoom_changed.connect(update_ui)\n",
            "\tExpandIntScaler.zoom_changed.connect(update_ui)\n"
            "\tif OS.has_feature(\"android\") or DisplayServer.is_touchscreen_available():\n"
            "\t\ttouch_control_button = SETTING_STEP_BUTTON.instantiate() as StandardButton\n"
            "\t\ttouch_control_button.custom_minimum_size = Vector2(100, ROW_HEIGHT)\n"
            "\t\ttouch_control_button.clicked.connect(on_touch_control_mode_next)\n"
            "\t\tpage_row.add_child(touch_control_button)\n"
            "\t\ttouch_settings_page_button = SETTING_STEP_BUTTON.instantiate() as StandardButton\n"
            "\t\ttouch_settings_page_button.custom_minimum_size = Vector2(70, ROW_HEIGHT)\n"
            "\t\ttouch_settings_page_button.text = \"Mobile\"\n"
            "\t\ttouch_settings_page_button.clicked.connect(on_touch_settings_page_clicked)\n"
            "\t\tpage_row.add_child(touch_settings_page_button)\n",
            str(path),
        )
        text = _replace_once(text, "func on_game_tab_clicked() -> void :\n", "func on_touch_settings_page_clicked() -> void:\n\tshow_tab(Tab.CONTROLS, 2)\n\n\nfunc on_game_tab_clicked() -> void :\n", str(path))
        text = _replace_once(text, "\tif tab != Tab.CONTROLS:\n\t\tpage = 0\n", "\tif tab != Tab.CONTROLS:\n\t\tpage = 0\n\telif page == 2 and not is_instance_valid(touch_settings_page_button):\n\t\tpage = 0\n", str(path))
        text = _replace_once(text, "\tmenus_page_button.button_pressed = tab == Tab.CONTROLS and page == 1\n", "\tmenus_page_button.button_pressed = tab == Tab.CONTROLS and page == 1\n\tif is_instance_valid(touch_settings_page_button):\n\t\ttouch_settings_page_button.button_pressed = tab == Tab.CONTROLS and page == 2\n", str(path))
        text = _replace_once(text, "\tbindings_box.visible = tab == Tab.CONTROLS\n", "\tvar touch_settings_page: bool = tab == Tab.CONTROLS and page == 2\n\tbindings_box.visible = tab == Tab.CONTROLS and not touch_settings_page\n\tcontent.visible = tab != Tab.CONTROLS or touch_settings_page\n", str(path))
        text = _replace_once(text, "\tvar index: int = views.find(Vector2i(int(current_tab), controls_page))\n", "\tif is_instance_valid(touch_settings_page_button):\n\t\tviews.insert(4, Vector2i(Tab.CONTROLS, 2))\n\tvar index: int = views.find(Vector2i(int(current_tab), controls_page))\n", str(path))
        text = _replace_once(text, "func build_controls_tab() -> void :\n", "func build_controls_tab() -> void :\n\tif controls_page == 2:\n\t\tbuild_touch_settings_page()\n\t\treturn\n", str(path))
        text = _replace_once(text, "func controls_row() -> PanelContainer:\n", MENU_TOUCH_METHODS + "func controls_row() -> PanelContainer:\n", str(path))
        text = _replace_once(text, "\tmenus_page_button.set_col_size()\n", "\tmenus_page_button.set_col_size()\n\tif is_instance_valid(touch_control_button):\n\t\ttouch_control_button.set_col_size()\n\tif is_instance_valid(touch_settings_page_button):\n\t\ttouch_settings_page_button.set_col_size()\n", str(path))
        text = _replace_once(
            text,
            "\tset_label(\"cursor_speed\", \"%d%%\" % Settings.menu_cursor_speed)\n",
            "\tset_label(\"cursor_speed\", \"%d%%\" % Settings.menu_cursor_speed)\n"
            "\tif is_instance_valid(touch_control_button):\n\t\ttouch_control_button.text = \"Move: %s\" % Settings.get_touch_control_mode_text()\n"
            "\tset_label(\"touch_deadzone\", \"%d%%\" % Settings.touch_control_deadzone)\n"
            "\tset_label(\"touch_scale\", \"%d%%\" % Settings.touch_control_scale)\n"
            "\tset_label(\"touch_opacity\", \"%d%%\" % Settings.touch_control_opacity)\n"
            "\tset_label(\"touch_offset_x\", \"%d\" % Settings.touch_control_offset_x)\n"
            "\tset_label(\"touch_offset_y\", \"%d\" % Settings.touch_control_offset_y)\n"
            "\tset_label(\"touch_pause_position\", Settings.get_touch_pause_button_position_text())\n"
            "\tset_label(\"touch_layout\", Settings.get_touch_control_layout_text())\n"
            "\tset_label(\"touch_arrange\", \"Arrange\")\n",
            str(path),
        )
        text = _replace_once(
            text,
            "\t\t\tif controls_page == 0:\n\t\t\t\tInputManager.reset_actions(InputManager.GAMEPLAY_ACTIONS)\n",
            "\t\t\tif controls_page == 2:\n\t\t\t\tSettings.reset_touch_control_defaults()\n\t\t\telif controls_page == 0:\n\t\t\t\tInputManager.reset_actions(InputManager.GAMEPLAY_ACTIONS)\n",
            str(path),
        )
        path.write_text(text, encoding="utf-8")


def _install_autoload(project_file: Path) -> None:
    text = project_file.read_text(encoding="utf-8")
    if not re.search(r"(?m)^Steamworks=", text):
        raise ValueError(
            "The recovered project has no Steamworks autoload. The builder will not invent a replacement or bypass "
            "missing DRM/platform checks; refusing to export."
        )
    autoload = 'AndroidTouchControls="*res://android/android_touch_controls.gd"'
    if autoload not in text:
        text = _replace_once(text, 'PlatformServices="*res://scenes/autoload/platform_services.gd"\n', 'PlatformServices="*res://scenes/autoload/platform_services.gd"\n' + autoload + "\n", str(project_file))
    importer = 'SaveTransferImporter="*res://android/save_transfer_importer.gd"\n'
    if importer not in text:
        text = _replace_once(text, 'Settings="*uid://d0ytpv0u2okb7"\n', importer + 'Settings="*uid://d0ytpv0u2okb7"\n', str(project_file))
    if "[input_devices]" in text:
        text = re.sub(r"(?m)^pointing/emulate_mouse_from_touch=.*$", "pointing/emulate_mouse_from_touch=false", text)
        if "pointing/emulate_mouse_from_touch=" not in text:
            text = text.replace("[input_devices]\n", "[input_devices]\npointing/emulate_mouse_from_touch=false\n", 1)
    else:
        text += "\n[input_devices]\n\npointing/emulate_mouse_from_touch=false\n"
    project_file.write_text(text, encoding="utf-8")


def _validate_android_gdextensions(project_dir: Path) -> None:
    """Fail closed when a recovered Android GDExtension mapping has no library."""
    missing: list[str] = []
    for descriptor in project_dir.rglob("*.gdextension"):
        try:
            lines = descriptor.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if not re.match(r"\s*android(?:\.[A-Za-z0-9_]+)?\s*=", line):
                continue
            for resource_path in re.findall(r'"(res://[^"\\]+)"', line):
                local_path = project_dir / resource_path.removeprefix("res://")
                if not local_path.is_file():
                    missing.append(f"{descriptor.relative_to(project_dir)} → {resource_path}")
    if missing:
        details = "\n".join(f"• {item}" for item in sorted(set(missing)))
        raise ValueError(
            "Android export was stopped because the recovered project declares Android GDExtension libraries "
            "that are missing. The builder will not remove or replace this integration. Provide the compatible "
            "Android libraries from an authorized source, restore them to the recovered project, then retry.\n\n"
            + details
        )


def _patch_android_texture_imports(project_dir: Path) -> int:
    """Use portable lossless imports for VRAM-compressed desktop textures."""
    changed = 0
    for import_file in project_dir.rglob("*.import"):
        if ".godot" in import_file.parts:
            continue
        try:
            text = import_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if 'importer="texture"' not in text:
            continue
        updated, count = re.subn(r"(?m)^compress/mode=2\s*$", "compress/mode=0", text, count=1)
        if count:
            import_file.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def _install_export_preset(project_dir: Path) -> str:
    presets = project_dir / "export_presets.cfg"
    text = presets.read_text(encoding="utf-8") if presets.exists() else ""
    found = re.search(r'(?ms)^\[preset\.(\d+)\]\s*\nname="AVS03 Android ARM64"', text)
    if found:
        preset_index = found.group(1)
        preset_section = re.compile(rf"(?ms)(^\[preset\.{preset_index}\]\s*\n.*?)(?=^\[preset\.\d+\]\s*$|\Z)")

        def include_save_archive(match: re.Match[str]) -> str:
            section = match.group(1)
            if re.search(r'(?m)^include_filter=', section):
                return re.sub(r'(?m)^include_filter=.*$', 'include_filter="android/save-transfer.zip"', section, count=1)
            return section.replace('export_filter="all_resources"', 'export_filter="all_resources"\ninclude_filter="android/save-transfer.zip"', 1)

        text, _ = preset_section.subn(include_save_archive, text, count=1)
        options = re.compile(rf"(?ms)(^\[preset\.{preset_index}\.options\]\s*\n.*?^version/code=)(\d+)")
        text, _ = options.subn(lambda match: match.group(1) + str(int(match.group(2)) + 1), text, count=1)
        presets.write_text(text, encoding="utf-8")
        return "AVS03 Android ARM64"
    index = max((int(number) for number in re.findall(r"(?m)^\[preset\.(\d+)\]", text)), default=-1) + 1
    if text and not text.endswith("\n"):
        text += "\n"
    text += ANDROID_PRESET.format(index=index)
    presets.write_text(text, encoding="utf-8")
    return "AVS03 Android ARM64"


def apply_android_ui_patch(project_dir: Path, patch_dir: Path) -> str:
    project_dir = project_dir.resolve()
    required = [project_dir / "project.godot", project_dir / "settings.gd", project_dir / "scenes" / "ui" / "settings_menu.gd"]
    if not all(path.is_file() for path in required):
        raise ValueError("Choose the recovered Godot project folder. It must contain project.godot, settings.gd, and scenes/ui/settings_menu.gd.")
    _validate_android_gdextensions(project_dir)
    (project_dir / "android").mkdir(exist_ok=True)
    for filename in ("android_touch_controls.gd", "touch_surface.gd", "save_transfer_importer.gd"):
        source = patch_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"Android touch patch file is missing: {source}")
        shutil.copy2(source, project_dir / "android" / filename)
    _patch_settings(required[1])
    _patch_settings_menu(required[2])
    _install_autoload(required[0])
    _patch_android_texture_imports(project_dir)
    return _install_export_preset(project_dir)


def export_android_apk(
    project_dir: Path,
    godot_executable: Path,
    output_apk: Path,
    patch_dir: Path,
    tool_paths: dict[str, Path | str] | None = None,
    save_archive: Path | None = None,
    build_log_path: Path | None = None,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> Path:
    if not godot_executable.is_file():
        raise ValueError("Select a valid Godot 4 executable.")
    preset_name = apply_android_ui_patch(project_dir, patch_dir)
    output_apk = output_apk.resolve()
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    if output_apk.exists():
        output_apk.unlink()
    if tool_paths:
        from tool_setup import godot_environment

        environment = godot_environment(tool_paths)
    else:
        environment = os.environ.copy()
    if sys.platform != "win32" and not tool_paths:
        profile = Path(tempfile.gettempdir()) / "avs03-godot-builder-profile"
        for name in ("data", "config", "cache"):
            (profile / name).mkdir(parents=True, exist_ok=True)
        environment["XDG_DATA_HOME"] = str(profile / "data")
        environment["XDG_CONFIG_HOME"] = str(profile / "config")
        environment["XDG_CACHE_HOME"] = str(profile / "cache")
    log_path = build_log_path or output_apk.with_suffix(".build.log")
    embedded_archive = project_dir / "android" / "save-transfer.zip"
    prior_archive = embedded_archive.read_bytes() if embedded_archive.exists() else None
    try:
        if save_archive:
            shutil.copy2(save_archive, embedded_archive)
        else:
            embedded_archive.unlink(missing_ok=True)
        commands = (
            (
                "import",
                "Importing project assets…",
                [str(godot_executable), "--headless", "--editor", "--path", str(project_dir), "--import"],
            ),
            (
                "export",
                "Exporting the Android APK…",
                [str(godot_executable), "--headless", "--path", str(project_dir), "--export-debug", preset_name, str(output_apk)],
            ),
        )
        for stage, title, command in commands:
            if progress_callback:
                progress_callback(stage, 0, title)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(("=== Godot headless Android asset import ===\n" if stage == "import" else "\n=== Godot Android export ===\n"))
                process = subprocess.Popen(
                    command,
                    cwd=project_dir,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors="replace",
                    bufsize=1,
                )
                if process.stdout is not None:
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        if progress_callback:
                            match = re.search(r"(?<![\d.])(\d{1,3})%(?!\d)", line)
                            if match:
                                progress_callback(stage, min(int(match.group(1)), 100), title)
                return_code = process.wait()
                log.write("\n")
            if return_code != 0:
                step = "asset import" if stage == "import" else "Android export"
                raise RuntimeError(f"Godot {step} failed with exit code {return_code}. Build log: {log_path}")
            if progress_callback:
                progress_callback(stage, 100, title)
    finally:
        if prior_archive is None:
            embedded_archive.unlink(missing_ok=True)
        else:
            embedded_archive.write_bytes(prior_archive)
    if return_code != 0 or not output_apk.is_file():
        raise RuntimeError(f"Godot export failed with exit code {return_code}. Build log: {log_path}")
    return output_apk
