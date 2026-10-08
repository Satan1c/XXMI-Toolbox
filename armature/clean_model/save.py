import bpy
from bpy.types import Context, Object

from ...common.library import write_objects
from ...common.log import log, timed
from ...common.utils import ToolError, armature_modifier
from .bake import baked_meshes
from .keys import add_shape_keys
from .materials import DetachedMaterials
from .rigs import keep_own_groups, main_rig, rig_parts
from .skeleton import deform_skeleton, influence
from .uvs import tidy_uvs

# Armature modifier settings the copies keep from their originals.
_DEFORM_SETTINGS = (
	"use_deform_preserve_volume",
	"use_bone_envelopes",
	"use_vertex_groups",
)


def _rig_copy(copy: Object, original: Object, skeleton: Object) -> None:
	"""Deform the copy by the skeleton as the original was by its rig.
	Groups of bones the skeleton doesn't have deform nothing: masks are already applied, controls are gone."""
	bones = skeleton.data.bones
	for vg in [vg for vg in copy.vertex_groups if vg.name not in bones]:
		copy.vertex_groups.remove(vg)
	modifier = copy.modifiers.new("Armature", "ARMATURE")
	modifier.object = skeleton
	source = armature_modifier(original)
	for prop in _DEFORM_SETTINGS:
		setattr(modifier, prop, getattr(source, prop))


def _write(
	filepath: str,
	rig: Object,
	skeleton: Object,
	copies: dict[Object, Object],
	materials: DetachedMaterials,
) -> None:
	"""Save the skeleton with the meshes in a collection of their own under its, to fold away in one click,
	all under the originals' names."""
	standing_in = {skeleton: rig, skeleton.data: rig.data, **materials.standing_in()}
	for original, copy in copies.items():
		standing_in[copy] = original
		standing_in.setdefault(copy.data, original.data)
	write_objects(
		filepath,
		rig.name,
		[skeleton],
		standing_in,
		nested={"Meshes": list(copies.values())},
	)


def _remove(copies: list[Object], skeleton: Object | None) -> None:
	for obj in [*copies, skeleton]:
		if obj is None:
			continue
		data = obj.data
		bpy.data.objects.remove(obj)
		if not data.users:
			(bpy.data.meshes if obj is not skeleton else bpy.data.armatures).remove(
				data
			)


def save_clean_model(
	context: Context,
	meshes: list[Object],
	filepath: str,
	drop_empty_uvs: bool = True,
	rename_uvs: bool = True,
) -> str:
	"""Save the meshes and the deform bones they use as a plain model:
	modifiers applied (into each shape key too), no rig controls or drivers, nothing else from the file."""
	rig = main_rig(meshes)
	if rig is None:
		raise ToolError("Select meshes deformed by an armature")
	parts, left_out = rig_parts(meshes, rig)
	part_of = {part.rig: part for part in parts}
	meshes = [obj for obj in meshes if obj.find_armature() in part_of]
	log.info(
		"saving %d meshes of %s to %s",
		len(meshes),
		", ".join(p.rig.name for p in parts),
		filepath,
	)

	with timed("baking"):
		baked, skipped = baked_meshes(context, meshes)
	copies = {
		obj: bpy.data.objects.new(obj.name, mesh) for obj, (mesh, _) in baked.items()
	}
	dropped_uvs = 0
	for obj, (mesh, _) in baked.items():
		dropped = tidy_uvs(mesh, drop_empty_uvs, rename_uvs)
		if dropped:
			log.debug(
				"%s: %d UV maps barely cover any faces, dropped", obj.name, dropped
			)
		dropped_uvs += dropped

	skeleton, materials = None, DetachedMaterials()
	try:
		for obj, copy in copies.items():
			keep_own_groups(copy, part_of[obj.find_armature()])
		with timed("building the skeleton"):
			moved, shared = influence(list(copies.values()))
			skeleton = deform_skeleton(context, parts, moved, shared)
		bone_count = len(skeleton.data.bones)

		for obj, copy in copies.items():
			_rig_copy(copy, obj, skeleton)
			add_shape_keys(copy, obj, baked[obj][1])
			materials.swap(copy)
		with timed("writing"):
			_write(filepath, rig, skeleton, copies, materials)
	finally:
		_remove(list(copies.values()), skeleton)
		materials.remove()

	notes = [
		f"Saved {len(copies)} meshes and {bone_count} deform bones of {rig.name} to {filepath}"
	]
	if len(parts) > 1:
		notes.append("with the bones of " + ", ".join(p.rig.name for p in parts[1:]))
	if left_out:
		notes.append(
			f"left out meshes of armatures that don't follow {rig.name}: "
			+ ", ".join(left_out)
		)
	if dropped_uvs:
		notes.append(f"dropped {dropped_uvs} UV maps that barely cover any faces")
	if skipped:
		notes.append(
			"shape keys a modifier changes the vertex count of were left out: "
			+ ", ".join(skipped)
		)
	return "; ".join(notes)
