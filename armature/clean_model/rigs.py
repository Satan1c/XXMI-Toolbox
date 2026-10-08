from dataclasses import dataclass, field

from bpy.types import Object

from ...vertex_groups.weights import read_weights


@dataclass
class Part:
	"""An armature whose bones go into the clean skeleton:
	the main rig, or one held to it (a tongue rig on the head)."""

	rig: Object
	# Its bones' names in the skeleton.
	names: dict[str, str]
	# For one held to the main rig: the main rig's bone each of its roots hangs from.
	hosts: dict[str, str] = field(default_factory=dict)
	# The skeleton names of the groups its meshes weigh.
	used: set[str] = field(default_factory=set)


def main_rig(meshes: list[Object]) -> Object | None:
	"""The armature deforming the most of the meshes."""
	counts = {}
	for obj in meshes:
		rig = obj.find_armature()
		if rig is not None:
			counts[rig] = counts.get(rig, 0) + 1
	return max(counts, key=counts.get) if counts else None


def _hosts(rig: Object, main: Object) -> dict[str, str] | None:
	"""{root bone: the main rig's bone it hangs from} for an armature that follows the main one,
	by Child Of constraints on its roots or by being parented to one of the main rig's bones; else None."""
	roots = [bone.name for bone in rig.data.bones if bone.parent is None]
	if rig.parent is main and rig.parent_type == "BONE":
		return {root: rig.parent_bone for root in roots}

	hosts = {}
	for root in roots:
		hold = next(
			(
				c
				for c in rig.pose.bones[root].constraints
				if c.type == "CHILD_OF" and c.target is main and c.subtarget
			),
			None,
		)
		if hold is None:
			return None
		hosts[root] = hold.subtarget
	return hosts or None


def _free_names(rig: Object, taken: set[str]) -> dict[str, str]:
	"""The rig's bone names, prefixed by the rig's where another rig has them already."""
	names = {}
	for bone in rig.data.bones:
		names[bone.name] = (
			bone.name if bone.name not in taken else f"{rig.name}_{bone.name}"
		)
		taken.add(names[bone.name])
	return names


def rig_parts(meshes: list[Object], main: Object) -> tuple[list[Part], list[str]]:
	"""The main rig's part and those of the armatures held to it,
	and the names of the meshes left out for being deformed by any other armature (a prop's)."""
	parts = {main: Part(main, {bone.name: bone.name for bone in main.data.bones})}
	taken = set(parts[main].names)
	refused = set()
	for rig in dict.fromkeys(obj.find_armature() for obj in meshes):
		if rig is None or rig in parts:
			continue
		hosts = _hosts(rig, main)
		if hosts is None:
			refused.add(rig)
		else:
			parts[rig] = Part(rig, _free_names(rig, taken), hosts)

	left_out = [obj.name for obj in meshes if obj.find_armature() in refused]
	return list(parts.values()), left_out


def keep_own_groups(copy: Object, part: Part) -> None:
	"""Keep only the groups of the copy's own armature, under their skeleton names, and note the ones it weighs:
	another armature's group of the same name would start moving it."""
	for vg in list(copy.vertex_groups):
		if vg.name in part.names:
			vg.name = part.names[vg.name]
		else:
			copy.vertex_groups.remove(vg)
	_, groups, weights = read_weights(copy.data)
	part.used.update(
		copy.vertex_groups[int(i)].name for i in set(groups[weights > 0.0])
	)
