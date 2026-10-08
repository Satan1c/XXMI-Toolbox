import bpy
from bpy.props import (
	BoolProperty,
	CollectionProperty,
	EnumProperty,
	IntProperty,
	PointerProperty,
	StringProperty,
)
from bpy.types import Object, PropertyGroup


def _is_mesh(self: PropertyGroup, obj: Object) -> bool:
	return obj.type == "MESH"


class XXMI_TOOLBOX_ObjectItem(PropertyGroup):
	object: PointerProperty(type=bpy.types.Object, poll=_is_mesh)  # type: ignore


class XXMI_TOOLBOX_UVSlot(PropertyGroup):
	name: StringProperty(name="Source UV")  # type: ignore
	fill: EnumProperty(
		name="Fill",
		items=[
			(
				"AUTO",
				"Auto",
				"By each target's UV<n> names (UV or UV0 for the first map; numbering from 1 works too), the dump "
				"filling maps a target hasn't got. Targets whose maps aren't all named UV<n> go in order",
			),
			(
				"CUSTOM",
				"Custom UV",
				"Fill it from one of each target's own UV maps",
			),
			(
				"DUMP",
				"From Dump",
				"Take the dump's map of this name, each target corner from the nearest dump face: for the game's own "
				"effect maps (outlines, projection, decals) a custom model hasn't got",
			),
			(
				"EMPTY",
				"Empty",
				"Zeros at every corner, for a map the game reads but this model has no use for",
			),
			(
				"PROJECTION",
				"Projection",
				"Projected straight from the front at one scale for every target: as tall as the map, centred on the "
				"model's middle, squashed further only if it would be wider",
			),
			(
				"BACKFACES",
				"Backfaces",
				"Each target's main map where its inside can be seen (a skirt's or a sleeve's), zeros where it can't",
			),
		],
		default="AUTO",
	)  # type: ignore
	slot: IntProperty(
		name="Target UV",
		min=1,
		max=8,
		default=1,
		description="Which of each target's UV maps, counting from 1, fills this one",
	)  # type: ignore


class XXMI_TOOLBOX_ModelSwapSettings(PropertyGroup):
	sources: CollectionProperty(
		type=XXMI_TOOLBOX_ObjectItem,
		description="Meshes the format is taken from: UV names, colors and vertex group names",
	)  # type: ignore
	targets: CollectionProperty(
		type=XXMI_TOOLBOX_ObjectItem,
		description="Meshes the source format is applied to",
	)  # type: ignore

	swap_uvs: BoolProperty(
		name="UV Names",
		default=True,
		description="Rename target UV maps in order to the source names and remove extra ones",
	)  # type: ignore
	swap_colors: BoolProperty(
		name="Colors",
		default=True,
		description="Overwrite target color attributes from the source and remove ones the source doesn't have",
	)  # type: ignore
	uv_slots: CollectionProperty(type=XXMI_TOOLBOX_UVSlot)  # type: ignore
	swap_weights: BoolProperty(
		name="Vertex Groups",
		default=True,
		description="Match target vertex groups to the source, then clean up for export",
	)  # type: ignore
	swap_weights_mode: EnumProperty(
		name="Weighted Targets",
		items=[
			(
				"REMAP",
				"Keep Weights",
				"Keep the target's own weights and only rename its groups after the source groups they overlap most",
			),
			(
				"TRANSFER",
				"Copy Weights",
				"Replace the target's weights with the source weights from the nearest source surface",
			),
		],
		default="REMAP",
		description="What to do with targets that already have weights; unweighted targets always get the source weights",
	)  # type: ignore
