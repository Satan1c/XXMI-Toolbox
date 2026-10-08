from collections.abc import Iterator
from contextlib import contextmanager

import bpy
from bpy.types import Context, Mesh, Object

# Left out of the bake: the clean model deforms by its new armature,
# and subdivision would only raise the vertex count a mod has to carry.
_NOT_BAKED = {"ARMATURE", "SUBSURF", "MULTIRES"}


@contextmanager
def _without(objects: list[Object], kinds: set[str]) -> Iterator[None]:
	modifiers = [
		mod
		for obj in objects
		for mod in obj.modifiers
		if mod.type in kinds and mod.show_viewport
	]
	for mod in modifiers:
		mod.show_viewport = False
	try:
		yield
	finally:
		for mod in modifiers:
			mod.show_viewport = True


def _evaluated(context: Context, obj: Object) -> Mesh:
	"""The object's mesh with its modifiers applied, in world space."""
	depsgraph = context.evaluated_depsgraph_get()
	depsgraph.update()
	mesh = bpy.data.meshes.new_from_object(
		obj.evaluated_get(depsgraph),
		preserve_all_data_layers=True,
		depsgraph=depsgraph,
	)
	mesh.transform(obj.matrix_world)
	return mesh


def baked_meshes(context: Context, meshes: list[Object]) -> dict[Object, Mesh]:
	"""Each mesh at rest with its modifiers applied, in world space."""
	with _without(meshes, _NOT_BAKED):
		return {obj: _evaluated(context, obj) for obj in meshes}
