from bpy.types import Context, UILayout

from . import operators


def draw_armature(layout: UILayout, context: Context) -> None:
	row = layout.row()
	row.scale_y = 1.3
	row.operator(
		operators.XXMI_TOOLBOX_OT_attach_to_game_armature.bl_idname,
		icon="ARMATURE_DATA",
	)
	layout.operator(
		operators.XXMI_TOOLBOX_OT_clean_up_game_model.bl_idname, icon="TRASH"
	)
