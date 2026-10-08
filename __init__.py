import os
import traceback

import bpy

from . import (
	armature,
	mesh,
	model_swap,
	panels,
	preferences,
	settings,
	textures,
	updater,
	vertex_groups,
)

# Read only by Blender 3.6 for the legacy add-on build; 4.2+ uses blender_manifest.toml.
bl_info = {
	"name": "XXMI Toolbox (Blender 3.6)",
	"author": "Satan1c, SpectrumQT, LeoTorreZ, Gustav0, SilentNightSound",
	"version": (1, 0, 0),
	"blender": (3, 6, 0),
	"location": "View3D > Sidebar > XXMI / WWMI / EFMI Tools tabs",
	"description": "Shared mesh and vertex group tools for XXMI modding add-ons",
	"category": "Mesh",
}

# Feature settings and operators before the scene settings that point at them and the panels that draw them.
_modules = (
	vertex_groups,
	mesh,
	model_swap,
	armature,
	textures,
	preferences,
	updater,
	settings,
	panels,
)
# Experimental tools are handed out separately and dropped into the add-on folder; updates keep them. One made for
# another version must not take the rest of the add-on down with it.
_experimental = None
if os.path.isdir(os.path.join(os.path.dirname(__file__), "experimental")):
	try:
		from . import experimental as _experimental
	except Exception:
		print("XXMI Toolbox: experimental tools failed to load")
		traceback.print_exc()
_registered = False
_experimental_registered = False


def register():
	global _registered
	# The legacy copy must stay inert on versions that load the extension instead.
	if not __package__.startswith("bl_ext.") and bpy.app.version >= (4, 2, 0):
		print(
			"XXMI Toolbox: legacy add-on ignored on Blender 4.2+, install the extension instead"
		)
		return
	for module in _modules:
		module.register()
	_registered = True
	_register_experimental()


def _register_experimental():
	global _experimental_registered
	if _experimental is None:
		return
	try:
		_experimental.register()
		_experimental_registered = True
	except Exception:
		print("XXMI Toolbox: experimental tools failed to register")
		traceback.print_exc()


def unregister():
	global _registered, _experimental_registered
	if not _registered:
		return
	if _experimental_registered:
		_experimental.unregister()
		_experimental_registered = False
	for module in reversed(_modules):
		module.unregister()
	_registered = False
