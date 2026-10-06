import bpy
import numpy as np
from bpy.types import Mesh, Object

from ..common.utils import call_on

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
