import numpy as np
from bpy.types import Mesh


def read_uvs(mesh: Mesh) -> list[tuple[str, np.ndarray]]:
	"""Each UV map's name and its (corners, 2) coordinates."""
	maps = []
	for layer in mesh.uv_layers:
		uv = np.empty(len(mesh.loops) * 2, dtype=np.float32)
		layer.data.foreach_get("uv", uv)
		maps.append((layer.name, uv.reshape(-1, 2)))
	return maps


def rebuild_uvs(mesh: Mesh, maps: list[tuple[str, np.ndarray | None]]) -> None:
	"""Replace the UV maps with these, in this order, the first one rendered;
	None leaves a map's corners at the origin. Blender can't reorder UV maps, so they're made anew."""
	layers = mesh.uv_layers
	while len(layers):
		layers.remove(layers[0])
	for name, uv in maps:
		layer = layers.new(name=name)
		if uv is not None:
			layer.data.foreach_set("uv", np.ascontiguousarray(uv, np.float32).ravel())
	if len(layers):
		layers.active_index = 0
		layers[0].active_render = True


def uv_use(mesh: Mesh, uv: np.ndarray) -> float:
	"""Share of faces the UV map gives any area."""
	count = len(mesh.polygons)
	if not count:
		return 0.0
	starts = np.empty(count, dtype=np.int32)
	totals = np.empty(count, dtype=np.int32)
	mesh.polygons.foreach_get("loop_start", starts)
	mesh.polygons.foreach_get("loop_total", totals)

	area = np.zeros(count)
	for k in range(1, int(totals.max()) - 1):
		fan = totals > k + 1
		a, b, c = uv[starts[fan]], uv[starts[fan] + k], uv[starts[fan] + k + 1]
		area[fan] += np.abs(
			(b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
			- (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
		)
	return float((area > 1e-9).mean())
