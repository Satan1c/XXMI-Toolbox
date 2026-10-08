from collections.abc import Callable
from dataclasses import dataclass

import bpy
import numpy as np
from bpy.types import ArmatureEditBones, Bone, Context, Object
from mathutils import Vector
from mathutils.geometry import intersect_point_line

from ...common.log import log
from ...common.utils import positions
from ...vertex_groups.weights import read_weights
from ..attach import editing
from ..cleanup import point_at_children
from ..influence import Influence, group_influence, merged
from .rigs import Part

# Rest shape of bendy bones; handles stay automatic, since custom ones point at controls that are gone.
_BBONE_REST = (
	"bbone_segments",
	"bbone_easein",
	"bbone_easeout",
	"bbone_rollin",
	"bbone_rollout",
	"use_endroll_as_inroll",
	"bbone_curveinx",
	"bbone_curveinz",
	"bbone_curveoutx",
	"bbone_curveoutz",
	"bbone_scalein",
	"bbone_scaleout",
)
# A bone moving nothing itself is a group node when it's farther than this share of the skeleton's size
# from its parent and its children.
_NODE_GAP = 0.1


@dataclass
class _Joint:
	"""A bone of the skeleton to build: where it lies in world space, what it hangs from, what it's made from."""

	head: Vector
	tail: Vector
	parent: str | None
	rig: Object
	bone: Bone


def influence(
	meshes: list[Object],
) -> tuple[dict[str, Influence], dict[frozenset[str], float]]:
	"""Per group, the vertices it weighs and their weights;
	per pair of groups, how much weight they share where they meet (each vertex's two strongest).
	The meshes are in world space."""
	moved = merged(
		(name, part)
		for obj in meshes
		for name, part in group_influence(obj, positions(obj.data)).items()
	)

	shared = {}
	for obj in meshes:
		verts, groups, weights = read_weights(obj.data)
		names = [vg.name for vg in obj.vertex_groups]
		order = np.lexsort((-weights, verts))
		v, g, w = verts[order], groups[order], weights[order]
		second = np.flatnonzero((v[1:] == v[:-1]) & np.r_[True, v[1:-1] != v[:-2]]) + 1
		for i in second:
			if w[i] > 0.0:
				key = frozenset((names[g[i - 1]], names[g[i]]))
				shared[key] = shared.get(key, 0.0) + float(w[i])
	return moved, shared


def _kept(part: Part) -> set[str]:
	"""The deform bones moving the part's used groups, and their deform ancestors, but group nodes."""
	bones = part.rig.data.bones
	original = {new: old for old, new in part.names.items()}
	kept = set()
	for name in part.used:
		bone = bones.get(original.get(name, name))
		while bone is not None:
			if bone.use_deform:
				kept.add(bone.name)
			bone = bone.parent

	# A bone moving nothing itself, far from its parent and its children
	# (a game face rig's group node at the world's origin, hung from the head) carries no joint:
	# its children hang from its parent instead.
	corners = np.array([bones[n].head_local for n in kept] or [(0.0, 0.0, 0.0)])
	size = float(np.linalg.norm(corners.max(0) - corners.min(0)))
	for name in [n for n in kept if part.names[n] not in part.used]:
		bone = bones[name]
		if bone.parent is None or bone.parent.name not in kept:
			continue
		near = [
			(bone.head_local - bone.parent.head_local).length,
			(bone.head_local - bone.parent.tail_local).length,
			*((bone.head_local - c.head_local).length for c in bone.children),
		]
		if min(near) > size * _NODE_GAP:
			kept.discard(name)
			log.debug(
				"%s: %s moves nothing and sits apart, left out", part.rig.name, name
			)
	return kept


def _kept_parent(
	part: Part, bone: Bone, kept: set[str], main: Part, kept_main: set[str]
) -> str | None:
	"""The skeleton name of the nearest kept bone above: a control between two deform bones goes.
	A held armature's root hangs from the main rig's bone holding it."""
	parent = bone.parent
	while parent is not None and parent.name not in kept:
		parent = parent.parent
	if parent is not None:
		return part.names[parent.name]

	host = main.rig.data.bones.get(part.hosts.get(bone.name, ""))
	while host is not None and host.name not in kept_main:
		host = host.parent
	return host.name if host is not None else None


def _joints(parts: list[Part]) -> dict[str, _Joint]:
	main = parts[0]
	kept_main = _kept(main)
	joints = {}
	for part in parts:
		kept = kept_main if part is main else _kept(part)
		matrix = part.rig.matrix_world
		for name in kept:
			bone = part.rig.data.bones[name]
			joints[part.names[name]] = _Joint(
				matrix @ bone.head_local,
				matrix @ bone.tail_local,
				_kept_parent(part, bone, kept, main, kept_main),
				part.rig,
				bone,
			)
	return joints


def _segment_distance(point: Vector, head: Vector, tail: Vector) -> float:
	closest, t = intersect_point_line(point, head, tail)
	if t < 0.0:
		closest = head
	elif t > 1.0:
		closest = tail
	return (point - closest).length


class _Orphans:
	"""Parents for deform bones that hang from controls only."""

	def __init__(
		self, joints: dict[str, _Joint], shared: dict[frozenset[str], float]
	) -> None:
		self.joints = joints
		self.shared = shared
		heads = [joint.head for joint in joints.values()]
		size = max(((head - heads[0]).length for head in heads), default=0.0)
		self.joint_gap = (size or 1.0) * 1e-3

	def hang(self) -> None:
		"""The bone ending where an orphan starts (rigs like Auto-Rig Pro keep their joints exact),
		else the one sharing the most weight with it on the mesh, else the nearest one.
		The bone above most of the rest stays the root."""
		joints = self.joints
		orphans = [name for name, joint in joints.items() if joint.parent is None]
		for name in orphans:
			gap, parent = self._nearest(
				name, lambda other: (joints[other].tail - joints[name].head).length
			)
			if gap < self.joint_gap:
				joints[name].parent = parent
				log.debug("%s hangs from %s, ending where it starts", name, parent)

		orphans = [name for name in orphans if joints[name].parent is None]
		if len(orphans) < 2:
			return
		root = max(orphans, key=lambda name: sum(self._below(o, name) for o in joints))
		for name in orphans:
			if name != root:
				joints[name].parent = self._joined(name)
				log.debug(
					"%s hangs from %s, by shared weight or nearness",
					name,
					joints[name].parent,
				)

	def _joined(self, name: str) -> str | None:
		# Where a bone blends into another is where it joins it: a tail into the hips, not the skirt beside it.
		blend, parent = self._nearest(
			name, lambda other: -self.shared.get(frozenset((name, other)), 0.0)
		)
		if blend < 0.0:
			return parent
		head = self.joints[name].head
		return self._nearest(
			name,
			lambda other: _segment_distance(
				head, self.joints[other].head, self.joints[other].tail
			),
		)[1]

	def _below(self, name: str | None, other: str) -> bool:
		while name is not None:
			if name == other:
				return True
			name = self.joints[name].parent
		return False

	def _nearest(
		self, name: str, distance: Callable[[str], float]
	) -> tuple[float, str | None]:
		return min(
			(
				(distance(other), other)
				for other in self.joints
				if other != name and not self._below(other, name)
			),
			default=(float("inf"), None),
		)


def _add_bones(edit_bones: ArmatureEditBones, joints: dict[str, _Joint]) -> None:
	for name, joint in joints.items():
		edit_bone = edit_bones.new(name)
		edit_bone.head, edit_bone.tail = joint.head, joint.tail
		edit_bone.align_roll(joint.rig.matrix_world.to_3x3() @ joint.bone.z_axis)
		for prop in _BBONE_REST:
			if hasattr(joint.bone, prop):
				setattr(edit_bone, prop, getattr(joint.bone, prop))

	for name, joint in joints.items():
		if joint.parent is not None:
			edit_bones[name].parent = edit_bones[joint.parent]


def deform_skeleton(
	context: Context,
	parts: list[Part],
	moved: dict[str, Influence],
	shared: dict[frozenset[str], float],
) -> Object:
	"""A plain armature of the deform bones the parts' meshes use and their deform ancestors, in world space,
	with no controls, constraints or drivers.
	The first part is the main rig; the others' bones hang from the bones holding them."""
	joints = _joints(parts)
	_Orphans(joints, shared).hang()

	name = parts[0].rig.name
	skeleton = bpy.data.objects.new(name, bpy.data.armatures.new(name))
	# Seen through the meshes, as rigs and imported game armatures are.
	skeleton.show_in_front = True
	context.scene.collection.objects.link(skeleton)
	try:
		with editing(context, skeleton) as edit_bones:
			_add_bones(edit_bones, joints)
			# Bones a ripper left pointing the wrong way (a model's ripped extras) are turned;
			# the rig's own keep theirs. Its look at rest doesn't change: heads stay where they are.
			point_at_children(list(edit_bones), moved, repair_only=True)
	finally:
		context.scene.collection.objects.unlink(skeleton)
	return skeleton
