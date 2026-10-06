import bpy

from . import operators, settings

classes = (
	settings.XXMI_TOOLBOX_ArmatureSettings,
	operators.XXMI_TOOLBOX_OT_attach_to_game_armature,
	operators.XXMI_TOOLBOX_OT_clean_up_game_model,
)

register, unregister = bpy.utils.register_classes_factory(classes)
