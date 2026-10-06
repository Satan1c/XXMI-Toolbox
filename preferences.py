from collections.abc import Callable

import bpy
from bpy.props import BoolProperty, IntProperty
from bpy.types import AddonPreferences, Context, UILayout

from .common.addon import ADDON

# Extra sections drawn under the updater, added by optional parts of the add-on.
DRAW_EXTRAS: list[Callable[[UILayout, Context], None]] = []


class XXMI_TOOLBOX_Preferences(AddonPreferences):
	bl_idname = ADDON

	auto_check_update: BoolProperty(
		name="Check Automatically",
		default=True,
		description="Look for a new release on GitHub when Blender starts, at most once per interval",
	)  # type: ignore
	update_interval_days: IntProperty(
		name="Every (Days)",
		default=1,
		min=1,
		max=30,
		description="Days between automatic update checks",
	)  # type: ignore
	show_changes: BoolProperty(
		name="Changes",
		default=True,
		description="Show what the latest release changed",
	)  # type: ignore

	def draw(self, context: Context) -> None:
		from .updater.ui import draw_updater

		draw_updater(self.layout.box(), context)
		for draw in DRAW_EXTRAS:
			draw(self.layout, context)


def preferences(context: Context) -> XXMI_TOOLBOX_Preferences:
	return context.preferences.addons[ADDON].preferences


register, unregister = bpy.utils.register_classes_factory((XXMI_TOOLBOX_Preferences,))
