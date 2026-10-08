from collections.abc import Iterable

import numpy as np
from bpy.types import Object
from mathutils import Vector

from ..vertex_groups.weights import Weights, read_weights

# What a bone moves: the points of its group and their weights.
Influence = tuple[np.ndarray, np.ndarray]


def group_influence(
	obj: Object, co: np.ndarray, read: Weights | None = None
) -> dict[str, Influence]:
	"""{group name: its weighted vertices, at the given positions, and their weights}, from the mesh's weights if
	they're read already."""
	verts, groups, weights = read if read is not None else read_weights(obj.data)
	names = [vg.name for vg in obj.vertex_groups]
	found = {}
	for group in np.unique(groups):
		pick = (groups == group) & (weights > 0.0)
		if pick.any():
			found[names[int(group)]] = (co[verts[pick]], weights[pick])
	return found


def merged(parts: Iterable[tuple[str, Influence]]) -> dict[str, Influence]:
	"""The influences found under one name on several meshes, as one."""
	found = {}
	for name, influence in parts:
		found.setdefault(name, []).append(influence)
	return {
		name: (
			np.concatenate([points for points, _ in influences]),
			np.concatenate([weights for _, weights in influences]),
		)
		for name, influences in found.items()
	}


def _core(influence: Influence) -> np.ndarray:
	"""The points a bone weighs at least half as much as its strongest."""
	points, weights = influence
	return points[weights >= weights.max() * 0.5]


def reach(head: Vector, influence: Influence) -> Vector:
	"""Where what a bone moves mostly ends: the far quarter of its core.
	A hem bone moves cloth at its root too, but it should point at the charm hanging off it."""
	core = _core(influence)
	distance = np.linalg.norm(core - np.array(head), axis=1)
	return Vector(core[distance >= np.percentile(distance, 75)].mean(0))


def elongation(influence: Influence) -> float:
	"""How many times longer than wide what a bone moves is."""
	core = _core(influence)
	if len(core) < 3:
		return 0.0
	spread = np.sort(np.linalg.eigvalsh(np.cov((core - core.mean(0)).T)))[::-1]
	return float(np.sqrt(spread[0] / max(spread[1], 1e-12)))


def extent(head: Vector, direction: Vector, influence: Influence) -> float:
	"""How far along the direction what a bone moves mostly reaches."""
	along = (_core(influence) - np.array(head)) @ np.array(direction)
	return float(np.percentile(along, 90))
