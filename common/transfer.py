from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

import bpy
import numpy as np
from bpy.types import Context, Object

from .utils import positions


@contextmanager
def joined_source(context: Context, sources: list[Object]) -> Iterator[Object]:
	# Data Transfer reads from a single object, so several source pieces are baked into one temporary mesh.
	if len(sources) == 1:
		yield sources[0]
		return
	depsgraph = context.evaluated_depsgraph_get()
	temps, meshes = [], []
	try:
		for obj in sources:
			mesh = bpy.data.meshes.new_from_object(
				obj.evaluated_get(depsgraph),
				preserve_all_data_layers=True,
				depsgraph=depsgraph,
			)
			mesh.transform(obj.matrix_world)
			meshes.append(mesh)
			temp = bpy.data.objects.new("XXMI_Toolbox_swap_source", mesh)
			context.scene.collection.objects.link(temp)
			temps.append(temp)
		with context.temp_override(
			object=temps[0],
			active_object=temps[0],
			selected_objects=temps,
			selected_editable_objects=temps,
		):
			bpy.ops.object.join()
		yield temps[0]
	finally:
		for temp in temps:
			try:
				bpy.data.objects.remove(temp)
			except ReferenceError:
				pass  # Already consumed by the join.
		for mesh in meshes:
			try:
				if mesh.users == 0:
					bpy.data.meshes.remove(mesh)
			except ReferenceError:
				pass


@contextmanager
def _as_shaped(target: Object) -> Iterator[None]:
	# Data Transfer samples the target at its base positions, ignoring shape keys:
	# a mesh reshaped by one must be sampled as it looks.
	mesh = target.data
	if mesh.shape_keys is None:
		yield
		return

	active = target.active_shape_key_index
	mix = target.shape_key_add(name="XXMI_Toolbox_mix", from_mix=True)
	shaped = np.empty(len(mesh.vertices) * 3)
	mix.data.foreach_get("co", shaped)
	target.shape_key_remove(mix)
	target.active_shape_key_index = active

	base = positions(mesh).ravel()
	mesh.vertices.foreach_set("co", shaped)
	mesh.update()
	try:
		yield
	finally:
		mesh.vertices.foreach_set("co", base)
		mesh.update()


def transfer(source: Object, target: Object, data_type: str, **mapping: str) -> None:
	with (
		_as_shaped(target),
		bpy.context.temp_override(
			object=source,
			active_object=source,
			selected_objects=[source, target],
			selected_editable_objects=[target],
		),
	):
		bpy.ops.object.data_transfer(
			data_type=data_type,
			use_create=True,
			layers_select_src="ALL",
			layers_select_dst="NAME",
			**mapping,
		)


def transfer_uvs(source: Object, targets: dict[Object, set[str]]) -> None:
	"""Fill each target's UV maps of the given names from the source's maps of those names,
	by the nearest source face, all targets in one go."""
	if not targets:
		return
	# Data Transfer matches UV maps by name: the targets' other maps step aside meanwhile.
	aside = [
		(layer, layer.name)
		for target, names in targets.items()
		for layer in target.data.uv_layers
		if layer.name not in names
	]
	for i, (layer, _) in enumerate(aside):
		layer.name = f"XXMI_Toolbox_aside_{i}"
	try:
		with ExitStack() as shaped:
			for target in targets:
				shaped.enter_context(_as_shaped(target))
			with bpy.context.temp_override(
				object=source,
				active_object=source,
				selected_objects=[source, *targets],
				selected_editable_objects=list(targets),
			):
				# One call for every target: the operator's search of the source is built once.
				bpy.ops.object.data_transfer(
					data_type="UV",
					use_create=False,
					layers_select_src="ALL",
					layers_select_dst="NAME",
					loop_mapping="POLYINTERP_NEAREST",
				)
	finally:
		for layer, name in aside:
			layer.name = name
