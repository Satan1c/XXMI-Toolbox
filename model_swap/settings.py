import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, PointerProperty
from bpy.types import Object, PropertyGroup


def _is_mesh(self: PropertyGroup, obj: Object) -> bool:
	return obj.type == "MESH"


class XXMI_TOOLBOX_ObjectItem(PropertyGroup):
	object: PointerProperty(type=bpy.types.Object, poll=_is_mesh)  # type: ignore


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
