from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import PropertyGroup

MERGE_MODES = [
	(
		"ALL",
		"Same ID",
		"Merge groups sharing an ID (`7`, `7.1`, `7.head.001`) or a name differing only by Blender's .001 suffix",
	),
	(
		"ACTIVE",
		"Into Active",
		"Merge only groups sharing the active group's ID or name",
	),
	("LIST", "List", "Merge only the listed IDs or names"),
	("RANGE", "Range", "Merge only IDs within the range"),
]


class XXMI_TOOLBOX_VertexGroupSettings(PropertyGroup):
	merge_mode: EnumProperty(name="Merge Mode", items=MERGE_MODES, default="ALL")  # type: ignore
	merge_list: StringProperty(
		name="Groups", description="Comma-separated IDs or names, e.g. `3, 7, hair`"
	)  # type: ignore
	merge_first: IntProperty(name="From", min=0, default=0)  # type: ignore
	merge_last: IntProperty(name="To", min=0, default=0)  # type: ignore
	fill_largest: IntProperty(
		name="Largest",
		description="Fill up to at least this ID, even past the highest existing one (0 = up to the highest existing ID)",
		min=0,
		default=0,
	)  # type: ignore
