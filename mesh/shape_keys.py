import re

import bpy
import numpy as np
from bpy.types import Context, Mesh, Object

from ..common.utils import ToolError


def _replace_mesh(obj: Object, mesh: Mesh) -> None:
	old = obj.data
	name = old.name
	obj.data = mesh
	if old.users == 0:
		bpy.data.meshes.remove(old)
	mesh.name = name


def apply_modifiers_with_shape_keys(
	context: Context, obj: Object, names: list[str]
) -> None:
	modifiers = [m for m in obj.modifiers if m.name in names]
	if not modifiers:
		return
	muted = [m for m in obj.modifiers if m.name not in names and m.show_viewport]
	hidden = [m for m in modifiers if not m.show_viewport]
	for m in muted:
		m.show_viewport = False
	for m in hidden:
		m.show_viewport = True
	key = obj.data.shape_keys
	state = (obj.show_only_shape_key, obj.active_shape_key_index)
	meta = []
	try:
		depsgraph = context.evaluated_depsgraph_get()
		if key is None:
			depsgraph.update()
			baked = bpy.data.meshes.new_from_object(
				obj.evaluated_get(depsgraph),
				preserve_all_data_layers=True,
				depsgraph=depsgraph,
			)
			_replace_mesh(obj, baked)
		else:
			blocks = key.key_blocks
			meta = [
				{
					"name": k.name,
					"mute": k.mute,
					"interpolation": k.interpolation,
					"value": k.value,
					"slider_min": k.slider_min,
					"slider_max": k.slider_max,
					"vertex_group": k.vertex_group,
					"relative_key": k.relative_key.name if k.relative_key else "",
				}
				for k in blocks
			]
			# The key's own vertex group would otherwise be baked into its coordinates and applied a second time.
			for k in blocks:
				k.vertex_group = ""
			obj.show_only_shape_key = True
			basis, coords = None, []
			for i in range(len(blocks)):
				obj.active_shape_key_index = i
				depsgraph.update()
				baked = bpy.data.meshes.new_from_object(
					obj.evaluated_get(depsgraph),
					preserve_all_data_layers=True,
					depsgraph=depsgraph,
				)
				if basis is not None and len(baked.vertices) != len(basis.vertices):
					bpy.data.meshes.remove(baked)
					bpy.data.meshes.remove(basis)
					raise ToolError(
						f"{obj.name}: modifiers change vertex count between shape keys"
					)
				if basis is None:
					basis = baked
					continue
				data = np.empty(len(baked.vertices) * 3, dtype=np.float32)
				baked.vertices.foreach_get("co", data)
				coords.append(data)
				bpy.data.meshes.remove(baked)
			obj.show_only_shape_key, obj.active_shape_key_index = state
			_replace_mesh(obj, basis)
			obj.shape_key_add(name=meta[0]["name"], from_mix=False)
			for entry, data in zip(meta[1:], coords):
				obj.shape_key_add(name=entry["name"], from_mix=False).data.foreach_set(
					"co", data
				)
			blocks = obj.data.shape_keys.key_blocks
			for block, entry in zip(blocks, meta):
				for attr in (
					"mute",
					"interpolation",
					"slider_min",
					"slider_max",
					"value",
					"vertex_group",
				):
					setattr(block, attr, entry[attr])
				if entry["relative_key"] in blocks:
					block.relative_key = blocks[entry["relative_key"]]
			obj.active_shape_key_index = state[1]
		for m in modifiers:
			obj.modifiers.remove(m)
	finally:
		if obj.data.shape_keys is key and key is not None:
			obj.show_only_shape_key, obj.active_shape_key_index = state
			for block, entry in zip(key.key_blocks, meta):
				block.vertex_group = entry["vertex_group"]
		for m in muted:
			m.show_viewport = True
		for m in hidden:
			if m.name in obj.modifiers:
				m.show_viewport = False


# What the exporters take: the game's own keys (imported as "Deform <n>") and the mod's ("Custom <n>").
EXPORT_NAME = re.compile(r"(DEFORM|CUSTOM)[ _\-.]?(\d{1,4})", re.IGNORECASE)
# {new name: name before renaming}, so a "Custom <n>" can still be told apart.
ORIGINAL_NAMES_KEY = "XXMI_Toolbox:ShapeKeyNames"


def name_for_export(meshes: list[Object]) -> int:
	"""Rename every shape key the exporters wouldn't take to "Custom <n>", numbering after the highest one in use.
	A name shared by several meshes gets one number, so their keys stay one key in game."""
	blocks = [
		block
		for obj in meshes
		if obj.data.shape_keys is not None
		for block in obj.data.shape_keys.key_blocks
	]
	numbers = [
		int(match.group(2))
		for block in blocks
		if (match := EXPORT_NAME.fullmatch(block.name))
		and match.group(1).upper() == "CUSTOM"
	]
	next_number = max(numbers, default=-1) + 1

	assigned, renamed = {}, 0
	for obj in meshes:
		keys = obj.data.shape_keys
		if keys is None:
			continue

		originals = dict(obj.get(ORIGINAL_NAMES_KEY, {}))
		for block in keys.key_blocks:
			if block == keys.reference_key or EXPORT_NAME.fullmatch(block.name):
				continue
			if block.name not in assigned:
				assigned[block.name] = next_number
				next_number += 1
			new_name = f"Custom {assigned[block.name]}"
			originals[new_name] = block.name
			block.name = new_name
			renamed += 1
		# The exporters tell the base key by this name; renamed last, so no other key holds it by then.
		keys.reference_key.name = "Basis"
		obj[ORIGINAL_NAMES_KEY] = originals
	return renamed
