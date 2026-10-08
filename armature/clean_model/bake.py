from collections.abc import Iterator
from contextlib import contextmanager

import bpy
from bpy.types import Context, Mesh, Object

from .keys import Shape, bake_keyed

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


def baked_meshes(
	context: Context, meshes: list[Object]
) -> tuple[dict[Object, tuple[Mesh, list[Shape]]], list[str]]:
	"""Each mesh at rest with its modifiers applied, in world space, and each shape key baked the same way.
	Keys a modifier changes the vertex count of can't be kept: their names come back too."""
	baked, skipped = {}, []
	with _without(meshes, _NOT_BAKED):
		for obj in meshes:
			mesh, shapes, missed = bake_keyed(
				context, obj, lambda obj=obj: _evaluated(context, obj)
			)
			baked[obj] = (mesh, shapes)
			skipped += missed
	return baked, skipped
