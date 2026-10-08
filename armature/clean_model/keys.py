from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np
from bpy.types import Context, Key, Mesh, Object

from ...common.utils import positions, transformed
from ...vertex_groups.weights import read_weights

# Which original vertex each evaluated one came from, carried through the modifiers for one evaluation.
_INDEX = "XXMI_Toolbox_index"


@dataclass
class Shape:
	name: str
	co: np.ndarray
	value: float
	slider_min: float
	slider_max: float
	mute: bool


@contextmanager
def _keys_at_rest(obj: Object) -> Iterator[Key | None]:
	"""Every shape key at 0 and free to be set: drivers off, nothing shown alone."""
	keys = obj.data.shape_keys
	if keys is None:
		yield None
		return
	blocks = [(b, b.value, b.mute, b.slider_min, b.slider_max) for b in keys.key_blocks]
	drivers = (
		[d for d in keys.animation_data.drivers if not d.mute]
		if keys.animation_data
		else []
	)
	alone = obj.show_only_shape_key

	for driver in drivers:
		driver.mute = True
	obj.show_only_shape_key = False
	for block, *_ in blocks:
		block.mute = False
		block.slider_min = min(block.slider_min, 0.0)
		block.slider_max = max(block.slider_max, 1.0)
		block.value = 0.0
	try:
		yield keys
	finally:
		for block, value, mute, low, high in blocks:
			block.slider_min, block.slider_max = low, high
			block.value, block.mute = value, mute
		for driver in drivers:
			driver.mute = False
		obj.show_only_shape_key = alone


@contextmanager
def _carrying_index(obj: Object) -> Iterator[None]:
	mesh = obj.data
	origin = mesh.attributes.new(_INDEX, "INT", "POINT")
	origin.data.foreach_set("value", np.arange(len(mesh.vertices), dtype=np.int32))
	try:
		yield
	finally:
		mesh.attributes.remove(mesh.attributes[_INDEX])


def _carried_index(obj: Object, mesh: Mesh) -> np.ndarray | None:
	"""Which original vertex each baked one came from, or None if a modifier didn't carry it through."""
	origin = mesh.attributes.get(_INDEX)
	if origin is None or origin.domain != "POINT":
		return None
	index = np.empty(len(mesh.vertices), dtype=np.int32)
	origin.data.foreach_get("value", index)
	if len(index) and (index.min() < 0 or index.max() >= len(obj.data.vertices)):
		return None
	return index


def _offsets(obj: Object, keys: Key) -> Iterator[tuple[str, np.ndarray]]:
	"""Each key's offsets from the key it's relative to, scaled by its vertex group's weights if it has one."""
	count = len(obj.data.vertices)
	if any(block.vertex_group for block in keys.key_blocks):
		verts, groups, weights = read_weights(obj.data)
		names = {vg.name: vg.index for vg in obj.vertex_groups}

	# Coordinates are stored as 32-bit floats: matching buffers copy straight through.
	co = np.empty(count * 3, dtype=np.float32)
	relatives = {}
	for block in list(keys.key_blocks)[1:]:
		block.data.foreach_get("co", co)
		relative = relatives.get(block.relative_key.name)
		if relative is None:
			relative = np.empty(count * 3, dtype=np.float32)
			block.relative_key.data.foreach_get("co", relative)
			relatives[block.relative_key.name] = relative
		offset = (co - relative).reshape(-1, 3).astype(np.float64)

		if block.vertex_group:
			share = np.zeros(count)
			pick = groups == names.get(block.vertex_group, -1)
			share[verts[pick]] = weights[pick]
			offset *= share[:, None]
		yield block.name, offset


def _mapped_keys(
	obj: Object, keys: Key, mesh: Mesh
) -> list[tuple[str, np.ndarray]] | None:
	"""Each key alone on the baked base, its offsets carried over by where each baked vertex came from:
	one evaluation instead of one per key. None when a modifier didn't carry the origins through."""
	index = _carried_index(obj, mesh)
	if index is None:
		return None
	base = positions(mesh)
	linear = np.array(obj.matrix_world.to_3x3())
	return [
		(name, base + offset[index] @ linear.T) for name, offset in _offsets(obj, keys)
	]


def _evaluated_keys(
	context: Context, obj: Object, keys: Key, mesh: Mesh
) -> tuple[list[tuple[str, np.ndarray]], list[str]]:
	"""Each key alone, the mesh evaluated once per key: for modifiers that lose where vertices came from."""
	depsgraph = context.evaluated_depsgraph_get()
	shaped, skipped = [], []
	for block in list(keys.key_blocks)[1:]:
		# A key relative to another adds what it differs from that one by: alone, on the base.
		block.value = 1.0
		depsgraph.update()
		evaluated = obj.evaluated_get(depsgraph)
		co = positions(evaluated.to_mesh())
		evaluated.to_mesh_clear()
		block.value = 0.0

		if len(co) != len(mesh.vertices):
			skipped.append(f"{obj.name}: {block.name}")
		else:
			shaped.append((block.name, transformed(co, obj.matrix_world)))
	return shaped, skipped


def bake_keyed(
	context: Context, obj: Object, bake: Callable[[], Mesh]
) -> tuple[Mesh, list[Shape], list[str]]:
	"""The mesh baked, and each of its shape keys baked alone the same way, with the key's own settings.
	Keys that couldn't be baked come back by name."""
	shaped, skipped = [], []
	with _keys_at_rest(obj) as keys:
		if keys is None or len(keys.key_blocks) < 2:
			return bake(), [], []

		with _carrying_index(obj):
			mesh = bake()
		shaped = _mapped_keys(obj, keys, mesh)
		if shaped is None:
			shaped, skipped = _evaluated_keys(context, obj, keys, mesh)
		if _INDEX in mesh.attributes:
			mesh.attributes.remove(mesh.attributes[_INDEX])

	# Read once the keys are released and have their own settings back.
	blocks = obj.data.shape_keys.key_blocks
	shapes = [
		Shape(
			name,
			co,
			blocks[name].value,
			blocks[name].slider_min,
			blocks[name].slider_max,
			blocks[name].mute,
		)
		for name, co in shaped
	]
	return mesh, shapes, skipped


def add_shape_keys(copy: Object, original: Object, shapes: list[Shape]) -> None:
	"""Give the copy the original's baked keys, on a reference key of the original's name."""
	if not shapes:
		return
	copy.shape_key_add(name=original.data.shape_keys.reference_key.name, from_mix=False)
	for shape in shapes:
		key = copy.shape_key_add(name=shape.name, from_mix=False)
		key.data.foreach_set("co", shape.co.astype(np.float32).ravel())
		key.slider_min, key.slider_max = shape.slider_min, shape.slider_max
		key.value, key.mute = shape.value, shape.mute
