from bpy.types import Context, UILayout

from . import operators


def draw_armature(layout: UILayout, context: Context) -> None:
	row = layout.row()
	row.scale_y = 1.3
	row.operator(
		operators.XXMI_TOOLBOX_OT_attach_to_game_armature.bl_idname,
		icon="ARMATURE_DATA",
	)
	settings = context.scene.xxmi_toolbox.armature
	column = layout.column(align=True)
	op = column.operator(
		operators.XXMI_TOOLBOX_OT_clean_up_game_model.bl_idname, icon="TRASH"
	)
	op.gather_ids = settings.gather_ids
	op.connect_bones = settings.connect_bones
	row = column.row(align=True)
	row.prop(settings, "gather_ids", toggle=True)
	row.prop(settings, "connect_bones", toggle=True)
	column = layout.column(align=True)
	column.operator(
		operators.XXMI_TOOLBOX_OT_save_game_armature.bl_idname, icon="EXPORT"
	)
	column.operator(
		operators.XXMI_TOOLBOX_OT_add_saved.bl_idname, text="Add Saved", icon="IMPORT"
	)
