extends Node

const TOUCH_SURFACE_SCRIPT: Script = preload("res://android/touch_surface.gd")

var touch_surface: Control
var edit_mode: bool = false


func _ready() -> void:
	if not OS.has_feature("android") and not DisplayServer.is_touchscreen_available():
		return
	# Route ordinary taps through the touch surface so controller touches never
	# move the game's mouse cursor as a side effect.
	Input.emulate_mouse_from_touch = false
	var layer := CanvasLayer.new()
	layer.name = "AndroidTouchControlsLayer"
	# Keep touch input alive during paused quick-start and upgrade screens.
	layer.process_mode = Node.PROCESS_MODE_ALWAYS
	# The game draws its CRT and monitor chrome at layers 127 and 128.
	layer.layer = 129
	get_tree().root.add_child.call_deferred(layer)
	touch_surface = Control.new()
	touch_surface.name = "TouchSurface"
	touch_surface.process_mode = Node.PROCESS_MODE_ALWAYS
	touch_surface.set_script(TOUCH_SURFACE_SCRIPT)
	touch_surface.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	touch_surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(touch_surface)


func toggle_edit_mode() -> void:
	edit_mode = not edit_mode
	if is_instance_valid(touch_surface):
		touch_surface.set_edit_mode(edit_mode)
