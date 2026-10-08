import bpy
from bpy.types import Object

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
