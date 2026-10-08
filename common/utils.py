from collections.abc import Callable, Container, Iterable, Iterator, Sequence
from contextlib import contextmanager

import bpy
import numpy as np
from bpy.types import ArmatureModifier, Context, Mesh, Object, bpy_struct
from mathutils import Matrix


class ToolError(Exception):
	pass


def selected_meshes(context: Context) -> list[Object]:
	objects = list(context.selected_objects)
	active = context.active_object
	if active is not None and active not in objects:
		objects.insert(0, active)
	return [obj for obj in objects if obj.type == "MESH"]


@contextmanager
def object_mode(context: Context) -> Iterator[None]:
	# Edit-mode changes live in a BMesh that the vertex group and attribute APIs don't see.
	active = context.view_layer.objects.active
	was_edit = active is not None and active.mode == "EDIT"
	if was_edit:
		bpy.ops.object.mode_set(mode="OBJECT")
	try:
		yield
	finally:
		if was_edit and context.view_layer.objects.active is active:
			bpy.ops.object.mode_set(mode="EDIT")


def call_on(obj: Object, op: Callable[..., set[str]], **kwargs) -> set[str]:
	with bpy.context.temp_override(
		object=obj,
		active_object=obj,
		selected_objects=[obj],
		selected_editable_objects=[obj],
	):
		return op(**kwargs)


def rename_all(items: Sequence[bpy_struct], names: Sequence[str]) -> None:
	# Renaming A -> B while B still exists makes Blender pick "B.001", so park everything on unique names first.
	for i, item in enumerate(items):
		item.name = f"__xxmi_toolbox_tmp_{i}"
	for item, name in zip(items, names):
		item.name = name


def positions(mesh: Mesh) -> np.ndarray:
	"""The mesh's vertex coordinates, a row each."""
	co = np.empty(len(mesh.vertices) * 3)
	mesh.vertices.foreach_get("co", co)
	return co.reshape(-1, 3)


def transformed(co: np.ndarray, matrix: Matrix) -> np.ndarray:
	array = np.array(matrix)
	return co @ array[:3, :3].T + array[:3, 3]


def world_positions(obj: Object) -> np.ndarray:
	return transformed(positions(obj.data), obj.matrix_world)


def armature_modifier(
	obj: Object, armatures: Container[Object] | None = None
) -> ArmatureModifier | None:
	"""The object's first Armature modifier, or its first one deformed by one of the armatures."""
	return next(
		(
			mod
			for mod in obj.modifiers
			if mod.type == "ARMATURE" and (armatures is None or mod.object in armatures)
		),
		None,
	)


def follow(obj: Object, armature: Object) -> None:
	"""Deform the mesh by the armature, through its Armature modifier or a new one."""
	modifier = armature_modifier(obj) or obj.modifiers.new("Armature", "ARMATURE")
	modifier.object = armature


def deformed_by(
	objects: Iterable[Object], armatures: Container[Object]
) -> list[Object]:
	"""The meshes among the objects that one of the armatures deforms."""
	return [
		obj
		for obj in objects
		if obj.type == "MESH" and armature_modifier(obj, armatures) is not None
	]
