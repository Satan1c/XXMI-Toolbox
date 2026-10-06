import time

from bpy.types import Context, UILayout

from ..preferences import XXMI_TOOLBOX_Preferences, preferences
from . import install, operators, state
from .notes import wrapped
from .releases import RELEASES_PAGE
from .version import installed_version, version_text


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


def _text_width(context: Context) -> int:
	"""About how many characters fit across the panel: labels don't wrap by themselves."""
	region = context.region
	if region is None:
		return 60
	return max(24, int(region.width / (7 * context.preferences.view.ui_scale)) - 4)


def _paragraph(layout: UILayout, context: Context, text: str, icon: str) -> None:
	column = layout.column(align=True)
	for i, line in enumerate(wrapped([text], _text_width(context) - 3)):
		column.label(text=line.strip(), icon=icon if i == 0 else "BLANK1")


def _changes(
	layout: UILayout, context: Context, prefs: XXMI_TOOLBOX_Preferences
) -> None:
	release = state.STATE.latest
	if release is None or not release.changes:
		return
	box = layout.box()
	row = box.row()
	row.alignment = "LEFT"
	current = " (installed)" if release.version == installed_version() else ""
	row.prop(
		prefs,
		"show_changes",
		text=f"Changes in {version_text(release.version)}{current}",
		icon="DOWNARROW_HLT" if prefs.show_changes else "RIGHTARROW",
		emboss=False,
	)
	if not prefs.show_changes:
		return
	column = box.column(align=True)
	column.scale_y = 0.8
	for line in wrapped(release.changes, _text_width(context)):
		column.label(text=line)


def draw_updater(layout: UILayout, context: Context) -> None:
	column = layout.column()
	if not state.online_access():
		_paragraph(
			column,
			context,
			"Turn on Allow Online Access in Preferences > System",
			"INTERNET_OFFLINE",
		)
	_status(column)
	if state.STATE.error:
		_paragraph(column, context, state.STATE.error, "ERROR")
	if install.is_development_copy():
		_paragraph(column, context, "Git checkout: update it with git", "INFO")

	prefs = preferences(context)
	_changes(column, context, prefs)
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
