from collections.abc import Callable, Iterable

from bpy.props import EnumProperty, IntProperty
from bpy.types import Context, Object, Operator, bpy_prop_collection

from ..common.utils import ToolError, object_mode
from ..vertex_groups import remap
from . import custom_properties, swap
from .settings import XXMI_TOOLBOX_ModelSwapSettings, XXMI_TOOLBOX_ObjectItem


def _meshes(items: Iterable[XXMI_TOOLBOX_ObjectItem]) -> list[Object]:
	seen = []
	for item in items:
		if item.object is not None and item.object not in seen:
			seen.append(item.object)
	return seen


def sync_uv_slots(settings: XXMI_TOOLBOX_ModelSwapSettings) -> None:
	"""One slot per UV map of the first source, keeping the choices made for names it still has;
	a new one is filled from the target map in the same place."""
	sources = _meshes(settings.sources)
	names = [layer.name for layer in sources[0].data.uv_layers] if sources else []
	if [item.name for item in settings.uv_slots] == names:
		return
	chosen = {item.name: (item.slot, item.fill) for item in settings.uv_slots}
	settings.uv_slots.clear()
	for position, name in enumerate(names, 1):
		item = settings.uv_slots.add()
		item.name = name
		item.slot, item.fill = chosen.get(name, (position, "AUTO"))


def _swap_objects(
	context: Context,
) -> tuple[XXMI_TOOLBOX_ModelSwapSettings, list[Object], list[Object]]:
	settings = context.scene.xxmi_toolbox.model_swap
	sources, targets = _meshes(settings.sources), _meshes(settings.targets)
	if not sources or not targets:
		raise ToolError("Add at least one source and one target mesh")
	if set(sources) & set(targets):
		raise ToolError("A mesh can't be both a source and a target")
	return settings, sources, targets


# Experimental tools can pick the remap's groups: each gives a remap.Choose for the sources, or None.
remap_choosers: list[Callable[[Context, list[Object]], remap.Choose | None]] = []


def _remap_choose(context: Context, sources: list[Object]) -> remap.Choose | None:
	for chooser in remap_choosers:
		choose = chooser(context, sources)
		if choose is not None:
			return choose
	return None


class _SwapOperator:
	bl_options = {"REGISTER", "UNDO"}

	@classmethod
	def poll(cls, context: Context) -> bool:
		settings = context.scene.xxmi_toolbox.model_swap
		return bool(_meshes(settings.sources)) and bool(_meshes(settings.targets))


class XXMI_TOOLBOX_OT_remap_vertex_groups(_SwapOperator, Operator):
	bl_idname = "xxmi_toolbox.remap_vertex_groups"
	bl_label = "Remap Vertex Groups"
	bl_description = (
		"Rename target vertex groups after the source group they overlap most, matching all source and all target meshes together. "
		"Meshes must be aligned in world space. Several groups landing on the same name get a .001 suffix: run Merge afterwards"
	)

	def execute(self, context: Context) -> set[str]:
		try:
			_, sources, targets = _swap_objects(context)
			with object_mode(context):
				renamed, least_certain = remap.remap(
					context,
					targets,
					sources,
					choose=_remap_choose(context, sources),
				)
		except ToolError as e:
			self.report({"ERROR"}, str(e))
			return {"CANCELLED"}
		message = f"Remapped {renamed} vertex groups"
		if least_certain:
			message += "; least certain: " + ", ".join(
				f"{a} -> {b} ({share:.0%})" for share, a, b in least_certain
			)
		self.report({"INFO"}, message)
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_model_swap(_SwapOperator, Operator):
	bl_idname = "xxmi_toolbox.model_swap"
	bl_label = "Model Swap"
	bl_description = (
		"Apply the source format to every target mesh: UV names, colors and vertex groups. "
		"Several source meshes are used together as one. Meshes must be aligned in world space"
	)

	def execute(self, context: Context) -> set[str]:
		try:
			settings, sources, targets = _swap_objects(context)
		except ToolError as e:
			self.report({"ERROR"}, str(e))
			return {"CANCELLED"}
		with object_mode(context):
			try:
				sync_uv_slots(settings)
				messages = swap.model_swap(
					context,
					sources,
					targets,
					uv_slots=[item.slot for item in settings.uv_slots],
					uv_modes=[item.fill for item in settings.uv_slots],
					uvs=settings.swap_uvs,
					colors=settings.swap_colors,
					weights=settings.swap_weights,
					keep_target_weights=settings.swap_weights_mode == "REMAP",
					remap_choose=_remap_choose(context, sources),
				)
			except ToolError as e:
				self.report({"ERROR"}, str(e))
				return {"FINISHED"}
		for message in messages:
			level = message.split(":", 1)[0]
			self.report({level} if level in ("WARNING", "ERROR") else {"INFO"}, message)
		self.report({"INFO"}, f"Model Swap applied to {len(targets)} meshes")
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_copy_custom_properties(Operator):
	bl_idname = "xxmi_toolbox.copy_custom_properties"
	bl_label = "Copy Custom Properties"
	bl_description = "Replace the custom properties of every target mesh with those of the single source mesh"
	bl_options = {"REGISTER", "UNDO"}

	@classmethod
	def poll(cls, context: Context) -> bool:
		settings = context.scene.xxmi_toolbox.model_swap
		if len(_meshes(settings.sources)) != 1:
			cls.poll_message_set("Needs exactly one source mesh")
			return False
		return bool(_meshes(settings.targets))

	def execute(self, context: Context) -> set[str]:
		try:
			_, sources, targets = _swap_objects(context)
		except ToolError as e:
			self.report({"ERROR"}, str(e))
			return {"CANCELLED"}
		for target in targets:
			custom_properties.replace_custom_properties(sources[0], target)
		self.report(
			{"INFO"},
			f"Copied custom properties from {sources[0].name} to {len(targets)} meshes",
		)
		return {"FINISHED"}


_SIDES = [("SOURCE", "Source", ""), ("TARGET", "Target", "")]


def _side_lists(
	context: Context, side: str
) -> tuple[bpy_prop_collection, bpy_prop_collection]:
	settings = context.scene.xxmi_toolbox.model_swap
	if side == "SOURCE":
		return settings.sources, settings.targets
	return settings.targets, settings.sources


class XXMI_TOOLBOX_OT_list_add_selected(Operator):
	bl_idname = "xxmi_toolbox.list_add_selected"
	bl_label = "Add Selected"
	bl_description = "Add the selected meshes to this list"
	bl_options = {"REGISTER", "UNDO"}

	side: EnumProperty(items=_SIDES)  # type: ignore

	def execute(self, context: Context) -> set[str]:
		items, other = _side_lists(context, self.side)
		present = set(_meshes(items))
		skipped = set(_meshes(other))
		for obj in context.selected_objects:
			if obj.type == "MESH" and obj not in present and obj not in skipped:
				items.add().object = obj
		sync_uv_slots(context.scene.xxmi_toolbox.model_swap)
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_list_remove(Operator):
	bl_idname = "xxmi_toolbox.list_remove"
	bl_label = "Remove"
	bl_description = "Remove this mesh from the list"
	bl_options = {"REGISTER", "UNDO"}

	side: EnumProperty(items=_SIDES)  # type: ignore
	index: IntProperty()  # type: ignore

	def execute(self, context: Context) -> set[str]:
		items, _ = _side_lists(context, self.side)
		if 0 <= self.index < len(items):
			items.remove(self.index)
		sync_uv_slots(context.scene.xxmi_toolbox.model_swap)
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_list_clear(Operator):
	bl_idname = "xxmi_toolbox.list_clear"
	bl_label = "Clear"
	bl_description = "Remove all meshes from the list"
	bl_options = {"REGISTER", "UNDO"}

	side: EnumProperty(items=_SIDES)  # type: ignore

	def execute(self, context: Context) -> set[str]:
		_side_lists(context, self.side)[0].clear()
		sync_uv_slots(context.scene.xxmi_toolbox.model_swap)
		return {"FINISHED"}
