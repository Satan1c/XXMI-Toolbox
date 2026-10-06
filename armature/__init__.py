import bpy

from . import operators

classes = (
	operators.XXMI_TOOLBOX_OT_attach_to_game_armature,
	operators.XXMI_TOOLBOX_OT_clean_up_game_model,
)

register, unregister = bpy.utils.register_classes_factory(classes)
