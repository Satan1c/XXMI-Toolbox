from bpy.types import Context, Object

from ..common.transfer import joined_source, transfer
from ..common.utils import ToolError, rename_all
from ..vertex_groups import cleanup, remap
from ..vertex_groups.ids import sort_vertex_groups
from ..vertex_groups.weights import (
	is_weighted,
	limit_and_normalize,
	unweighted_vertex_count,
)


def swap_uvs(source: Object, target: Object) -> int:
	names = [layer.name for layer in source.data.uv_layers]
	layers = target.data.uv_layers
	while len(layers) > len(names):
		layers.remove(layers[len(layers) - 1])
	rename_all(list(layers), names[: len(layers)])
	return len(names) - len(layers)


def swap_colors(source: Object, target: Object) -> None:
	source_colors = source.data.color_attributes
	colors = target.data.color_attributes
	for name in [a.name for a in colors]:
		attribute = colors[name]
		match = source_colors.get(name)
		if match is None or (match.domain, match.data_type) != (
			attribute.domain,
			attribute.data_type,
		):
			colors.remove(attribute)
	domains = {a.domain for a in source_colors}
	if "CORNER" in domains:
		transfer(source, target, "COLOR_CORNER", loop_mapping="POLYINTERP_NEAREST")
	if "POINT" in domains:
		transfer(source, target, "COLOR_VERTEX", vert_mapping="POLYINTERP_NEAREST")


def _cleanup_weights(target: Object) -> None:
	cleanup.remove_unused(target)
	# Merge before limiting: a bone split across "3" and "3.001" could otherwise lose both halves.
	cleanup.merge(target, lambda key: True)
	limit_and_normalize(target)
	cleanup.remove_unused(target)
	cleanup.fill_gaps(target)
	sort_vertex_groups(target)


def _remap_weighted(
	context: Context,
	targets: list[Object],
	sources: list[Object],
	joined: Object,
	messages: list[str],
) -> list[Object]:
	"""Rename the weighted targets' groups after the source's,
	in one pass so every piece gets the same name for the same bone. Returns the targets remapped."""
	remapped = [target for target in targets if is_weighted(target)]
	if not remapped:
		return []
	renamed, least_certain = remap.remap(context, remapped, sources, joined)
	messages.append(f"Remapped {renamed} vertex groups on {len(remapped)} meshes")
	if least_certain:
		messages.append(
			"Least certain: "
			+ ", ".join(f"{a} -> {b} ({share:.0%})" for share, a, b in least_certain)
		)
	return remapped


def _swap_weights(
	target: Object, joined: Object, remapped: list[Object], messages: list[str]
) -> None:
	if target not in remapped:
		target.vertex_groups.clear()
		transfer(joined, target, "VGROUP_WEIGHTS", vert_mapping="POLYINTERP_NEAREST")
	_cleanup_weights(target)
	unweighted = unweighted_vertex_count(target)
	if unweighted:
		messages.append(
			f"WARNING: {target.name}: {unweighted} vertices have no weights"
		)


def model_swap(
	context: Context,
	sources: list[Object],
	targets: list[Object],
	uvs: bool = True,
	colors: bool = True,
	weights: bool = True,
	keep_target_weights: bool = True,
) -> list[str]:
	messages = []
	with joined_source(
		context, sources if colors or weights else sources[:1]
	) as joined:
		remapped = []
		if weights and keep_target_weights:
			remapped = _remap_weighted(context, targets, sources, joined, messages)

		for target in targets:
			try:
				if uvs:
					missing = swap_uvs(sources[0], target)
					if missing > 0:
						messages.append(
							f"WARNING: {target.name} has {missing} fewer UV maps than the source"
						)
				if colors:
					swap_colors(joined, target)
				if weights:
					_swap_weights(target, joined, remapped, messages)
			except ToolError as e:
				messages.append(f"ERROR: {e}")
	return messages
