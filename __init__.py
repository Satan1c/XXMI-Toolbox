import os

import bpy

from . import (
	armature,
	mesh,
	model_swap,
	panels,
	preferences,
	settings,
	updater,
	vertex_groups,
)

# Read only by Blender 3.6 for the legacy add-on build; 4.2+ uses blender_manifest.toml.
bl_info = {
	"name": "XXMI Toolbox (Blender 3.6)",
	"author": "Satan1c, SpectrumQT, LeoTorreZ, Gustav0, SilentNightSound",
	"version": (0, 1, 0),
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
	preferences,
	updater,
	settings,
	panels,
)
# Only present in local development copies.
if os.path.isdir(os.path.join(os.path.dirname(__file__), "experimental")):
	from . import experimental

	_modules += (experimental,)
_registered = False


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


def unregister():
	global _registered
	if not _registered:
		return
	for module in reversed(_modules):
		module.unregister()
	_registered = False
