import math
from collections import Counter

import bpy
from bpy.types import Context, EditBone, Object
from mathutils import Matrix, Vector

from ..common.utils import ToolError
from ..vertex_groups.ids import vg_id
from .attach import Space, editing, existing_spaces, group_centres

RING_KEY = "XXMI_Toolbox:Ring"


def _kept_bones(rig: Object, spaces: list[Space]) -> set[str]:
	"""The game bones the ID armatures copy, and their parents: a bone's pose depends on every bone above it."""
	kept = set()
	for space in spaces:
		for name in space.bones.values():
			bone = rig.data.bones.get(name)
			while bone is not None and bone.name not in kept:
				kept.add(bone.name)
				bone = bone.parent
	return kept


def _remove_objects(objects: set[Object]) -> int:
	collections = {collection for obj in objects for collection in obj.users_collection}
	meshes = {obj.data for obj in objects if obj.type == "MESH"}
	for obj in objects:
		bpy.data.objects.remove(obj)
	for mesh in meshes:
		if not mesh.users:
			bpy.data.meshes.remove(mesh)
	# Only collections this emptied: ones the user left empty are none of its business.
	emptied = [
		collection
		for collection in collections
		if isinstance(collection, bpy.types.Collection)
		and not collection.all_objects
		and not collection.children
	]
	for collection in emptied:
		bpy.data.collections.remove(collection)
	return len(emptied)


def _gather(space: Space) -> bool:
	"""Move the ID armature into the collection most of its meshes are in."""
	collections = Counter(
		obj.users_collection[0] for obj in space.meshes if obj.users_collection
	)
	if not collections:
		return False
	target = collections.most_common(1)[0][0]
	armature = space.armature
	if list(armature.users_collection) == [target]:
		return False
	for collection in armature.users_collection:
		collection.objects.unlink(armature)
	target.objects.link(armature)
	return True


def _point_at_children(edit_bones: list[EditBone], centres: dict[str, Vector]) -> int:
	"""Point bones at the child that carries on their chain (else at the middle of several) and connect it; point
	the ends of chains at the middle of what they deform. Returns how many connected. Heads stay where they are, and
	rolls stay as close to the old ones as the new direction allows."""
	heads = [bone.head for bone in edit_bones]
	size = (max((head - heads[0]).length for head in heads) if heads else 0.0) or 1.0
	shortest = size * 1e-3
	for bone in edit_bones:
		bone.use_connect = False
	connected = 0

	def visit(bone: EditBone, direction: Vector | None) -> None:
		nonlocal connected
		children = sorted(
			bone.children, key=lambda child: -(child.head - bone.head).length
		)
		distances = [(child.head - bone.head).length for child in children]
		roll_axis = bone.z_axis.copy()
		tail, chain = None, None
		# The farthest child carries on the chain when it's clearly past the rest: the hand past the forearm's
		# twist bones, which share its line and would end up inside it.
		if (
			children
			and distances[0] > shortest
			and (len(children) == 1 or distances[0] >= distances[1] * 1.5)
		):
			tail, chain = children[0].head.copy(), children[0]
		elif children:
			middle = sum((child.head for child in children), Vector()) / len(children)
			spread = sum(distances) / len(children)
			# Children around the head (a pelvis between spine and legs) give no direction worth taking.
			if (middle - bone.head).length > max(spread * 0.25, shortest):
				tail = middle
		elif (
			bone.name in centres
			and (centres[bone.name] - bone.head).length > shortest * 10
		):
			# To the middle of what it deforms, so ends sharing a head (the halves of a bow) part ways.
			tail = centres[bone.name].copy()
		elif direction is not None:
			# A chain's end carries on its parent's line.
			tail = bone.head + direction * bone.parent.length * 0.5
		if tail is not None:
			bone.tail = tail
			bone.align_roll(roll_axis)
		if chain is not None:
			chain.use_connect = True
			connected += 1
		for child in children:
			visit(child, bone.vector.normalized() if child == chain else None)

	for bone in edit_bones:
		if bone.parent is None:
			visit(bone, None)
	return connected


def _deformed_centres(
	rig: Object, spaces: list[Space], meshes: set[Object]
) -> dict[str, Vector]:
	"""{game bone: armature-space middle of the dumped vertices its IDs weigh}."""
	bones = {space.armature: space.bones for space in spaces}
	to_rig = rig.matrix_world.inverted()
	found = {}
	for obj in meshes:
		modifier = next(
			(
				mod
				for mod in obj.modifiers
				if mod.type == "ARMATURE" and mod.object in bones
			),
			None,
		)
		if modifier is None:
			continue
		for name, centre in group_centres(obj).items():
			bone = bones[modifier.object].get(vg_id(name))
			if bone is not None:
				found.setdefault(bone, []).append(to_rig @ Vector(centre))
	return {bone: sum(points, Vector()) / len(points) for bone, points in found.items()}


def _ring() -> Object:
	"""A circle around the middle of a bone, for the custom shape of bones that would be drawn inside another."""
	ring = next((obj for obj in bpy.data.objects if obj.get(RING_KEY)), None)
	if ring is not None:
		return ring
	count = 24
	mesh = bpy.data.meshes.new("XXMI Toolbox Ring")
	mesh.from_pydata(
		[
			(math.cos(2 * math.pi * i / count), 0.5, math.sin(2 * math.pi * i / count))
			for i in range(count)
		],
		[(i, (i + 1) % count) for i in range(count)],
		[],
	)
	# Only the pose bones use it: it stays out of the scene.
	ring = bpy.data.objects.new(mesh.name, mesh)
	ring[RING_KEY] = True
	return ring


def _half_width(inverse: Matrix, length: float, point: Vector) -> float | None:
	"""How far from its axis an octahedral bone reaches at the point, or None if the point is outside it."""
	local = inverse @ point
	t = local.y / length
	if not 0.0 <= t <= 1.0:
		return None
	width = 0.1 * length * (t / 0.1 if t < 0.1 else (1.0 - t) / 0.9)
	return width if abs(local.x) + abs(local.z) <= width + 1e-6 else None


def _ring_hidden(rig: Object) -> int:
	"""Draw bones lying wholly inside a longer one (a twist bone inside its limb) as rings around it."""
	bones = [
		(bone, bone.matrix_local.inverted(), bone.length) for bone in rig.data.bones
	]
	ringed = 0
	for bone, _, length in bones:
		points = [
			bone.head_local.lerp(bone.tail_local, f) for f in (0.25, 0.5, 0.75, 1.0)
		]
		width = next(
			(
				_half_width(inverse, other_length, points[1])
				for other, inverse, other_length in bones
				if other_length > length
				and all(
					_half_width(inverse, other_length, point) is not None
					for point in points
				)
			),
			None,
		)
		if width is None:
			continue
		scale = max(width * 1.6, length * 0.15) / length
		pose_bone = rig.pose.bones[bone.name]
		pose_bone.custom_shape = _ring()
		pose_bone.custom_shape_scale_xyz = (scale, 1.0, scale)
		ringed += 1
	return ringed


def _connect(
	context: Context, rig: Object, spaces: list[Space], meshes: set[Object]
) -> tuple[int, int]:
	centres = _deformed_centres(rig, spaces, meshes)
	with editing(context, rig) as edit_bones:
		connected = _point_at_children(list(edit_bones), centres)
	# An ID bone's rest must stay its game bone's, or copying the game bone's pose would offset the dump.
	for space in spaces:
		with editing(context, space.armature) as edit_bones:
			for group_id, name in space.bones.items():
				source = rig.data.bones[name]
				bone = edit_bones[str(group_id)]
				bone.matrix = source.matrix_local
				bone.length = source.length
	return connected, _ring_hidden(rig)


def clean_up(
	context: Context,
	rig: Object,
	gather_ids: bool = False,
	connect_bones: bool = False,
) -> str:
	"""Remove what the ID armatures don't need from the game model: its meshes, what hangs under it (weapons,
	props) and the bones nothing copies."""
	spaces = existing_spaces(context, rig)
	if not spaces:
		raise ToolError(
			f"Nothing follows {rig.name} yet: attach the dumped meshes first"
		)
	armatures = {space.armature for space in spaces}
	attached = {
		obj
		for obj in context.scene.objects
		if obj.type == "MESH"
		and any(
			mod.type == "ARMATURE" and mod.object in armatures for mod in obj.modifiers
		)
	}
	doomed = {
		obj
		for obj in context.scene.objects
		if obj.type == "MESH" and obj.find_armature() == rig
	}
	doomed |= set(rig.children_recursive)
	doomed -= attached | armatures | {rig}
	# Importers leave the game's empty transforms around the armature: drop the ones left holding nothing.
	ancestors, top = set(), rig
	while top.parent is not None:
		top = top.parent
		ancestors.add(top)
	doomed |= {
		obj
		for obj in top.children_recursive
		if obj.type == "EMPTY"
		and obj not in ancestors
		and all(
			child in doomed or child.type == "EMPTY" for child in obj.children_recursive
		)
	}

	kept = _kept_bones(rig, spaces)
	unused = [bone.name for bone in rig.data.bones if bone.name not in kept]
	if unused:
		with editing(context, rig) as edit_bones:
			for name in unused:
				edit_bones.remove(edit_bones[name])
	removed_objects = len(doomed)
	removed_collections = _remove_objects(doomed)
	# Kept for the transform they give the armature; hiding a parent leaves its children shown.
	for obj in ancestors:
		if obj.type == "EMPTY":
			obj.hide_set(True)
	line = (
		f"Removed {removed_objects} objects, {len(unused)} bones and {removed_collections} emptied collections "
		f"from {rig.name}; kept {len(kept)} bones"
	)
	if connect_bones:
		connected, ringed = _connect(context, rig, spaces, attached)
		line += f", {connected} connected, {ringed} inside others drawn as rings"
	if gather_ids:
		for space in spaces:
			# Largest first: a tie between collections goes to the main piece's.
			space.meshes = [
				obj
				for obj in sorted(
					attached, key=lambda obj: (-len(obj.data.polygons), obj.name)
				)
				if any(
					mod.type == "ARMATURE" and mod.object == space.armature
					for mod in obj.modifiers
				)
			]
		moved = sum(_gather(space) for space in spaces)
		line += f"; moved {moved} ID armatures to their meshes' collections"
	return line
