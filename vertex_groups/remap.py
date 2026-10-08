from collections.abc import Callable

import bpy
import numpy as np
from bpy.types import Context, Mesh, Object

from ..common.log import log
from ..common.transfer import joined_source, transfer
from ..common.utils import ToolError, rename_all
from .weights import is_weighted, read_weights

# A target's vertices with the source weights sampled at them, and the source group names.
Reference = tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]
# Given the summed overlaps per target group and the source group names,
# the {target group: (source group, share)} to use instead of the most overlapped.
Choose = Callable[[dict[str, np.ndarray], list[str]], dict[str, tuple[str, float]]]


def _vertex_areas(mesh: Mesh) -> np.ndarray:
	vertex_count = len(mesh.vertices)
	polygon_count = len(mesh.polygons)
	if not polygon_count:
		return np.ones(vertex_count)
	areas = np.empty(polygon_count, dtype=np.float32)
	starts = np.empty(polygon_count, dtype=np.int32)
	totals = np.empty(polygon_count, dtype=np.int32)
	mesh.polygons.foreach_get("area", areas)
	mesh.polygons.foreach_get("loop_start", starts)
	mesh.polygons.foreach_get("loop_total", totals)
	loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
	mesh.loops.foreach_get("vertex_index", loop_verts)
	order = np.argsort(starts)
	per_loop = np.repeat(areas[order] / totals[order], totals[order])
	result = np.zeros(vertex_count)
	np.add.at(result, loop_verts, per_loop)
	if not result.any():
		return np.ones(vertex_count)
	return result


def _reference_weights(context: Context, target: Object, joined: Object) -> Reference:
	# Source weights at every target vertex, sampled from the nearest source surface.
	probe = target.copy()
	probe.data = target.data.copy()
	context.scene.collection.objects.link(probe)
	try:
		probe.vertex_groups.clear()
		transfer(joined, probe, "VGROUP_WEIGHTS", vert_mapping="POLYINTERP_NEAREST")
		return read_weights(probe.data) + ([vg.name for vg in probe.vertex_groups],)
	finally:
		mesh = probe.data
		bpy.data.objects.remove(probe)
		bpy.data.meshes.remove(mesh)


def _overlap(
	target: Object,
	reference: Reference,
	source_index: dict[str, int],
	similarity: bool = False,
) -> np.ndarray:
	"""Matrix [target group, source group] of area-weighted weight overlap, or with similarity its cosine."""
	verts, groups, weights = read_weights(target.data)
	weights = weights * _vertex_areas(target.data)[verts]
	# Vertices outside every face (dumped parts keep the whole buffer) have no area: their 0/0 cosine would be NaN.
	keep = weights > 0.0
	verts, groups, weights = verts[keep], groups[keep], weights[keep]

	ref_verts, ref_groups, ref_weights, ref_names = reference
	ref_source = np.array([source_index[name] for name in ref_names], dtype=np.int64)[
		ref_groups
	]
	keep = ref_weights > 0.0
	order = np.argsort(ref_verts[keep], kind="stable")
	ref_verts, ref_source, ref_weights = (
		ref_verts[keep][order],
		ref_source[keep][order],
		ref_weights[keep][order],
	)

	# Pair every target weight with every reference weight on the same vertex, without a dense vertex matrix.
	count = np.bincount(ref_verts, minlength=len(target.data.vertices))
	start = np.cumsum(count) - count
	repeats = count[verts]
	pick = (
		np.arange(repeats.sum())
		- np.repeat(np.cumsum(repeats) - repeats, repeats)
		+ np.repeat(start[verts], repeats)
	)
	width = len(source_index)
	flat = np.bincount(
		np.repeat(groups, repeats) * width + ref_source[pick],
		weights=np.repeat(weights, repeats) * ref_weights[pick],
		minlength=len(target.vertex_groups) * width,
	)
	matrix = flat.reshape(len(target.vertex_groups), width)
	if similarity:
		# A weak group overlaps its strong neighbour more than its own twin; the cosine finds the twin.
		areas = _vertex_areas(target.data)
		target_norm = np.sqrt(
			np.bincount(
				groups,
				weights * weights / areas[verts],
				minlength=len(target.vertex_groups),
			)
		)
		source_norm = np.sqrt(
			np.bincount(
				ref_source,
				ref_weights * ref_weights * areas[ref_verts],
				minlength=width,
			)
		)
		matrix = matrix / np.maximum(np.outer(target_norm, source_norm), 1e-30)
	return matrix


def overlaps(
	context: Context, targets: list[Object], joined: Object, similarity: bool = False
) -> tuple[list[str], dict[Object, np.ndarray]]:
	"""The source group names, and per target its [group, source group] overlap matrix."""
	source_names = [vg.name for vg in joined.vertex_groups]
	if not source_names or not is_weighted(joined):
		raise ToolError("Source meshes have no weighted vertex groups")
	source_index = {name: i for i, name in enumerate(source_names)}
	return source_names, {
		target: _overlap(
			target,
			_reference_weights(context, target, joined),
			source_index,
			similarity,
		)
		for target in targets
	}


def remap(
	context: Context,
	targets: list[Object],
	sources: list[Object],
	joined: Object | None = None,
	choose: Choose | None = None,
) -> tuple[int, list[tuple[float, str, str]]]:
	"""Rename every target group after the source group it overlaps most. Returns the renamed count and the least certain matches."""
	if joined is None:
		with joined_source(context, sources) as joined:
			return remap(context, targets, sources, joined, choose)
	source_names, matrices = overlaps(context, targets, joined)

	# Summed per name across all targets, so every piece gets the same answer for the same bone.
	totals = {}
	for target in targets:
		matrix = matrices[target]
		for vg in target.vertex_groups:
			row = matrix[vg.index]
			if row.any():
				totals[vg.name] = totals.get(vg.name, 0.0) + row
	plan = {
		name: (source_names[int(row.argmax())], float(row.max() / row.sum()))
		for name, row in totals.items()
	}
	if choose is not None:
		plan.update(choose(totals, source_names))
	for name, (match, share) in sorted(plan.items()):
		log.debug("remap %s -> %s (%.0f%%)", name, match, share * 100)

	renamed = 0
	for target in targets:
		matched = [vg for vg in target.vertex_groups if vg.name in plan]
		rename_all(matched, [plan[vg.name][0] for vg in matched])
		renamed += len(matched)
	least_certain = sorted(
		(share, name, match) for name, (match, share) in plan.items()
	)[:3]
	return renamed, least_certain
