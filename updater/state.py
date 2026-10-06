import json
import os
import threading
import time
from dataclasses import dataclass

import bpy

from ..common.addon import ADDON, IS_EXTENSION
from .releases import Release, latest_release
from .version import installed_version


@dataclass
class UpdateState:
	checking: bool = False
	checked: bool = False
	latest: Release | None = None
	error: str = ""
	last_check: float = 0.0
	ignored: str = ""
	installed: str = ""


STATE = UpdateState()
_thread: threading.Thread | None = None


def online_access() -> bool:
	# Blender 4.2+ lets users forbid add-ons from going online; earlier versions have no such setting.
	return getattr(bpy.app, "online_access", True)


def _state_file() -> str:
	if IS_EXTENSION:
		folder = bpy.utils.extension_path_user(ADDON, create=True)
	else:
		folder = bpy.utils.user_resource("CONFIG", path="xxmi_toolbox", create=True)
	return os.path.join(folder, "updater.json")


def load_state() -> None:
	try:
		with open(_state_file(), encoding="utf-8") as file:
			data = json.load(file)
	except (OSError, ValueError):
		return
	STATE.last_check = float(data.get("last_check", 0.0))
	STATE.ignored = str(data.get("ignored", ""))


def save_state() -> None:
	try:
		with open(_state_file(), "w", encoding="utf-8") as file:
			json.dump({"last_check": STATE.last_check, "ignored": STATE.ignored}, file)
	except OSError:
		pass


def update_available() -> bool:
	return STATE.latest is not None and STATE.latest.version > installed_version()


def _check() -> None:
	try:
		STATE.latest = latest_release()
		STATE.error = ""
		STATE.checked = True
	except (OSError, ValueError, KeyError) as e:
		STATE.error = f"Update check failed: {getattr(e, 'reason', e)}"
	STATE.checking = False


def _redraw() -> None:
	for window in bpy.context.window_manager.windows:
		for area in window.screen.areas:
			area.tag_redraw()


def _poll_check() -> float | None:
	if _thread is not None and _thread.is_alive():
		return 0.5
	STATE.last_check = time.time()
	save_state()
	_redraw()
	return None


def start_check() -> None:
	"""Ask GitHub for the latest release on a background thread; the UI redraws when it answers."""
	global _thread
	if STATE.checking or not online_access():
		return
	STATE.checking = True
	_thread = threading.Thread(target=_check, daemon=True)
	_thread.start()
	bpy.app.timers.register(_poll_check, first_interval=0.5)
