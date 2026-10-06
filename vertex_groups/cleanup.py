from collections.abc import Callable

import numpy as np
from bpy.types import Object

from ..common.utils import ToolError
from .ids import MergeKey, dup_suffix, merge_key, strip_dup_suffix, vg_id
from .weights import read_weights

# Only guards Fill Gaps against IDs parsed from names like "99999999"; other tools are unbounded on purpose.
# MergedSkeleton's merged palette holds 1024 bones, and its merged indices go through Fill Gaps.
FILL_MAX_ID = 1024


def remove_all(obj: Object) -> int:
	count = len(obj.vertex_groups)
	obj.vertex_groups.clear()
	return count


def remove_unused(obj: Object, threshold: float = 0.0) -> int:
	_, groups, weights = read_weights(obj.data)
	used = set(np.unique(groups[weights > threshold]).tolist())
	removed = 0
	for vg in reversed(list(obj.vertex_groups)):
		if vg.index not in used:
			obj.vertex_groups.remove(vg)
			removed += 1
	return removed


def merge_scope(
	mode: str, active_name: str = "", names: str = "", first: int = 0, last: int = 0
) -> Callable[[MergeKey], bool]:
	if mode == "ALL":
		return lambda key: True
	if mode == "ACTIVE":
		active_key = merge_key(active_name)
		return lambda key: key == active_key
	if mode == "LIST":
		keys = {merge_key(name.strip()) for name in names.split(",") if name.strip()}
		return lambda key: key in keys
	if mode == "RANGE":
		return lambda key: key[0] == "id" and first <= key[1] <= last
	raise ValueError(mode)


def merge(obj: Object, in_scope: Callable[[MergeKey], bool]) -> int:
	buckets = {}
	for vg in obj.vertex_groups:
		key = merge_key(vg.name)
		if in_scope(key):
			buckets.setdefault(key, []).append(vg)
	# A lone "3.001" is still worth cleaning up: remap leaves those behind when the plain name was taken.
	buckets = {
		key: members
		for key, members in buckets.items()
		if len(members) > 1 or dup_suffix.search(members[0].name)
	}
	if not buckets:
		return 0

	verts, groups, weights = read_weights(obj.data)
	vertex_count = len(obj.data.vertices)
	plans = []
	for members in buckets.values():
		# Prefer a labelled name ("0.head") over a bare ID ("0"), and either over a Blender duplicate ("0.head.001").
		keeper = min(
			members,
			key=lambda vg: (
				bool(dup_suffix.search(vg.name)),
				strip_dup_suffix(vg.name).strip().isdigit(),
				vg.index,
			),
		)
		mask = np.isin(groups, [vg.index for vg in members])
		totals = np.zeros(vertex_count)
		np.add.at(totals, verts[mask], weights[mask])
		plans.append(
			(
				keeper,
				strip_dup_suffix(keeper.name),
				[vg for vg in members if vg != keeper],
				totals,
			)
		)

	merged = 0
	for keeper, name, others, totals in plans:
		hit = np.nonzero(totals > 0.0)[0]
		values, inverse = np.unique(np.minimum(totals[hit], 1.0), return_inverse=True)
		for i, value in enumerate(values):
			keeper.add(hit[inverse == i].tolist(), float(value), "REPLACE")
		for vg in others:
			obj.vertex_groups.remove(vg)
		keeper.name = name
		merged += len(others)
	return merged


def fill_gaps(obj: Object, largest: int = 0) -> int:
	groups = list(obj.vertex_groups)
	if not groups and largest <= 0:
		return 0
	ids = [vg_id(vg.name) for vg in groups]
	used = {group_id for group_id in ids if group_id is not None}

	# Name-only groups (MMD, rips, hand-named) are assumed to already be in export order.
	renames = []
	for position, (vg, group_id) in enumerate(zip(groups, ids)):
		if group_id is not None:
			continue
		if position in used:
			raise ToolError(
				f"{obj.name}: `{vg.name}` would become ID {position}, which is already taken"
			)
		renames.append((vg, f"{position}.{vg.name}", position))

	top = max(
		[group_id for group_id in ids if group_id is not None]
		+ [pos for _, _, pos in renames]
		+ [largest]
	)
	if top >= FILL_MAX_ID:
		raise ToolError(
			f"{obj.name}: vertex group ID {top} is above the {FILL_MAX_ID - 1} limit"
		)

	for vg, name, position in renames:
		vg.name = name
		used.add(position)
	missing = [i for i in range(top + 1) if i not in used]
	for i in missing:
		obj.vertex_groups.new(name=str(i))
	return len(missing) + len(renames)
