from bpy.types import Mesh

from ...common.utils import rename_all
from ...common.uvs import read_uvs, rebuild_uvs, uv_use

# A UV map whose faces are this rarely more than a point is junk a ripper or an importer left behind.
_USED_UV = 0.1


def tidy_uvs(mesh: Mesh, drop_empty: bool, rename: bool) -> int:
	"""Main UV map first, maps barely covering any faces dropped, the rest named UV0, UV1...
	Returns how many were dropped."""
	layers = mesh.uv_layers
	if not len(layers):
		return 0
	maps = read_uvs(mesh)
	main = next((i for i, layer in enumerate(layers) if layer.active_render), 0)

	order = [main] + [i for i in range(len(maps)) if i != main]
	kept = [
		i
		for i in order
		if i == main or not drop_empty or uv_use(mesh, maps[i][1]) >= _USED_UV
	]
	names = [f"UV{n}" if rename else maps[i][0] for n, i in enumerate(kept)]

	if kept == list(range(len(maps))):
		rename_all(list(layers), names)
	else:
		rebuild_uvs(mesh, [(name, maps[i][1]) for name, i in zip(names, kept)])
	return len(maps) - len(kept)
