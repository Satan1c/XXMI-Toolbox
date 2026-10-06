from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

import bpy
from bpy.types import Context, Object, bpy_struct


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
