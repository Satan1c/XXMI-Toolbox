from ..common.operators import register_classes_factory
from . import operators

classes = (
	operators.XXMI_TOOLBOX_OT_separate_by_material,
	operators.XXMI_TOOLBOX_OT_clean_uv_names,
	operators.XXMI_TOOLBOX_OT_reset_vertex_colors,
	operators.XXMI_TOOLBOX_OT_convert_vertex_colors,
	operators.XXMI_TOOLBOX_ModifierItem,
	operators.XXMI_TOOLBOX_OT_apply_modifiers_with_shape_keys,
	operators.XXMI_TOOLBOX_OT_name_shape_keys_for_export,
	operators.XXMI_TOOLBOX_OT_create_merged_object,
	operators.XXMI_TOOLBOX_OT_apply_merged_sculpt,
)

register, unregister = register_classes_factory(classes)
