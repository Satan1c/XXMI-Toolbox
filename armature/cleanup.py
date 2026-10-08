import math
from collections import Counter

import bpy
from bpy.types import Context, EditBone, Object
from mathutils import Matrix, Vector

from ..common.log import log
from ..common.utils import (
	ToolError,
	armature_modifier,
	deformed_by,
	positions,
	transformed,
)
from ..vertex_groups.ids import vg_id
from .attach import Space, editing, existing_spaces
from .influence import Influence, elongation, extent, group_influence, merged, reach

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


# Hand-made rigs: a bone heading within this angle of its child is taken to lead to it.
FOLLOWS = math.radians(60)
# What a chain's end moves counts as hanging off it in a line once it's this many times longer than wide.
ELONGATED = 2.0
# A bone whose head lies partway along an ancestor's segment, this near its line (relative to its length),
# is one of the limb's bands (a twist bone).
BAND = 0.02
# One at its parent's own joint is a band too when what it moves runs within this angle of the parent's line
# (a calf's helper at the knee, weighted down the calf).
ALONG = math.radians(30)


class _Pointer:
	"""Points the bones of one armature, from the roots down: see point_at_children."""

	def __init__(
		self, edit_bones: list[EditBone], moved: dict[str, Influence], repair_only: bool
	) -> None:
		heads = [bone.head for bone in edit_bones]
		size = max((head - heads[0]).length for head in heads) if heads else 0.0
		self.shortest = (size or 1.0) * 1e-3
		self.moved = moved
		self.repair_only = repair_only
		self.connected = 0

	def visit(self, bone: EditBone, direction: Vector | None, beside: Vector) -> None:
		"""Point the bone, then its children.
		Direction is the way its chain comes in, if it carries one on; beside is its parent's way."""
		children = sorted(
			bone.children, key=lambda child: -(child.head - bone.head).length
		)
		roll_axis = bone.z_axis.copy()

		chain = self._chain(bone, children)
		if chain is not None:
			tail = chain.head.copy()
		elif children:
			tail = self._branch_tail(bone, children, beside)
		else:
			tail = self._end_tail(bone, direction, beside)

		# A twist bone runs along its limb, inside it, whatever hangs off it: a sleeve's physics root.
		band = None if self.repair_only else self._band(bone)
		if band is not None:
			tail, chain = band, None

		if tail is not None:
			bone.tail = tail
			bone.align_roll(roll_axis)
		if chain is not None:
			chain.use_connect = True
			self.connected += 1

		way = bone.vector.normalized()
		for child in children:
			self.visit(child, way if child == chain else None, way)

	def _reaches(self, bone: EditBone, point: Vector | None) -> bool:
		"""Whether the point lies far enough from the bone's head to aim at."""
		return point is not None and (point - bone.head).length > self.shortest * 10

	def _length_along(self, bone: EditBone, way: Vector) -> float:
		"""As far as what the bone moves goes along the way, else half its parent's length."""
		influence = self.moved.get(bone.name)
		length = extent(bone.head, way, influence) if influence else 0.0
		return length if length > self.shortest * 10 else bone.parent.length * 0.5

	def _chain(self, bone: EditBone, children: list[EditBone]) -> EditBone | None:
		"""The child carrying on the bone's chain: the farthest one, when it's clearly past the rest
		(the hand past the forearm's twist bones, which share its line and would end up inside it)."""
		if not children:
			return None
		distances = [(child.head - bone.head).length for child in children[:2]]
		if distances[0] <= self.shortest:
			return None
		if len(children) > 1 and distances[0] < distances[1] * 1.5:
			return None

		# A toe beside the toe joint isn't where that joint's bone leads: hand-made rigs keep it pointing ahead.
		heading = bone.vector.angle(children[0].head - bone.head, math.pi)
		if self.repair_only and heading > FOLLOWS:
			return None
		return children[0]

	def _branch_tail(
		self, bone: EditBone, children: list[EditBone], beside: Vector
	) -> Vector | None:
		"""Between several children: at their middle. Hand-made rigs keep their way."""
		if self.repair_only:
			return None

		count = len(children)
		middle = sum((child.head for child in children), Vector()) / count
		spread = sum((child.head - bone.head).length for child in children) / count
		if (middle - bone.head).length > max(spread * 0.25, self.shortest):
			return middle

		# Children around the head (a pelvis between spine and legs, a sleeve's root amid its strands)
		# give no direction worth taking: it carries on its parent's way, the rip's being anything.
		if bone.parent is not None:
			return bone.head + beside * max(bone.length, self.shortest * 10)
		return None

	def _end_tail(
		self, bone: EditBone, direction: Vector | None, beside: Vector
	) -> Vector | None:
		influence = self.moved.get(bone.name)
		end = reach(bone.head, influence) if influence else None
		if self.repair_only:
			return self._repaired_end_tail(bone, direction, end)

		# What it moves hangs off it in a line (a charm off a hem strand, a bow's half):
		# towards its far end, so ends sharing a head part ways.
		# One off its parent's chain (a shake bone beside an ornament) points at what it moves too:
		# the way the rip pointed it is anything, and mirrored bones would part.
		if self._reaches(bone, end) and (
			direction is None or elongation(influence) > ELONGATED
		):
			return end

		# A compact end (a fingertip) carries on its parent's line, as far as what it moves goes along it:
		# aiming at a compact spread of vertices would send it out sideways.
		# Off the chain with nothing to aim at, it takes its parent's way too.
		if bone.parent is not None:
			way = direction if direction is not None else beside
			return bone.head + way * self._length_along(bone, way)
		return None

	def _repaired_end_tail(
		self, bone: EditBone, direction: Vector | None, end: Vector | None
	) -> Vector | None:
		"""Only the last bone of a chain pointing back against it is turned (a ripped tail tip pointing up its tail):
		towards what it moves if that lies ahead, else on along the chain.
		Anything else keeps the rig's way, a compact spread (a toe's part of a shoe) being no direction to trust."""
		if direction is None or bone.vector.angle(direction, 0.0) <= math.pi / 2:
			return None
		ahead = self._reaches(bone, end) and (
			(end - bone.head).angle(direction, math.pi) < math.pi / 2
		)
		if ahead:
			return end
		return bone.head + direction * self._length_along(bone, direction)

	def _band(self, bone: EditBone) -> Vector | None:
		"""For a band of a limb, a tail on along the limb, short of its segment's end:
		drawn as a ring, it then lies wholly inside, not on the tip."""
		tail = self._partway_band(bone)
		return tail if tail is not None else self._joint_band(bone)

	def _partway_band(self, bone: EditBone) -> Vector | None:
		"""A bone whose head lies partway along its parent's or grandparent's segment."""
		for ancestor in (bone.parent, bone.parent and bone.parent.parent):
			if ancestor is None or ancestor.length < self.shortest:
				continue
			way = ancestor.vector
			share = (bone.head - ancestor.head).dot(way) / way.length_squared
			off = (bone.head - (ancestor.head + way * share)).length
			if 0.05 < share < 0.95 and off <= BAND * way.length:
				return ancestor.head + way * (share + (1.0 - share) * 0.75)
		return None

	def _joint_band(self, bone: EditBone) -> Vector | None:
		"""A bone at its parent's joint moving what runs along the parent."""
		parent, influence = bone.parent, self.moved.get(bone.name)
		if parent is None or influence is None or parent.length < self.shortest:
			return None
		if (bone.head - parent.head).length > BAND * parent.length:
			return None

		end = reach(bone.head, influence)
		if (
			self._reaches(bone, end)
			and (end - bone.head).angle(parent.vector, math.pi) <= ALONG
		):
			return parent.head + parent.vector * 0.75
		return None


def point_at_children(
	edit_bones: list[EditBone], moved: dict[str, Influence], repair_only: bool = False
) -> int:
	"""Point bones at the child that carries on their chain (else at the middle of several) and connect it;
	point ends at the far end of what they move when it hangs off them in a line, else along their parent's chain.
	Returns how many connected.
	Heads stay where they are, and rolls stay as close to the old ones as the new direction allows.

	Ripped armatures point their bones anywhere, so every bone is redone.
	With repair_only, for rigs made by hand, bones keep the way they point unless it's plainly broken:
	a bone already heading for its child is joined to it,
	and a chain's last bone pointing back against it is turned round."""
	for bone in edit_bones:
		bone.use_connect = False

	pointer = _Pointer(edit_bones, moved, repair_only)
	for bone in edit_bones:
		if bone.parent is None:
			pointer.visit(bone, None, bone.vector.normalized())
	return pointer.connected


def _deformed_influence(
	rig: Object, spaces: list[Space], meshes: set[Object]
) -> dict[str, Influence]:
	"""{game bone: the armature-space dumped vertices its IDs weigh, and their weights}."""
	bones = {space.armature: space.bones for space in spaces}
	to_rig = rig.matrix_world.inverted()
	parts = []
	for obj in meshes:
		modifier = armature_modifier(obj, bones)
		if modifier is None:
			continue
		co = transformed(positions(obj.data), to_rig @ obj.matrix_world)
		for name, influence in group_influence(obj, co).items():
			bone = bones[modifier.object].get(vg_id(name))
			if bone is not None:
				parts.append((bone, influence))
	return merged(parts)


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
	moved = _deformed_influence(rig, spaces, meshes)
	with editing(context, rig) as edit_bones:
		connected = point_at_children(list(edit_bones), moved)
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
	attached = set(deformed_by(context.scene.objects, armatures))
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
	log.debug("removing objects: %s", ", ".join(sorted(obj.name for obj in doomed)))
	log.debug("removing bones: %s", ", ".join(unused))
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
			space.meshes = deformed_by(
				sorted(attached, key=lambda obj: (-len(obj.data.polygons), obj.name)),
				{space.armature},
			)
		moved = sum(_gather(space) for space in spaces)
		line += f"; moved {moved} ID armatures to their meshes' collections"
	return line
