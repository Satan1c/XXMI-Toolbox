from bpy.types import Context, Operator

from ..common.utils import ToolError
from . import install, state
from .version import version_text


class XXMI_TOOLBOX_OT_check_for_update(Operator):
	bl_idname = "xxmi_toolbox.check_for_update"
	bl_label = "Check for Update"
	bl_description = "Ask GitHub for the latest XXMI Toolbox release"

	@classmethod
	def poll(cls, context: Context) -> bool:
		if not state.online_access():
			cls.poll_message_set("Allow Online Access in Preferences > System")
			return False
		return not state.STATE.checking

	def execute(self, context: Context) -> set[str]:
		state.start_check()
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_install_update(Operator):
	bl_idname = "xxmi_toolbox.install_update"
	bl_label = "Update Now"
	bl_description = (
		"Download the latest release from GitHub and install it over this one"
	)

	@classmethod
	def poll(cls, context: Context) -> bool:
		if install.is_development_copy():
			cls.poll_message_set("This is a git checkout: update it with git")
			return False
		return state.online_access() and state.update_available()

	def execute(self, context: Context) -> set[str]:
		release = state.STATE.latest
		try:
			install.install(release)
		except ToolError as e:
			self.report({"ERROR"}, str(e))
			return {"CANCELLED"}
		state.STATE.installed = version_text(release.version)
		self.report(
			{"INFO"}, f"XXMI Toolbox {state.STATE.installed} installed: restart Blender"
		)
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_ignore_update(Operator):
	bl_idname = "xxmi_toolbox.ignore_update"
	bl_label = "Ignore"
	bl_description = (
		"Stop showing this release in the sidebar; it stays in the add-on preferences"
	)

	def execute(self, context: Context) -> set[str]:
		if state.STATE.latest is not None:
			state.STATE.ignored = state.STATE.latest.tag
			state.save_state()
		return {"FINISHED"}
