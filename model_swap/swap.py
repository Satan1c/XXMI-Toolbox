import re

from bpy.types import Context, Object

from ..common.transfer import joined_source, transfer, transfer_uvs
from ..common.utils import ToolError, rename_all
from ..common.uvs import read_uvs, rebuild_uvs
from ..vertex_groups import cleanup, remap
from ..vertex_groups.ids import sort_vertex_groups
from ..vertex_groups.weights import (
	is_weighted,
	limit_and_normalize,
	unweighted_vertex_count,
)
from .uv_fill import UVFills

_NUMBERED = re.compile(r"UV(\d*)")


def _numbered(target: Object) -> dict[int, int] | None:
	"""{number: index} when every UV map of the target is named UV<n>, else None.
	Plain UV is 0; numbering from 1 counts from 1."""
	numbers = {}
	for index, layer in enumerate(target.data.uv_layers):
		match = _NUMBERED.fullmatch(layer.name)
		if match is None:
			return None
		numbers[int(match.group(1) or 0)] = index
	if numbers and 0 not in numbers and min(numbers) == 1:
		numbers = {number - 1: index for number, index in numbers.items()}
	return numbers or None


# Fills that make a map from the target itself, not from one of its maps or the dump's.
_MADE = ("EMPTY", "PROJECTION", "BACKFACES")


def _uv_plan(
	names: list[str],
	target: Object,
	slots: list[int] | None,
	modes: list[str] | None,
	in_dump: set[str],
) -> list[int | str | None]:
	"""Per source map, the target map that fills it, a made fill, "DUMP", or None when nothing can."""
	count = len(target.data.uv_layers)
	numbered = _numbered(target)
	plan = []
	for k, name in enumerate(names):
		mode = modes[k] if modes and k < len(modes) else "AUTO"
		if mode in _MADE:
			plan.append(mode)
			continue

		if mode == "CUSTOM":
			index = slots[k] - 1 if slots and k < len(slots) else k
			index = index if 0 <= index < count else None
		elif mode == "DUMP":
			index = None
		elif numbered is not None:
			index = numbered.get(k)
		else:
			index = k if k < count else None
		plan.append(
			index if index is not None else ("DUMP" if name in in_dump else None)
		)
	return plan


def swap_uvs(
	source: Object,
	target: Object,
	fills: UVFills,
	slots: list[int] | None = None,
	modes: list[str] | None = None,
	in_dump: set[str] = frozenset(),
) -> tuple[int, set[str]]:
	"""Give the target the source's UV maps, each filled per its mode:
	AUTO by the target's UV<n> names (in order when they aren't all named so), the dump filling the rest;
	CUSTOM from the target map at its slot (1-based); DUMP from the dump;
	EMPTY, PROJECTION and BACKFACES made by the fills.
	Returns how many maps nothing could fill, and which are left for the dump."""
	names = [layer.name for layer in source.data.uv_layers]
	plan = _uv_plan(names, target, slots, modes, in_dump)
	dumped = {name for name, step in zip(names, plan) if step == "DUMP"}
	missing = sum(step is None for step in plan)

	layers = target.data.uv_layers
	count = len(layers)
	in_place = all(step == k for k, step in enumerate(plan[:count]))
	if in_place and all(step is None for step in plan[count:]):
		while len(layers) > len(names):
			layers.remove(layers[len(layers) - 1])
		rename_all(list(layers), names[: len(layers)])
		return missing, dumped

	# Out of order (a model whose backface UVs sit second, where the game wants them fourth), made,
	# or left for the dump: the maps are rebuilt.
	maps = [uv for _, uv in read_uvs(target.data)]
	main = next(
		(maps[i] for i, layer in enumerate(layers) if layer.active_render), None
	)
	made = {
		"EMPTY": lambda name: fills.empty(target, name),
		"PROJECTION": lambda name: fills.projection(target, name),
		"BACKFACES": lambda name: fills.backfaces(target, name, main),
		"DUMP": lambda name: None,
	}
	rebuild_uvs(
		target.data,
		[
			(name, maps[step] if isinstance(step, int) else made[step](name))
			for name, step in zip(names, plan)
			if step is not None
		],
	)
	return missing, dumped


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
	choose: remap.Choose | None,
	messages: list[str],
) -> list[Object]:
	"""Rename the weighted targets' groups after the source's,
	in one pass so every piece gets the same name for the same bone. Returns the targets remapped."""
	remapped = [target for target in targets if is_weighted(target)]
	if not remapped:
		return []
	renamed, least_certain = remap.remap(context, remapped, sources, joined, choose)
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
	uv_slots: list[int] | None = None,
	uv_modes: list[str] | None = None,
	remap_choose: remap.Choose | None = None,
) -> list[str]:
	messages = []
	# UV maps a target hasn't got come from the dump, so every source piece goes into it.
	with joined_source(
		context, sources if colors or weights or uvs else sources[:1]
	) as joined:
		remapped = []
		if weights and keep_target_weights:
			remapped = _remap_weighted(
				context, targets, sources, joined, remap_choose, messages
			)

		in_dump = {layer.name for layer in joined.data.uv_layers}
		fills = UVFills(sources[0], targets)
		filled = {}
		for target in targets:
			try:
				if uvs:
					missing, dumped = swap_uvs(
						sources[0], target, fills, uv_slots, uv_modes, in_dump
					)
					if dumped:
						filled[target] = dumped
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
		transfer_uvs(joined, filled)
	return messages
