from bpy.types import Context, Menu, UILayout

from . import operators


def draw_vertex_groups(layout: UILayout, context: Context) -> None:
	settings = context.scene.xxmi_toolbox.vertex_groups

	column = layout.column(align=True)
	column.prop(settings, "merge_mode", text="")
	if settings.merge_mode == "LIST":
		column.prop(settings, "merge_list", text="")
	elif settings.merge_mode == "RANGE":
		row = column.row(align=True)
		row.prop(settings, "merge_first")
		row.prop(settings, "merge_last")
	op = column.operator(
		operators.XXMI_TOOLBOX_OT_merge_vertex_groups.bl_idname, icon="AUTOMERGE_ON"
	)
	op.mode = settings.merge_mode
	op.names = settings.merge_list
	op.first = settings.merge_first
	op.last = settings.merge_last

	column = layout.column(align=True)
	row = column.row(align=True)
	row.operator(
		operators.XXMI_TOOLBOX_OT_fill_vertex_group_gaps.bl_idname,
		text="Fill Gaps",
		icon="ADD",
	).largest = settings.fill_largest
	row.prop(settings, "fill_largest")
	column.operator(
		operators.XXMI_TOOLBOX_OT_fill_missing_weights.bl_idname,
		text="Fill Missing Weights",
		icon="MOD_VERTEX_WEIGHT",
	)
	column.operator(
		operators.XXMI_TOOLBOX_OT_remove_unused_vertex_groups.bl_idname,
		text="Remove Unused",
		icon="X",
	)
	column.operator(
		operators.XXMI_TOOLBOX_OT_remove_all_vertex_groups.bl_idname,
		text="Remove All",
		icon="CANCEL",
	)


def draw_vertex_group_menu(self: Menu, context: Context) -> None:
	layout = self.layout
	layout.separator()
	layout.operator(
		operators.XXMI_TOOLBOX_OT_merge_vertex_groups.bl_idname,
		text="Merge Same ID",
		icon="AUTOMERGE_ON",
	).mode = "ALL"
	layout.operator(
		operators.XXMI_TOOLBOX_OT_merge_vertex_groups.bl_idname,
		text="Merge into Active",
	).mode = "ACTIVE"
	layout.operator(
		operators.XXMI_TOOLBOX_OT_fill_vertex_group_gaps.bl_idname, text="Fill Gaps"
	)
	layout.operator(
		operators.XXMI_TOOLBOX_OT_fill_missing_weights.bl_idname,
		text="Fill Missing Weights",
	)
	layout.operator(
		operators.XXMI_TOOLBOX_OT_remove_unused_vertex_groups.bl_idname,
		text="Remove Unused",
	)


MENUS = ("MESH_MT_vertex_group_context_menu", "VIEW3D_MT_vertex_group")
