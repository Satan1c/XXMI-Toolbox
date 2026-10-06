from collections.abc import Callable

import bpy
from bpy.types import Context, Panel, UILayout

from .armature.ui import draw_armature
from .mesh.ui import draw_mesh
from .model_swap.ui import draw_model_swap
from .updater.ui import draw_update_notice, draw_updater
from .vertex_groups.ui import draw_vertex_groups

# (sidebar tab, panel that proves the host add-on is enabled)
HOSTS = (
	("XXMI Tools", "XXMI_PT_Sidebar"),
	("WWMI Tools", "WWMI_TOOLS_PT_SIDEBAR"),
	("EFMI Tools", "EFMI_TOOLS_PT_SIDEBAR"),
)

# (key, label, draw, poll or None)
SECTIONS = (
	("vertex_groups", "Vertex Groups", draw_vertex_groups, None),
	("mesh", "Mesh", draw_mesh, None),
	("model_swap", "Model Swap", draw_model_swap, None),
	("armature", "Armature", draw_armature, None),
	("updater", "Updater", draw_updater, None),
)


def _main_idname(host_panel: str) -> str:
	return f"XXMI_TOOLBOX_PT_{host_panel.lower()}"


def section_panel(
	category: str,
	host_panel: str,
	key: str,
	label: str,
	draw: Callable[[UILayout, Context], None],
	section_poll: Callable[[type[Panel], Context], bool] | None = None,
) -> type[Panel]:
	main_idname = _main_idname(host_panel)
	idname = f"{main_idname}_{key}"
	attributes = {
		"bl_idname": idname,
		"bl_label": label,
		"bl_space_type": "VIEW_3D",
		"bl_region_type": "UI",
		"bl_category": category,
		"bl_parent_id": main_idname,
		"bl_options": {"DEFAULT_CLOSED"},
		"draw": lambda self, context: draw(self.layout, context),
	}
	if section_poll:
		attributes["poll"] = classmethod(section_poll)
	return type(idname, (Panel,), attributes)


def _make_panels(category: str, host_panel: str) -> list[type[Panel]]:
	# One copy per host tab: a panel can only live in one sidebar category.
	def poll(cls: type[Panel], context: Context) -> bool:
		return hasattr(bpy.types, host_panel)

	main_idname = _main_idname(host_panel)
	panels = [
		type(
			main_idname,
			(Panel,),
			{
				"bl_idname": main_idname,
				"bl_label": "Toolbox",
				"bl_space_type": "VIEW_3D",
				"bl_region_type": "UI",
				"bl_category": category,
				"bl_order": 90,
				"bl_options": {"DEFAULT_CLOSED"},
				"poll": classmethod(poll),
				"draw": lambda self, context: draw_update_notice(self.layout, context),
			},
		)
	]
	panels += [section_panel(category, host_panel, *section) for section in SECTIONS]
	return panels


panels = [
	panel
	for category, host_panel in HOSTS
	for panel in _make_panels(category, host_panel)
]


def register():
	for panel in panels:
		bpy.utils.register_class(panel)


def unregister():
	for panel in reversed(panels):
		bpy.utils.unregister_class(panel)
