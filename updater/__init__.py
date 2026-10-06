import time

import bpy

from ..preferences import preferences
from . import install, operators, state

classes = (
	operators.XXMI_TOOLBOX_OT_check_for_update,
	operators.XXMI_TOOLBOX_OT_install_update,
	operators.XXMI_TOOLBOX_OT_ignore_update,
)


def _auto_check() -> None:
	try:
		prefs = preferences(bpy.context)
	except KeyError:
		return None  # Loaded without an add-on entry, as the tests do.
	interval = prefs.update_interval_days * 24 * 60 * 60
	if prefs.auto_check_update and time.time() - state.STATE.last_check >= interval:
		state.start_check()
	return None


def register() -> None:
	for cls in classes:
		bpy.utils.register_class(cls)
	install.remove_leftovers()
	state.load_state()
	if not bpy.app.background:
		bpy.app.timers.register(_auto_check, first_interval=3.0)


def unregister() -> None:
	if bpy.app.timers.is_registered(_auto_check):
		bpy.app.timers.unregister(_auto_check)
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)
