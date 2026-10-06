import json

import bpy
import numpy as np
from bpy.types import Context, Mesh, Object

from ..common.utils import ToolError

MERGED_OBJECT_KEY = "XXMI_Toolbox:MergedObjectComponents"
# Merged objects made by WWMI/EFMI Tools store {name: vertex count} in join order instead.
LEGACY_MERGED_OBJECT_KEYS = (
	"WWMI:MergedObjectComponents",
	"EFMI:MergedObjectComponents",
)
PART_ATTRIBUTE = "xxmi_toolbox_part"


def create_merged_object(context: Context, objects: list[Object]) -> Object:
	if len(objects) < 2:
		raise ToolError("Select at least 2 meshes")
	collection = objects[0].users_collection[0]
	copies = []
	for i, obj in enumerate(objects):
		copy = obj.copy()
		copy.data = obj.data.copy()
		collection.objects.link(copy)
		# Join order isn't guaranteed to follow selection order, so tag every vertex with its origin.
		part = copy.data.attributes.new(PART_ATTRIBUTE, "INT", "POINT")
		part.data.foreach_set("value", [i] * len(copy.data.vertices))
		copies.append(copy)
	copy_meshes = [copy.data for copy in copies[1:]]
	with context.temp_override(
		object=copies[0],
		active_object=copies[0],
		selected_objects=copies,
		selected_editable_objects=copies,
	):
		bpy.ops.object.join()
	for mesh in copy_meshes:
		if mesh.users == 0:
			bpy.data.meshes.remove(mesh)

	merged = copies[0]
	merged.name = "MERGED_OBJECT"
	merged[MERGED_OBJECT_KEY] = json.dumps([obj.name for obj in objects])
	if merged.data.shape_keys is not None:
		# Otherwise sculpting may land on whichever key was active instead of the Basis.
		merged.active_shape_key_index = 0
	for obj in context.selected_objects:
		obj.select_set(False)
	merged.select_set(True)
	context.view_layer.objects.active = merged
	return merged


def _base_coords(mesh: Mesh) -> np.ndarray:
	key = mesh.shape_keys
	source = key.reference_key.data if key is not None else mesh.vertices
	coords = np.empty(len(source) * 3, dtype=np.float32)
	source.foreach_get("co", coords)
	return coords.reshape(-1, 3)


def apply_merged_sculpt(merged: Object, apply_to_shape_keys: bool = False) -> int:
	if MERGED_OBJECT_KEY in merged:
		names = json.loads(merged[MERGED_OBJECT_KEY])
		if PART_ATTRIBUTE not in merged.data.attributes:
			raise ToolError(f"{merged.name}: `{PART_ATTRIBUTE}` attribute is missing")
		parts = np.empty(len(merged.data.vertices), dtype=np.int32)
		merged.data.attributes[PART_ATTRIBUTE].data.foreach_get("value", parts)
	else:
		legacy = next((k for k in LEGACY_MERGED_OBJECT_KEYS if k in merged), None)
		if legacy is None:
			raise ToolError(f"{merged.name}: not a merged object")
		counts = json.loads(merged[legacy])
		names = list(counts)
		parts = np.repeat(np.arange(len(names)), list(counts.values()))
		if len(parts) != len(merged.data.vertices):
			raise ToolError(
				f"{merged.name}: vertex count no longer matches the merged objects"
			)

	matrix = np.array(merged.matrix_world, dtype=np.float64)
	world = _base_coords(merged.data) @ matrix[:3, :3].T + matrix[:3, 3]

	targets = []
	for i, name in enumerate(names):
		obj = bpy.data.objects.get(name)
		if obj is None or obj.type != "MESH":
			raise ToolError(f"Merged component `{name}` no longer exists")
		coords = world[parts == i]
		if len(coords) != len(obj.data.vertices):
			raise ToolError(
				f"`{name}` vertex count changed since the merged object was created"
			)
		targets.append((obj, coords))

	for obj, coords in targets:
		inverse = np.linalg.inv(np.array(obj.matrix_world, dtype=np.float64))
		local = (coords @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
		mesh = obj.data
		key = mesh.shape_keys
		if key is not None:
			basis = key.reference_key
			if apply_to_shape_keys:
				delta = local - _base_coords(mesh)
				data = np.empty(len(basis.data) * 3, dtype=np.float32)
				for block in key.key_blocks:
					if block == basis:
						continue
					block.data.foreach_get("co", data)
					block.data.foreach_set("co", (data.reshape(-1, 3) + delta).ravel())
			basis.data.foreach_set("co", local.ravel())
		mesh.vertices.foreach_set("co", local.ravel())
		mesh.update()
	return len(targets)
