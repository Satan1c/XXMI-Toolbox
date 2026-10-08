import os

import bpy
from bpy.types import Context, Object

from .utils import ToolError

GAME_ARMATURE_KEY = "XXMI_Toolbox:GameArmature"


def write_objects(filepath: str, name: str, objects: list[Object]) -> None:
	"""Write the objects to a .blend as one collection, for Add Saved to bring into another file."""
	collection = bpy.data.collections.new(name)
	try:
		for obj in objects:
			collection.objects.link(obj)
		# A collection to add, not a scene to open: writing a scene this way crashes Blender 5.2.
		bpy.data.libraries.write(
			filepath, {collection}, path_remap="ABSOLUTE", fake_user=True
		)
	finally:
		bpy.data.collections.remove(collection)


def _link_saved(context: Context, filepath: str) -> list[Object]:
	"""Link a saved file's collections into the scene, nested ones staying under their parents.
	Returns their objects."""
	with bpy.data.libraries.load(filepath) as (source, loaded):
		loaded.collections = source.collections
	collections = [c for c in loaded.collections if c is not None]
	if not collections:
		raise ToolError(f"{os.path.basename(filepath)} has nothing saved in it")

	nested = {child for c in collections for child in c.children_recursive}
	objects = []
	for collection in collections:
		collection.use_fake_user = False
		if collection not in nested:
			context.scene.collection.children.link(collection)
		objects += [obj for obj in collection.all_objects if obj not in objects]
	return objects


def add_saved(context: Context, filepath: str) -> list[Object]:
	"""Bring the collections of a saved model or game armature into the scene, as they were saved."""
	if not os.path.isfile(filepath):
		raise ToolError(f"{filepath} doesn't exist")
	if bpy.data.filepath and os.path.samefile(filepath, bpy.data.filepath):
		raise ToolError("That's this file")
	objects = _link_saved(context, filepath)

	armatures = [obj for obj in objects if obj.type == "ARMATURE"]
	for obj in objects:
		# A game armature's ID armatures and the empties above it stay out of sight, as Clean Up left them.
		if obj.get(GAME_ARMATURE_KEY) or (
			obj.type == "EMPTY" and any(a.parent == obj for a in armatures)
		):
			obj.hide_set(True)

	view_layer = context.view_layer
	for obj in view_layer.objects:
		obj.select_set(False)
	main = [a for a in armatures if not a.get(GAME_ARMATURE_KEY)]
	for obj in main:
		obj.select_set(True)
	if main:
		view_layer.objects.active = main[0]
	return objects
