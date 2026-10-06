import re

import bpy
from bpy.types import Object

from ..common.utils import ToolError, call_on, rename_all

_leading_id = re.compile(r"^\s*(\d+)")
dup_suffix = re.compile(r"\.\d{3}$")
# ("id", 7) for every group addressing bone 7, ("name", "hair") for a name-only group.
MergeKey = tuple[str, int | str]


def vg_id(name: str) -> int | None:
	match = _leading_id.match(name)
	return int(match.group(1)) if match else None


def strip_dup_suffix(name: str) -> str:
	while dup_suffix.search(name):
		name = dup_suffix.sub("", name, count=1)
	return name


def merge_key(name: str) -> MergeKey:
	# "0.head", "0.head.001" and "0.neck" all address bone 0; name-only groups merge only with their Blender duplicates.
	group_id = vg_id(name)
	if group_id is not None:
		return ("id", group_id)
	return ("name", strip_dup_suffix(name))


def shift_ids(obj: Object, delta: int) -> int:
	"""Add delta to every group's leading ID, keeping its label; groups without an ID are left alone."""
	groups = [vg for vg in obj.vertex_groups if vg_id(vg.name) is not None]
	names = []
	for vg in groups:
		group_id = vg_id(vg.name) + delta
		if group_id < 0:
			raise ToolError(f"{obj.name}: `{vg.name}` would get a negative ID")
		names.append(_leading_id.sub(str(group_id), vg.name, count=1))
	rename_all(groups, names)
	return len(groups)


def sort_vertex_groups(obj: Object) -> None:
	if obj.vertex_groups:
		call_on(obj, bpy.ops.object.vertex_group_sort, sort_type="NAME")
