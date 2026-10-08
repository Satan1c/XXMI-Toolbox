from ..common.operators import register_classes_factory
from . import operators, settings

classes = (
	settings.XXMI_TOOLBOX_ObjectItem,
	settings.XXMI_TOOLBOX_UVSlot,
	settings.XXMI_TOOLBOX_ModelSwapSettings,
	operators.XXMI_TOOLBOX_OT_remap_vertex_groups,
	operators.XXMI_TOOLBOX_OT_model_swap,
	operators.XXMI_TOOLBOX_OT_copy_custom_properties,
	operators.XXMI_TOOLBOX_OT_list_add_selected,
	operators.XXMI_TOOLBOX_OT_list_remove,
	operators.XXMI_TOOLBOX_OT_list_clear,
)

register, unregister = register_classes_factory(classes)
