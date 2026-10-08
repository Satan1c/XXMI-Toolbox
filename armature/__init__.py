import bpy

from . import operators, settings

classes = (
	settings.XXMI_TOOLBOX_ArmatureSettings,
	operators.XXMI_TOOLBOX_OT_attach_to_game_armature,
	operators.XXMI_TOOLBOX_OT_clean_up_game_model,
	operators.XXMI_TOOLBOX_OT_save_game_armature,
	operators.XXMI_TOOLBOX_OT_add_saved,
)

register, unregister = bpy.utils.register_classes_factory(classes)
