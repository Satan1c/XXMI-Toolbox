import math
from functools import cached_property

import numpy as np
from bpy.types import Mesh, Object
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..common.log import log
from ..common.utils import world_positions

# Rays cast from behind a face to see whether its back can be seen: straight back and tilted this far all round.
_TILT = math.radians(60)
_RAYS = 6


def _corner_vertices(mesh: Mesh) -> np.ndarray:
	index = np.empty(len(mesh.loops), dtype=np.int32)
	mesh.loops.foreach_get("vertex_index", index)
	return index


def _back_directions(normal: Vector) -> list[Vector]:
	side = normal.orthogonal().normalized()
	up = normal.cross(side)
	back = [-normal]
	for i in range(_RAYS):
		turn = 2.0 * math.pi * i / _RAYS
		around = side * math.cos(turn) + up * math.sin(turn)
		back.append(-normal * math.cos(_TILT) + around * math.sin(_TILT))
	return back


def inside_shows(obj: Object) -> np.ndarray:
	"""Per face, whether its back can be seen from outside the mesh:
	a ray from behind it gets out (a skirt's or a sleeve's inside),
	rather than ending on the mesh's other walls (a closed body's)."""
	mesh = obj.data
	co = world_positions(obj)
	bvh = BVHTree.FromPolygons(co.tolist(), [tuple(p.vertices) for p in mesh.polygons])
	size = float(np.linalg.norm(co.max(0) - co.min(0))) if len(co) else 1.0
	matrix = obj.matrix_world
	normals = matrix.to_3x3().inverted().transposed()

	shows = np.zeros(len(mesh.polygons), dtype=bool)
	for i, polygon in enumerate(mesh.polygons):
		normal = (normals @ polygon.normal).normalized()
		start = matrix @ polygon.center - normal * size * 1e-4
		shows[i] = any(
			bvh.ray_cast(start, direction)[0] is None
			for direction in _back_directions(normal)
		)
	return shows


class UVFills:
	"""What fills a source UV map that no target map does, in game terms:
	XXMI Tools may flip V on export, as the dump says per map."""

	def __init__(self, source: Object, targets: list[Object]) -> None:
		self.source = source
		self.targets = targets

	def empty(self, target: Object, name: str) -> np.ndarray:
		"""Zeros at every corner."""
		return self._to_blender(np.zeros((len(target.data.loops), 2)), name)

	def projection(self, target: Object, name: str) -> np.ndarray:
		"""Straight from the front, one scale for every target:
		as tall as the map, centred on the model's middle, squashed further only if it would be wider."""
		scale, floor = self._frame
		co = world_positions(target)[_corner_vertices(target.data)]
		uv = np.stack([0.5 + co[:, 0] * scale, (co[:, 2] - floor) * scale], 1)
		return self._to_blender(uv, name)

	def backfaces(
		self, target: Object, name: str, main: np.ndarray | None
	) -> np.ndarray:
		"""The main map where the target's inside can be seen, zeros where it can't."""
		uv = self.empty(target, name)
		if main is None:
			return uv
		mesh = target.data
		starts = np.empty(len(mesh.polygons), dtype=np.int32)
		totals = np.empty(len(mesh.polygons), dtype=np.int32)
		mesh.polygons.foreach_get("loop_start", starts)
		mesh.polygons.foreach_get("loop_total", totals)
		shows = inside_shows(target)
		log.debug("%s: inside seen on %.0f%% of faces", target.name, shows.mean() * 100)
		corners = np.repeat(shows, totals)
		order = np.concatenate([np.arange(s, s + t) for s, t in zip(starts, totals)])
		uv[order[corners]] = main[order[corners]]
		return uv

	@cached_property
	def _frame(self) -> tuple[float, float]:
		"""The projection's scale and the floor it starts from."""
		co = np.concatenate([world_positions(obj) for obj in self.targets])
		height = float(co[:, 2].max() - co[:, 2].min()) or 1.0
		half_width = float(np.abs(co[:, 0]).max()) or 1.0
		scale, floor = min(1.0 / height, 0.5 / half_width), float(co[:, 2].min())
		log.debug("projection: %.4f per unit, from %.4f up", scale, floor)
		return scale, floor

	def _to_blender(self, uv: np.ndarray, name: str) -> np.ndarray:
		if self._flipped(name):
			uv[:, 1] = 1.0 - uv[:, 1]
		return uv

	def _flipped(self, name: str) -> bool:
		settings = self.source.get(f"3DMigoto:{name}")
		return bool(settings is not None and settings.get("flip_v", False))
