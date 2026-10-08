import os
from collections.abc import Iterator
from contextlib import contextmanager

import bpy
from bpy.types import ID, Collection, Context, Object

from .utils import ToolError

GAME_ARMATURE_KEY = "XXMI_Toolbox:GameArmature"


def _collections(
	name: str, objects: list[Object], nested: dict[str, list[Object]]
) -> list[tuple[Collection, str]]:
	"""A new collection holding the objects, with nested ones of more; each comes with the name it should have."""
	collection = bpy.data.collections.new(name)
	created = [(collection, name)]
	for child_name, children in nested.items():
		child = bpy.data.collections.new(child_name)
		collection.children.link(child)
		created.append((child, child_name))
		for obj in children:
			child.objects.link(obj)
	for obj in objects:
		collection.objects.link(obj)
	return created


@contextmanager
def _named_as_originals(pairs: list[tuple[ID, ID]]) -> Iterator[None]:
	"""Each (copy, original): the copy takes the original's name meanwhile, the original parked aside."""
	names = [original.name for _, original in pairs]
	try:
		for i, (_, original) in enumerate(pairs):
			original.name = f"XXMI_Toolbox_original_{i}"
		for (copy, _), original_name in zip(pairs, names):
			copy.name = original_name
		yield
	finally:
		for i, (copy, _) in enumerate(pairs):
			copy.name = f"XXMI_Toolbox_copy_{i}"
		for (_, original), original_name in zip(pairs, names):
			original.name = original_name


def write_objects(
	filepath: str,
	name: str,
	objects: list[Object],
	standing_in: dict[ID, ID] | None = None,
	nested: dict[str, list[Object]] | None = None,
) -> None:
	"""Write the objects to a .blend as one collection, with nested collections of more,
	for Add Saved to bring into another file.
	Copies standing in for originals of this file are written under the originals' names rather than as .001s,
	and so are the collections."""
	created = _collections(name, objects, nested or {})
	pairs = list((standing_in or {}).items())
	pairs += [
		(new, bpy.data.collections[wanted])
		for new, wanted in created
		if new.name != wanted
	]
	try:
		with _named_as_originals(pairs):
			# A collection to add, not a scene to open: writing a scene this way crashes Blender 5.2.
			bpy.data.libraries.write(
				filepath, {created[0][0]}, path_remap="ABSOLUTE", fake_user=True
			)
	finally:
		for new, _ in reversed(created):
			bpy.data.collections.remove(new)


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
