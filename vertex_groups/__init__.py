import bpy

from . import operators, settings, ui

classes = (
	settings.XXMI_TOOLBOX_VertexGroupSettings,
	operators.XXMI_TOOLBOX_OT_merge_vertex_groups,
	operators.XXMI_TOOLBOX_OT_fill_vertex_group_gaps,
	operators.XXMI_TOOLBOX_OT_remove_unused_vertex_groups,
	operators.XXMI_TOOLBOX_OT_remove_all_vertex_groups,
)


def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	for menu in ui.MENUS:
		getattr(bpy.types, menu).append(ui.draw_vertex_group_menu)


def unregister():
	for menu in ui.MENUS:
		getattr(bpy.types, menu).remove(ui.draw_vertex_group_menu)
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)
