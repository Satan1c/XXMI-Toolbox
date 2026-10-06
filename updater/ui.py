import time

from bpy.types import Context, UILayout

from ..preferences import preferences
from . import install, operators, state
from .releases import RELEASES_PAGE
from .version import version_text


def _status(layout: UILayout) -> None:
	current = state.STATE
	row = layout.row(align=True)
	row.scale_y = 1.5
	check = operators.XXMI_TOOLBOX_OT_check_for_update.bl_idname
	if current.installed:
		row.alert = True
		row.label(
			text=f"{current.installed} installed: restart Blender", icon="CHECKMARK"
		)
		return
	if current.checking:
		sub = row.row(align=True)
		sub.enabled = False
		sub.operator(check, text="Checking...")
		return
	if state.update_available():
		row.operator(
			operators.XXMI_TOOLBOX_OT_install_update.bl_idname,
			text=f"Update Now to {version_text(current.latest.version)}",
			icon="IMPORT",
		)
	elif current.checked:
		sub = row.row(align=True)
		sub.enabled = False
		sub.operator(check, text="Up to Date")
	else:
		row.operator(check, icon="URL")
		return
	row.operator(check, text="", icon="FILE_REFRESH")


def draw_updater(layout: UILayout, context: Context) -> None:
	column = layout.column()
	if not state.online_access():
		column.label(
			text="Online access is off in Preferences > System", icon="INTERNET_OFFLINE"
		)
	_status(column)
	if state.STATE.error:
		column.label(text=state.STATE.error, icon="ERROR")
	if install.is_development_copy():
		column.label(text="Git checkout: update it with git", icon="INFO")

	prefs = preferences(context)
	row = column.row()
	row.prop(prefs, "auto_check_update")
	sub = row.row()
	sub.active = prefs.auto_check_update
	sub.prop(prefs, "update_interval_days")

	row = column.row()
	last = state.STATE.last_check
	when = time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "never"
	row.label(text=f"Last check: {when}")
	row.operator("wm.url_open", text="Releases", icon="URL").url = RELEASES_PAGE


def draw_update_notice(layout: UILayout, context: Context) -> None:
	current = state.STATE
	if (
		not state.update_available()
		or current.installed
		or current.latest.tag == current.ignored
	):
		return
	box = layout.box()
	column = box.column(align=True)
	column.alert = True
	column.label(
		text=f"XXMI Toolbox {version_text(current.latest.version)} is out", icon="ERROR"
	)
	column.alert = False
	row = column.row(align=True)
	row.scale_y = 1.3
	row.operator(operators.XXMI_TOOLBOX_OT_ignore_update.bl_idname, icon="X")
	row.operator(operators.XXMI_TOOLBOX_OT_install_update.bl_idname, icon="IMPORT")
	column.operator(
		"wm.url_open", text="Release Notes", icon="URL"
	).url = current.latest.page
