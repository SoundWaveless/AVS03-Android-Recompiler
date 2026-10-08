extends Node

const TRANSFER_RELATIVE_PATH := "save-transfer-inbox/save-transfer.zip"
const EMBEDDED_TRANSFER_PATH := "res://android/save-transfer.zip"
const IMPORT_MARKER_PATH := "user://avs03_save_transfer_imported.flag"


func _ready() -> void:
	# This autoload is installed before SaveManager so imported profiles are
	# present before the game decides whether to show the profile chooser.
	print("AVS03 local save directory: %s" % OS.get_user_data_dir())
	import_pending_transfer()


func import_pending_transfer() -> void:
	var candidates := ["user://" + TRANSFER_RELATIVE_PATH]
	# ADB transfer uses the app's files directory, one level above Godot's
	# custom user:// directory (AntivirusSurvivors on this project).
	var app_files_path := OS.get_user_data_dir().get_base_dir()
	candidates.append(app_files_path.path_join(TRANSFER_RELATIVE_PATH))
	var zip_path := ""
	for candidate: String in candidates:
		if FileAccess.file_exists(candidate):
			zip_path = candidate
			break
	var from_apk := false
	if zip_path.is_empty() and FileAccess.file_exists(EMBEDDED_TRANSFER_PATH):
		var embedded_hash := FileAccess.get_sha256(EMBEDDED_TRANSFER_PATH)
		var imported_hash := FileAccess.get_file_as_string(IMPORT_MARKER_PATH) if FileAccess.file_exists(IMPORT_MARKER_PATH) else ""
		if not embedded_hash.is_empty() and imported_hash != embedded_hash:
			zip_path = EMBEDDED_TRANSFER_PATH
			from_apk = true
	if zip_path.is_empty():
		if FileAccess.file_exists(EMBEDDED_TRANSFER_PATH):
			print("AVS03 save transfer is already imported for this APK build.")
		else:
			print("AVS03 save transfer: no archive was bundled or copied to the app.")
		return
	if _import_archive(zip_path):
		if from_apk:
			var marker := FileAccess.open(IMPORT_MARKER_PATH, FileAccess.WRITE)
			if marker != null:
				marker.store_string(FileAccess.get_sha256(EMBEDDED_TRANSFER_PATH))
				marker.close()
		else:
			DirAccess.remove_absolute(ProjectSettings.globalize_path(zip_path))


func _import_archive(zip_path: String) -> bool:
	var reader := ZIPReader.new()
	if reader.open(zip_path) != OK:
		push_warning("AVS03 save transfer could not be opened: %s" % zip_path)
		return false
	print("AVS03 save transfer found archive: %s" % zip_path)
	var imported := 0
	for entry: String in reader.get_files():
		# Only accept the files produced by the builder. Never extract arbitrary
		# archive paths into the game's writable data directory.
		if entry == "settings.cfg":
			if _write_entry(reader, entry, "user://settings.cfg"):
				imported += 1
		elif entry.begins_with("profiles/"):
			var profile_path := entry.trim_prefix("profiles/")
			var components := profile_path.split("/", false)
			# Steam desktop saves may keep files under profiles/<SteamID>/.
			# Android has no Steam account, so map that profile to profiles/.
			if components.size() == 2 and components[0].is_valid_int():
				profile_path = components[1]
			var file_name := profile_path.get_file()
			var allowed_names := ["state.json", "slot_1.json", "slot_2.json", "slot_3.json", "slot_1.json.bak", "slot_2.json.bak", "slot_3.json.bak"]
			if allowed_names.has(file_name):
				if _write_entry(reader, entry, "user://profiles/" + file_name):
					imported += 1
	reader.close()
	if imported == 0:
		push_warning("AVS03 save transfer archive contained no recognized save data.")
		return false
	print("AVS03 save transfer imported %d file(s) into %s." % [imported, OS.get_user_data_dir().path_join("profiles")])
	return true


func _write_entry(reader: ZIPReader, entry: String, destination: String) -> bool:
	var data := reader.read_file(entry)
	if data.is_empty():
		return false
	var parent := destination.get_base_dir()
	if not DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(parent)):
		if DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(parent)) != OK:
			return false
	var file := FileAccess.open(destination, FileAccess.WRITE)
	if file == null:
		return false
	file.store_buffer(data)
	file.close()
	return true
