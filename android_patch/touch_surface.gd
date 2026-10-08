extends Control

const JOYSTICK_RADIUS: float = 56.0
const JOYSTICK_MARGIN: float = 82.0
const DPAD_EXTENT: float = 55.0
const DPAD_ARM_WIDTH: float = 28.0
const CLICK_RADIUS: float = 38.0
const SECONDARY_RADIUS: float = 30.0
const X_BUTTON_RADIUS: float = 27.0
const PAUSE_BUTTON_RADIUS: float = 25.0
const LT_BUTTON_RADIUS: float = 28.0
const XBOX_A_BUTTON: int = 0
const XBOX_B_BUTTON: int = 1
const XBOX_X_BUTTON: int = 2
const XBOX_START_BUTTON: int = 6
const XBOX_DPAD_UP: int = 11
const XBOX_DPAD_DOWN: int = 12
const XBOX_DPAD_LEFT: int = 13
const XBOX_DPAD_RIGHT: int = 14
const BASE_COLOR := Color(0.72, 0.9, 1.0, 0.24)
const ACTIVE_COLOR := Color(0.78, 0.94, 1.0, 0.48)
const ARROW_COLOR := Color(1.0, 1.0, 1.0, 0.72)
const XBOX_A_COLOR := Color(0.12, 0.72, 0.3, 0.5)
const XBOX_B_COLOR := Color(0.84, 0.18, 0.18, 0.5)
const XBOX_X_COLOR := Color(0.12, 0.38, 0.9, 0.5)

var joystick_touch: int = -1
var dpad_touches: Dictionary = {}
var click_touch: int = -1
var secondary_touch: int = -1
var x_touch: int = -1
var pause_touch: int = -1
var lt_touch: int = -1
var direct_pointer_touch: int = -1
var direct_pointer_position: Vector2 = Vector2.ZERO
var captured_control_touches: Dictionary = {}
var joystick_vector: Vector2 = Vector2.ZERO
var movement_vector: Vector2 = Vector2.ZERO
var click_pressed: bool = false
var secondary_pressed: bool = false
var x_pressed: bool = false
var pause_pressed: bool = false
var lt_pressed: bool = false
var dispatching_virtual_action: bool = false
var emitted_dpad_buttons: Dictionary = {}
var emitted_stick_vector: Vector2 = Vector2.ZERO
var ui_scale: float = 1.0
var viewport_scale: float = 1.0
var observed_touch_control_mode: int = Settings.TOUCH_CONTROL_JOYSTICK
var edit_mode: bool = false
var editing_touch: int = -1
var editing_secondary_touch: int = -1
var editing_control: String = ""
var editing_position: Vector2 = Vector2.ZERO
var editing_primary_position: Vector2 = Vector2.ZERO
var editing_secondary_position: Vector2 = Vector2.ZERO
var editing_scale: float = 1.0
var pinch_start_distance: float = 1.0
var pinch_start_scale: float = 1.0


func _ready() -> void:
	set_process_input(true)
	set_process(true)
	get_viewport().size_changed.connect(queue_redraw)
	observed_touch_control_mode = Settings.touch_control_mode
	Settings.settings_changed.connect(on_settings_changed)
	self_modulate = Color(1.0, 1.0, 1.0, Settings.touch_control_opacity / 100.0)


func set_edit_mode(enabled: bool) -> void:
	edit_mode = enabled
	editing_touch = -1
	editing_secondary_touch = -1
	editing_control = ""
	if enabled:
		release_all_touches()
	queue_redraw()


func _process(delta: float) -> void:
	if not movement_vector.is_zero_approx():
		# Upgrade and quick-start overlays pause the game tree, so the cursor/player
		# cannot consume virtual actions there. Move the active cursor while paused.
		if get_tree().paused:
			var cursor := GameEvents.active_cursor as Node2D
			if cursor != null and is_instance_valid(cursor):
				cursor.global_position += movement_vector * 240.0 * viewport_scale * delta
				if cursor.has_method("clamp_to_screen"):
					cursor.call("clamp_to_screen")
		queue_redraw()


func _input(event: InputEvent) -> void:
	if edit_mode:
		if event is InputEventScreenTouch:
			var edit_touch := event as InputEventScreenTouch
			if edit_touch.pressed and not edit_touch.canceled:
				begin_edit_touch(edit_touch.index, edit_touch.position)
			else:
				end_edit_touch(edit_touch.index)
			get_viewport().set_input_as_handled()
		elif event is InputEventScreenDrag:
			var edit_drag := event as InputEventScreenDrag
			if edit_drag.index == editing_touch:
				editing_primary_position = edit_drag.position
				update_edit_gesture()
				get_viewport().set_input_as_handled()
			elif edit_drag.index == editing_secondary_touch:
				editing_secondary_position = edit_drag.position
				update_edit_gesture()
				get_viewport().set_input_as_handled()
			else:
				get_viewport().set_input_as_handled()
			queue_redraw()
			get_viewport().set_input_as_handled()
		return
	if event is InputEventMouseButton:
		var mouse_button := event as InputEventMouseButton
		if not dispatching_virtual_action and mouse_button.device == InputEvent.DEVICE_ID_EMULATION and (not captured_control_touches.is_empty() or is_virtual_control_position(mouse_button.position)):
			get_viewport().set_input_as_handled()
		return
	if event is InputEventMouseMotion:
		var mouse_motion := event as InputEventMouseMotion
		if not dispatching_virtual_action and mouse_motion.device == InputEvent.DEVICE_ID_EMULATION and (not captured_control_touches.is_empty() or is_virtual_control_position(mouse_motion.position)):
			get_viewport().set_input_as_handled()
			return
	if event is InputEventScreenTouch:
		var touch := event as InputEventScreenTouch
		if touch.pressed and not touch.canceled:
			begin_touch(touch.index, touch.position)
			if not captured_control_touches.has(touch.index):
				begin_direct_touch(touch.index, touch.position)
		else:
			end_touch(touch.index)
			if touch.index == direct_pointer_touch:
				end_direct_touch(touch.index)
		get_viewport().set_input_as_handled()
	elif event is InputEventScreenDrag:
		var drag := event as InputEventScreenDrag
		if drag.index == joystick_touch:
			update_joystick(drag.position)
			get_viewport().set_input_as_handled()
		elif dpad_touches.has(drag.index):
			update_dpad_touch(drag.index, drag.position)
			get_viewport().set_input_as_handled()
		elif drag.index == click_touch:
			get_viewport().set_input_as_handled()
		elif drag.index == secondary_touch:
			get_viewport().set_input_as_handled()
		elif drag.index == x_touch or drag.index == pause_touch:
			get_viewport().set_input_as_handled()
		elif drag.index == lt_touch:
			get_viewport().set_input_as_handled()
		elif drag.index == direct_pointer_touch:
			update_direct_touch(drag.index, drag.position)
			get_viewport().set_input_as_handled()


func begin_edit_touch(index: int, position: Vector2) -> void:
	var size := get_viewport_rect().size
	update_scale(size)
	if Rect2(Vector2(size.x - 116.0 * ui_scale, 8.0 * ui_scale), Vector2(108.0 * ui_scale, 48.0 * ui_scale)).has_point(position):
		set_edit_mode(false)
		AndroidTouchControls.edit_mode = false
		return
	if editing_touch >= 0:
		if editing_secondary_touch < 0 and not editing_control.is_empty():
			# The first finger selects and holds a control; the second may land
			# anywhere. Only the distance between them changes that control's size.
			editing_secondary_touch = index
			editing_secondary_position = position
			pinch_start_distance = maxf(editing_primary_position.distance_to(editing_secondary_position), 1.0)
			pinch_start_scale = Settings.get_touch_custom_scale(editing_control)
			queue_redraw()
		return
	editing_touch = index
	editing_primary_position = position
	editing_position = position
	var nearest_distance := INF
	for control: String in ["move", "a", "b", "x", "pause", "lt"]:
		var center := control_center_for(control, size)
		var distance := position.distance_to(center)
		var radius := control_hit_radius(control) * ui_scale * individual_control_scale(control) * 1.8
		if distance <= radius and distance < nearest_distance:
			nearest_distance = distance
			editing_control = control
	if not editing_control.is_empty():
		editing_scale = Settings.get_touch_custom_scale(editing_control)
	queue_redraw()


func end_edit_touch(index: int) -> void:
	if index != editing_touch:
		if index == editing_secondary_touch:
			commit_edit_gesture()
		return
	commit_edit_gesture()


func update_edit_gesture() -> void:
	if editing_secondary_touch >= 0:
		var distance := editing_primary_position.distance_to(editing_secondary_position)
		var drag_distance := distance - pinch_start_distance
		editing_scale = clampf(pinch_start_scale * (1.0 + drag_distance / maxf(pinch_start_distance, 48.0)), 0.4, 2.0)
	else:
		editing_position = editing_primary_position


func commit_edit_gesture() -> void:
	if not editing_control.is_empty():
		var size := get_viewport_rect().size
		Settings.set_touch_custom_position(editing_control, Vector2(editing_position.x / size.x, editing_position.y / size.y))
		Settings.set_touch_custom_scale(editing_control, editing_scale)
	editing_touch = -1
	editing_secondary_touch = -1
	editing_control = ""
	queue_redraw()


func control_hit_radius(control: String) -> float:
	match control:
		"move":
			return DPAD_EXTENT if Settings.touch_control_mode == Settings.TOUCH_CONTROL_DPAD else JOYSTICK_RADIUS
		"a": return CLICK_RADIUS
		"b": return SECONDARY_RADIUS
		"x": return X_BUTTON_RADIUS
		"pause": return PAUSE_BUTTON_RADIUS
		"lt": return LT_BUTTON_RADIUS
	return 24.0


func individual_control_scale(control: String) -> float:
	if Settings.touch_control_layout != Settings.TOUCH_LAYOUT_CUSTOM:
		return 1.0
	return Settings.get_touch_custom_scale(control)


func begin_touch(index: int, position: Vector2) -> void:
	var size := get_viewport_rect().size
	var mode: int = Settings.touch_control_mode
	var control_center := control_center_for("move", size)
	var button_center := control_center_for("a", size)
	var f_button_center := control_center_for("b", size)
	var x_button_center := control_center_for("x", size)
	var pause_button_center := control_center_for("pause", size)
	var lt_button_center := control_center_for("lt", size)
	if lt_touch < 0 and position.distance_to(lt_button_center) <= LT_BUTTON_RADIUS * ui_scale * individual_control_scale("lt") * 1.6:
		lt_touch = index
		captured_control_touches[index] = true
		set_lt_action(true)
		get_viewport().set_input_as_handled()
	elif pause_touch < 0 and position.distance_to(pause_button_center) <= PAUSE_BUTTON_RADIUS * ui_scale * individual_control_scale("pause") * 1.6:
		pause_touch = index
		captured_control_touches[index] = true
		set_pause_action(true)
		get_viewport().set_input_as_handled()
	elif x_touch < 0 and position.distance_to(x_button_center) <= X_BUTTON_RADIUS * ui_scale * individual_control_scale("x") * 1.6:
		x_touch = index
		captured_control_touches[index] = true
		set_x_action(true)
		get_viewport().set_input_as_handled()
	elif secondary_touch < 0 and position.distance_to(f_button_center) <= SECONDARY_RADIUS * ui_scale * individual_control_scale("b") * 1.6:
		secondary_touch = index
		captured_control_touches[index] = true
		set_secondary_action(true)
		get_viewport().set_input_as_handled()
	elif click_touch < 0 and position.distance_to(button_center) <= CLICK_RADIUS * ui_scale * individual_control_scale("a") * 1.7:
		click_touch = index
		captured_control_touches[index] = true
		set_click(true)
		get_viewport().set_input_as_handled()
	elif mode == Settings.TOUCH_CONTROL_DPAD and dpad_touches.size() < 4 and position.distance_to(control_center) <= DPAD_EXTENT * ui_scale * individual_control_scale("move") * 1.45:
		update_dpad_touch(index, position)
		captured_control_touches[index] = true
		get_viewport().set_input_as_handled()
	elif mode == Settings.TOUCH_CONTROL_JOYSTICK and joystick_touch < 0 and position.distance_to(control_center) <= JOYSTICK_RADIUS * ui_scale * individual_control_scale("move") * 1.8:
		joystick_touch = index
		captured_control_touches[index] = true
		update_joystick(position)
		get_viewport().set_input_as_handled()
	queue_redraw()


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		release_all_touches()


func release_all_touches() -> void:
	if direct_pointer_touch >= 0:
		end_direct_touch(direct_pointer_touch)
	joystick_touch = -1
	dpad_touches.clear()
	click_touch = -1
	secondary_touch = -1
	x_touch = -1
	pause_touch = -1
	lt_touch = -1
	captured_control_touches.clear()
	joystick_vector = Vector2.ZERO
	movement_vector = Vector2.ZERO
	sync_virtual_movement_actions()
	set_click(false)
	set_secondary_action(false)
	set_x_action(false)
	set_pause_action(false)
	set_lt_action(false)
	release_virtual_dpad()
	send_virtual_stick(Vector2.ZERO, true)
	queue_redraw()


func end_touch(index: int) -> void:
	if index == joystick_touch:
		joystick_touch = -1
		captured_control_touches.erase(index)
		joystick_vector = Vector2.ZERO
		movement_vector = Vector2.ZERO
		sync_virtual_movement_actions()
		get_viewport().set_input_as_handled()
	if dpad_touches.has(index):
		dpad_touches.erase(index)
		captured_control_touches.erase(index)
		rebuild_movement_vector()
		get_viewport().set_input_as_handled()
	if index == click_touch:
		click_touch = -1
		set_click(false)
		captured_control_touches.erase(index)
		get_viewport().set_input_as_handled()
	if index == secondary_touch:
		secondary_touch = -1
		set_secondary_action(false)
		captured_control_touches.erase(index)
		get_viewport().set_input_as_handled()
	if index == x_touch:
		x_touch = -1
		set_x_action(false)
		captured_control_touches.erase(index)
		get_viewport().set_input_as_handled()
	if index == pause_touch:
		pause_touch = -1
		set_pause_action(false)
		captured_control_touches.erase(index)
		get_viewport().set_input_as_handled()
	if index == lt_touch:
		lt_touch = -1
		set_lt_action(false)
		captured_control_touches.erase(index)
		get_viewport().set_input_as_handled()
	queue_redraw()


func begin_direct_touch(index: int, position: Vector2) -> void:
	if direct_pointer_touch >= 0:
		return
	direct_pointer_touch = index
	direct_pointer_position = position
	send_direct_pointer_motion(position, Vector2(1.0, 1.0))
	send_direct_pointer_button(true, position)


func update_direct_touch(index: int, position: Vector2) -> void:
	if index != direct_pointer_touch:
		return
	var relative := position - direct_pointer_position
	direct_pointer_position = position
	if not relative.is_zero_approx():
		send_direct_pointer_motion(position, relative)


func end_direct_touch(index: int) -> void:
	if index != direct_pointer_touch:
		return
	send_direct_pointer_button(false, direct_pointer_position)
	direct_pointer_touch = -1


func send_direct_pointer_motion(position: Vector2, relative: Vector2) -> void:
	var cursor := GameEvents.active_cursor as Cursor
	if cursor != null and is_instance_valid(cursor) and cursor.mouse_mode:
		var canvas_transform := cursor.get_canvas_transform()
		cursor.global_position = canvas_transform.affine_inverse() * position + Cursor.MOUSE_CURSOR_OFFSET
		cursor.clamp_to_screen()
	var event := InputEventMouseMotion.new()
	event.device = InputEvent.DEVICE_ID_EMULATION
	event.position = position
	event.global_position = position
	event.relative = relative
	dispatching_virtual_action = true
	Input.parse_input_event(event)
	dispatching_virtual_action = false


func send_direct_pointer_button(pressed: bool, position: Vector2) -> void:
	var event := InputEventMouseButton.new()
	event.device = InputEvent.DEVICE_ID_EMULATION
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = pressed
	event.position = position
	event.global_position = position
	dispatching_virtual_action = true
	Input.parse_input_event(event)
	dispatching_virtual_action = false


func update_joystick(position: Vector2) -> void:
	var offset := position - control_center_for("move", get_viewport_rect().size)
	var max_distance := JOYSTICK_RADIUS * ui_scale * individual_control_scale("move")
	joystick_vector = offset.limit_length(max_distance) / max_distance
	apply_joystick_deadzone()
	get_viewport().set_input_as_handled()
	queue_redraw()


func apply_joystick_deadzone() -> void:
	var magnitude := joystick_vector.length()
	var deadzone := Settings.touch_control_deadzone / 100.0
	if magnitude <= deadzone:
		movement_vector = Vector2.ZERO
		sync_virtual_movement_actions()
		return
	var adjusted_magnitude := (magnitude - deadzone) / (1.0 - deadzone)
	movement_vector = joystick_vector.normalized() * adjusted_magnitude
	sync_virtual_movement_actions()


func update_dpad_touch(index: int, position: Vector2) -> void:
	var offset := position - control_center_for("move", get_viewport_rect().size)
	var direction := Vector2.ZERO
	if offset.length() >= 8.0 * ui_scale:
		if absf(offset.x) > absf(offset.y):
			direction = Vector2.RIGHT if offset.x > 0.0 else Vector2.LEFT
		else:
			direction = Vector2.DOWN if offset.y > 0.0 else Vector2.UP
	dpad_touches[index] = direction
	rebuild_movement_vector()
	get_viewport().set_input_as_handled()
	queue_redraw()


func rebuild_movement_vector() -> void:
	var combined := Vector2.ZERO
	for direction: Vector2 in dpad_touches.values():
		combined += direction
	movement_vector = combined.normalized() if combined.length() > 1.0 else combined
	sync_virtual_movement_actions()


func sync_virtual_movement_actions() -> void:
	if Settings.touch_control_mode == Settings.TOUCH_CONTROL_DPAD:
		send_virtual_stick(Vector2.ZERO)
		var desired := {
			XBOX_DPAD_UP: movement_vector.y < -0.1,
			XBOX_DPAD_DOWN: movement_vector.y > 0.1,
			XBOX_DPAD_LEFT: movement_vector.x < -0.1,
			XBOX_DPAD_RIGHT: movement_vector.x > 0.1,
		}
		for button: int in desired:
			var pressed: bool = desired[button]
			if bool(emitted_dpad_buttons.get(button, false)) != pressed:
				send_virtual_button(button, pressed)
				emitted_dpad_buttons[button] = pressed
	else:
		release_virtual_dpad()
		send_virtual_stick(movement_vector)


func send_virtual_button(button: int, pressed: bool) -> void:
	var event := InputEventJoypadButton.new()
	event.device = -1
	event.button_index = button
	event.pressed = pressed
	event.pressure = 1.0 if pressed else 0.0
	Input.parse_input_event(event)


func release_virtual_dpad() -> void:
	for button: int in [XBOX_DPAD_UP, XBOX_DPAD_DOWN, XBOX_DPAD_LEFT, XBOX_DPAD_RIGHT]:
		if bool(emitted_dpad_buttons.get(button, false)):
			send_virtual_button(button, false)
		emitted_dpad_buttons[button] = false


func send_virtual_stick(value: Vector2, force: bool = false) -> void:
	if not force and emitted_stick_vector.is_equal_approx(value):
		return
	emitted_stick_vector = value
	for axis_index: int in [JOY_AXIS_LEFT_X, JOY_AXIS_LEFT_Y]:
		var event := InputEventJoypadMotion.new()
		event.device = -1
		event.axis = axis_index
		event.axis_value = value.x if axis_index == JOY_AXIS_LEFT_X else value.y
		Input.parse_input_event(event)


func is_virtual_control_position(position: Vector2) -> bool:
	var size := get_viewport_rect().size
	var center := control_center_for("move", size)
	var button := control_center_for("a", size)
	var f_button := control_center_for("b", size)
	var x_button := control_center_for("x", size)
	var pause_button := control_center_for("pause", size)
	var lt_button := control_center_for("lt", size)
	if position.distance_to(lt_button) <= LT_BUTTON_RADIUS * ui_scale * individual_control_scale("lt") * 1.6:
		return true
	if position.distance_to(pause_button) <= PAUSE_BUTTON_RADIUS * ui_scale * individual_control_scale("pause") * 1.6:
		return true
	if position.distance_to(x_button) <= X_BUTTON_RADIUS * ui_scale * individual_control_scale("x") * 1.6:
		return true
	if position.distance_to(f_button) <= SECONDARY_RADIUS * ui_scale * individual_control_scale("b") * 1.7:
		return true
	if position.distance_to(button) <= CLICK_RADIUS * ui_scale * individual_control_scale("a") * 1.7:
		return true
	if Settings.touch_control_mode == Settings.TOUCH_CONTROL_DPAD:
		return position.distance_to(center) <= DPAD_EXTENT * ui_scale * individual_control_scale("move") * 1.45
	return position.distance_to(center) <= JOYSTICK_RADIUS * ui_scale * individual_control_scale("move") * 1.8


func set_secondary_action(pressed: bool) -> void:
	if secondary_pressed == pressed:
		return
	secondary_pressed = pressed
	send_virtual_button(XBOX_B_BUTTON, pressed)


func set_x_action(pressed: bool) -> void:
	if x_pressed == pressed:
		return
	x_pressed = pressed
	send_virtual_button(XBOX_X_BUTTON, pressed)


func set_pause_action(pressed: bool) -> void:
	if pause_pressed == pressed:
		return
	pause_pressed = pressed
	send_virtual_button(XBOX_START_BUTTON, pressed)


func set_lt_action(pressed: bool) -> void:
	if lt_pressed == pressed:
		return
	lt_pressed = pressed
	var event := InputEventJoypadMotion.new()
	event.device = -1
	event.axis = JOY_AXIS_TRIGGER_LEFT
	event.axis_value = 1.0 if pressed else 0.0
	Input.parse_input_event(event)


func on_settings_changed() -> void:
	if observed_touch_control_mode != Settings.touch_control_mode:
		observed_touch_control_mode = Settings.touch_control_mode
		joystick_touch = -1
		captured_control_touches.clear()
		dpad_touches.clear()
		joystick_vector = Vector2.ZERO
		movement_vector = Vector2.ZERO
		sync_virtual_movement_actions()
		if click_touch >= 0:
			click_touch = -1
			set_click(false)
		if secondary_touch >= 0:
			secondary_touch = -1
			set_secondary_action(false)
		if x_touch >= 0:
			x_touch = -1
			set_x_action(false)
		if pause_touch >= 0:
			pause_touch = -1
			set_pause_action(false)
		if lt_touch >= 0:
			lt_touch = -1
			set_lt_action(false)
	if Settings.touch_control_mode == Settings.TOUCH_CONTROL_JOYSTICK:
		apply_joystick_deadzone()
	else:
		rebuild_movement_vector()
	self_modulate = Color(1.0, 1.0, 1.0, Settings.touch_control_opacity / 100.0)
	queue_redraw()


func set_click(pressed: bool) -> void:
	if click_pressed == pressed:
		return
	click_pressed = pressed
	send_virtual_button(XBOX_A_BUTTON, pressed)


func joystick_center(viewport_size: Vector2) -> Vector2:
	update_scale(viewport_size)
	var offset := Vector2(Settings.touch_control_offset_x, Settings.touch_control_offset_y) * ui_scale
	return Vector2(JOYSTICK_MARGIN * ui_scale, viewport_size.y - JOYSTICK_MARGIN * ui_scale) + offset


func control_center_for(control: String, viewport_size: Vector2) -> Vector2:
	update_scale(viewport_size)
	if Settings.touch_control_layout == Settings.TOUCH_LAYOUT_CUSTOM:
		return Settings.get_touch_custom_position(control) * viewport_size
	match control:
		"move": return joystick_center(viewport_size)
		"a": return click_center(viewport_size)
		"b": return secondary_center(viewport_size)
		"x": return x_center(viewport_size)
		"pause": return pause_center(viewport_size)
		"lt": return lt_center()
	return viewport_size * 0.5


func click_center(viewport_size: Vector2) -> Vector2:
	update_scale(viewport_size)
	var offset := Vector2(-Settings.touch_control_offset_x, Settings.touch_control_offset_y) * ui_scale
	return Vector2(viewport_size.x - JOYSTICK_MARGIN * ui_scale, viewport_size.y - JOYSTICK_MARGIN * ui_scale) + offset


func secondary_center(viewport_size: Vector2) -> Vector2:
	# Xbox face-button positions: A below B.
	return click_center(viewport_size) + Vector2(52.0, -48.0) * ui_scale


func x_center(viewport_size: Vector2) -> Vector2:
	# Xbox X occupies the left position in the face-button diamond.
	return click_center(viewport_size) + Vector2(-52.0, -48.0) * ui_scale


func pause_center(viewport_size: Vector2) -> Vector2:
	var y := 30.0 * ui_scale if Settings.touch_pause_button_top else viewport_size.y - 30.0 * ui_scale
	return Vector2(viewport_size.x * 0.5, y)


func lt_center() -> Vector2:
	return Vector2(32.0, 32.0) * ui_scale


func update_scale(viewport_size: Vector2) -> void:
	viewport_scale = clampf(minf(viewport_size.x / 640.0, viewport_size.y / 360.0), 0.8, 1.5)
	ui_scale = viewport_scale * Settings.touch_control_scale / 100.0


func draw_arrow(center: Vector2, direction: Vector2, active: bool) -> void:
	var arrow_size := 8.0 * ui_scale
	var shaft_size := 5.0 * ui_scale
	var tip := center + direction * arrow_size
	var base := center - direction * (arrow_size * 0.55)
	var perpendicular := Vector2(-direction.y, direction.x)
	var points := PackedVector2Array([
		tip,
		base + perpendicular * arrow_size * 0.72,
		base + perpendicular * shaft_size,
		base - perpendicular * shaft_size,
		base - perpendicular * arrow_size * 0.72,
	])
	draw_colored_polygon(points, ACTIVE_COLOR if active else ARROW_COLOR)


func _draw() -> void:
	var size := get_viewport_rect().size
	update_scale(size)
	if edit_mode:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.0, 0.0, 0.0, 0.28), true)
		draw_string(ThemeDB.fallback_font, Vector2(16.0, 30.0 * ui_scale), "Drag controls to move them", HORIZONTAL_ALIGNMENT_LEFT, -1, int(16.0 * ui_scale), Color.WHITE)
		var done_rect := Rect2(Vector2(size.x - 116.0 * ui_scale, 8.0 * ui_scale), Vector2(108.0 * ui_scale, 48.0 * ui_scale))
		draw_rect(done_rect, Color(0.12, 0.38, 0.9, 0.8), true)
		draw_string(ThemeDB.fallback_font, done_rect.position + Vector2(23.0 * ui_scale, 31.0 * ui_scale), "Done", HORIZONTAL_ALIGNMENT_LEFT, -1, int(18.0 * ui_scale), Color.WHITE)
	var control_center := displayed_control_center("move", size)
	var button_center := displayed_control_center("a", size)
	var f_button_center := displayed_control_center("b", size)
	var x_button_center := displayed_control_center("x", size)
	var pause_button_center := displayed_control_center("pause", size)
	var lt_button_center := displayed_control_center("lt", size)
	var dpad_mode: bool = Settings.touch_control_mode == Settings.TOUCH_CONTROL_DPAD
	var base_ui_scale := ui_scale
	ui_scale = base_ui_scale * displayed_control_scale("move")
	if dpad_mode:
		draw_dpad(control_center)
	else:
		var radius := JOYSTICK_RADIUS * ui_scale
		draw_circle(control_center, radius, BASE_COLOR)
		draw_arc(control_center, radius, 0.0, TAU, 48, Color(0.85, 0.94, 1.0, 0.4), 2.0 * ui_scale, true)
		var knob := control_center + joystick_vector * radius
		draw_circle(knob, radius * 0.38, ACTIVE_COLOR if joystick_touch >= 0 else BASE_COLOR)
	ui_scale = base_ui_scale * displayed_control_scale("a")
	draw_circle(button_center, CLICK_RADIUS * ui_scale, ACTIVE_COLOR if click_pressed else XBOX_A_COLOR)
	draw_arc(button_center, CLICK_RADIUS * ui_scale, 0.0, TAU, 40, Color(0.85, 0.94, 1.0, 0.4), 2.0 * ui_scale, true)
	draw_string(ThemeDB.fallback_font, button_center + Vector2(-5.0 * ui_scale, 5.0 * ui_scale), "A", HORIZONTAL_ALIGNMENT_LEFT, -1, int(16.0 * ui_scale), Color(1.0, 1.0, 1.0, 0.72))
	ui_scale = base_ui_scale * displayed_control_scale("b")
	draw_circle(f_button_center, SECONDARY_RADIUS * ui_scale, ACTIVE_COLOR if secondary_pressed else XBOX_B_COLOR)
	draw_arc(f_button_center, SECONDARY_RADIUS * ui_scale, 0.0, TAU, 36, Color(0.85, 0.94, 1.0, 0.4), 2.0 * ui_scale, true)
	draw_string(ThemeDB.fallback_font, f_button_center + Vector2(-5.0 * ui_scale, 5.0 * ui_scale), "B", HORIZONTAL_ALIGNMENT_LEFT, -1, int(14.0 * ui_scale), Color(1.0, 1.0, 1.0, 0.72))
	ui_scale = base_ui_scale * displayed_control_scale("x")
	draw_circle(x_button_center, X_BUTTON_RADIUS * ui_scale, ACTIVE_COLOR if x_pressed else XBOX_X_COLOR)
	draw_arc(x_button_center, X_BUTTON_RADIUS * ui_scale, 0.0, TAU, 36, Color(0.85, 0.94, 1.0, 0.4), 2.0 * ui_scale, true)
	draw_string(ThemeDB.fallback_font, x_button_center + Vector2(-5.0 * ui_scale, 5.0 * ui_scale), "X", HORIZONTAL_ALIGNMENT_LEFT, -1, int(14.0 * ui_scale), Color(1.0, 1.0, 1.0, 0.72))
	ui_scale = base_ui_scale * displayed_control_scale("pause")
	draw_circle(pause_button_center, PAUSE_BUTTON_RADIUS * ui_scale, ACTIVE_COLOR if pause_pressed else BASE_COLOR)
	draw_arc(pause_button_center, PAUSE_BUTTON_RADIUS * ui_scale, 0.0, TAU, 36, Color(0.85, 0.94, 1.0, 0.4), 2.0 * ui_scale, true)
	draw_string(ThemeDB.fallback_font, pause_button_center + Vector2(-5.0 * ui_scale, 5.0 * ui_scale), "II", HORIZONTAL_ALIGNMENT_LEFT, -1, int(13.0 * ui_scale), Color(1.0, 1.0, 1.0, 0.72))
	ui_scale = base_ui_scale * displayed_control_scale("lt")
	draw_circle(lt_button_center, LT_BUTTON_RADIUS * ui_scale, ACTIVE_COLOR if lt_pressed else BASE_COLOR)
	draw_arc(lt_button_center, LT_BUTTON_RADIUS * ui_scale, 0.0, TAU, 36, Color(0.85, 0.94, 1.0, 0.4), 2.0 * ui_scale, true)
	draw_string(ThemeDB.fallback_font, lt_button_center + Vector2(-8.0 * ui_scale, 5.0 * ui_scale), "LT", HORIZONTAL_ALIGNMENT_LEFT, -1, int(12.0 * ui_scale), Color(1.0, 1.0, 1.0, 0.72))
	ui_scale = base_ui_scale


func draw_dpad(center: Vector2) -> void:
	var arm := DPAD_EXTENT * ui_scale
	var width := DPAD_ARM_WIDTH * ui_scale
	var vertical := Rect2(center + Vector2(-width * 0.5, -arm), Vector2(width, arm * 2.0))
	var horizontal := Rect2(center + Vector2(-arm, -width * 0.5), Vector2(arm * 2.0, width))
	draw_rect(vertical, BASE_COLOR, true)
	draw_rect(horizontal, BASE_COLOR, true)
	draw_rect(vertical, Color(0.85, 0.94, 1.0, 0.4), false, 2.0 * ui_scale)
	draw_rect(horizontal, Color(0.85, 0.94, 1.0, 0.4), false, 2.0 * ui_scale)
	var directions: Array[Vector2] = [Vector2.UP, Vector2.DOWN, Vector2.LEFT, Vector2.RIGHT]
	for direction: Vector2 in directions:
		var active := movement_direction_active(direction)
		var arrow_center := center + direction * arm * 0.66
		draw_arrow(arrow_center, direction, active)


func movement_direction_active(direction: Vector2) -> bool:
	for touch_direction: Vector2 in dpad_touches.values():
		if touch_direction == direction:
			return true
	return false


func displayed_control_center(control: String, size: Vector2) -> Vector2:
	if edit_mode and editing_control == control and editing_touch >= 0:
		return editing_position
	return control_center_for(control, size)


func displayed_control_scale(control: String) -> float:
	if edit_mode and editing_control == control and editing_touch >= 0:
		return editing_scale
	return individual_control_scale(control)


func _exit_tree() -> void:
	release_all_touches()
