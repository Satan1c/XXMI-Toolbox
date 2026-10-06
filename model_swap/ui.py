from bpy.types import Context, UILayout, bpy_prop_collection

from . import operators


def _draw_mesh_list(
	layout: UILayout, label: str, items: bpy_prop_collection, side: str
) -> None:
	box = layout.box()
	box.label(text=label)
	column = box.column(align=True)
	for i, item in enumerate(items):
		row = column.row(align=True)
		row.prop(item, "object", text="")
		op = row.operator(
			operators.XXMI_TOOLBOX_OT_list_remove.bl_idname, text="", icon="REMOVE"
		)
		op.side = side
		op.index = i
	row = column.row(align=True)
	row.operator(
		operators.XXMI_TOOLBOX_OT_list_add_selected.bl_idname,
		text="Add Selected",
		icon="ADD",
	).side = side
	if len(items):
		row.operator(
			operators.XXMI_TOOLBOX_OT_list_clear.bl_idname, text="", icon="TRASH"
		).side = side


def draw_model_swap(layout: UILayout, context: Context) -> None:
	settings = context.scene.xxmi_toolbox.model_swap

	_draw_mesh_list(layout, "Source (format from)", settings.sources, "SOURCE")
	_draw_mesh_list(layout, "Target (applied to)", settings.targets, "TARGET")

	row = layout.row(align=True)
	row.prop(settings, "swap_uvs", toggle=True)
	row.prop(settings, "swap_colors", toggle=True)
	row.prop(settings, "swap_weights", text="VGs", toggle=True)
	if settings.swap_weights:
		layout.row(align=True).prop(settings, "swap_weights_mode", expand=True)
	row = layout.row()
	row.scale_y = 1.5
	row.operator(operators.XXMI_TOOLBOX_OT_model_swap.bl_idname, icon="FILE_REFRESH")

	column = layout.column(align=True)
	column.operator(
		operators.XXMI_TOOLBOX_OT_remap_vertex_groups.bl_idname, icon="GROUP_VERTEX"
	)
	column.operator(
		operators.XXMI_TOOLBOX_OT_copy_custom_properties.bl_idname, icon="PROPERTIES"
	)
