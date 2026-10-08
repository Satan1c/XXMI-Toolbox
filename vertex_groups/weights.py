import bpy
import numpy as np
from bpy.types import Mesh, Object
from mathutils.kdtree import KDTree

from ..common.utils import call_on, positions

DX11_MAX_INFLUENCES = 4
# Vertex index, group index and weight of every assignment.
Weights = tuple[np.ndarray, np.ndarray, np.ndarray]


def read_weights(mesh: Mesh) -> Weights:
	verts, groups, weights = [], [], []
	for vert in mesh.vertices:
		for elem in vert.groups:
			verts.append(vert.index)
			groups.append(elem.group)
			weights.append(elem.weight)
	return (
		np.array(verts, dtype=np.int64),
		np.array(groups, dtype=np.int64),
		np.array(weights, dtype=np.float64),
	)


def is_weighted(obj: Object) -> bool:
	_, _, weights = read_weights(obj.data)
	return bool((weights > 0.0).any())


def unweighted_vertex_count(obj: Object) -> int:
	verts, _, weights = read_weights(obj.data)
	weighted = np.zeros(len(obj.data.vertices), dtype=bool)
	weighted[verts[weights > 0.0]] = True
	return int((~weighted).sum())


def _nearest_of(co: np.ndarray, sources: np.ndarray) -> KDTree:
	tree = KDTree(len(sources))
	for i in sources:
		tree.insert(co[i], int(i))
	tree.balance()
	return tree


def fill_missing(obj: Object) -> int:
	"""Give each vertex without any weight the weights of the nearest weighted vertex of the mesh;
	returns how many were filled. Unweighted vertices don't follow the skeleton in game."""
	mesh = obj.data
	count = len(mesh.vertices)
	verts, groups, weights = read_weights(mesh)
	keep = weights > 0.0
	verts, groups, weights = verts[keep], groups[keep], weights[keep]
	weighted = np.zeros(count, dtype=bool)
	weighted[verts] = True
	missing = np.flatnonzero(~weighted)
	if not len(missing) or not weighted.any():
		return 0

	co = positions(mesh)
	tree = _nearest_of(co, np.flatnonzero(weighted))
	# Each vertex's weights as one run of the sorted lists.
	order = np.argsort(verts, kind="stable")
	verts, groups, weights = verts[order], groups[order], weights[order]
	start = np.searchsorted(verts, np.arange(count))
	end = np.searchsorted(verts, np.arange(count), side="right")

	vertex_groups = obj.vertex_groups
	for i in missing:
		_, nearest, _ = tree.find(co[i])
		for k in range(start[nearest], end[nearest]):
			vertex_groups[int(groups[k])].add([int(i)], float(weights[k]), "REPLACE")
	return len(missing)


def limit_and_normalize(obj: Object, limit: int = DX11_MAX_INFLUENCES) -> None:
	if not obj.vertex_groups:
		return
	call_on(
		obj,
		bpy.ops.object.vertex_group_limit_total,
		group_select_mode="ALL",
		limit=limit,
	)
	call_on(
		obj,
		bpy.ops.object.vertex_group_normalize_all,
		group_select_mode="ALL",
		lock_active=False,
	)
