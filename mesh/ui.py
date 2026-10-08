from bpy.types import Context, UILayout

from . import operators


def draw_mesh(layout: UILayout, context: Context) -> None:
	column = layout.column(align=True)
	column.operator(
		operators.XXMI_TOOLBOX_OT_separate_by_material.bl_idname, icon="MATERIAL"
	)
	column.operator(operators.XXMI_TOOLBOX_OT_clean_uv_names.bl_idname, icon="UV")
	column.operator(
		operators.XXMI_TOOLBOX_OT_reset_vertex_colors.bl_idname, icon="COLOR"
	)
	column.operator(
		operators.XXMI_TOOLBOX_OT_convert_vertex_colors.bl_idname, icon="COLOR"
	)


	column = layout.column(align=True)
	column.operator(
		operators.XXMI_TOOLBOX_OT_apply_modifiers_with_shape_keys.bl_idname,
		icon="MODIFIER",
	)
	column.operator(
		operators.XXMI_TOOLBOX_OT_name_shape_keys_for_export.bl_idname,
		icon="SHAPEKEY_DATA",
	)

	column = layout.column(align=True)
	column.operator(
		operators.XXMI_TOOLBOX_OT_create_merged_object.bl_idname, icon="SCULPTMODE_HLT"
	)
	column.operator(
		operators.XXMI_TOOLBOX_OT_apply_merged_sculpt.bl_idname, text="Apply Sculpt"
	).shape_keys = False
	column.operator(
		operators.XXMI_TOOLBOX_OT_apply_merged_sculpt.bl_idname,
		text="Apply Sculpt + Shape Keys",
	).shape_keys = True
