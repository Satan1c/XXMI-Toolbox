import bpy
from bpy.props import (
	BoolProperty,
	CollectionProperty,
	EnumProperty,
	FloatVectorProperty,
	StringProperty,
)
from bpy.types import Context, Event, Object, Operator, PropertyGroup

from ..common.log import report
from ..common.operators import PerMeshOperator
from ..common.utils import object_mode, selected_meshes
from . import colors, sculpt, separate, shape_keys, uv


class XXMI_TOOLBOX_OT_separate_by_material(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.separate_by_material"
	bl_label = "Separate by Material"
	bl_description = "Separate meshes by material and name each part after its material"

	def process(self, context: Context, obj: Object) -> None:
		separate.separate_by_material(context, obj)


class XXMI_TOOLBOX_OT_clean_uv_names(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.clean_uv_names"
	bl_label = "Clean UV Names"
	bl_description = "Rename UV maps in order to TEXCOORD.xy, TEXCOORD1.xy, ... as expected by 3DMigoto"

	def process(self, context: Context, obj: Object) -> None:
		uv.clean_uv_names(obj)


class XXMI_TOOLBOX_OT_reset_vertex_colors(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.reset_vertex_colors"
	bl_label = "Reset Vertex Colors"
	bl_description = "Recreate a color attribute filled with a single color"

	name: StringProperty(name="Name", default="COLOR")  # type: ignore
	color: FloatVectorProperty(
		name="Color",
		subtype="COLOR",
		size=4,
		min=0.0,
		max=1.0,
		default=(1.0, 0.5, 0.5, 0.5),
	)  # type: ignore
	data_type: EnumProperty(
		name="Data Type",
		items=[
			("BYTE_COLOR", "Byte Color", ""),
			("FLOAT_COLOR", "Float Color", ""),
		],
		default="BYTE_COLOR",
	)  # type: ignore
	domain: EnumProperty(
		name="Domain",
		items=[
			("CORNER", "Face Corner", ""),
			("POINT", "Vertex", ""),
		],
		default="CORNER",
	)  # type: ignore

	def invoke(self, context: Context, event: Event) -> set[str]:
		return context.window_manager.invoke_props_dialog(self)

	def process(self, context: Context, obj: Object) -> None:
		colors.reset_vertex_colors(
			obj, self.name, self.color, self.data_type, self.domain
		)


class XXMI_TOOLBOX_OT_convert_vertex_colors(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.convert_vertex_colors"
	bl_label = "Convert Vertex Colors to Float"
	bl_description = "Convert byte color attributes to float storage, keeping the stored values unchanged"

	def process(self, context: Context, obj: Object) -> None:
		colors.convert_byte_colors(obj)


class XXMI_TOOLBOX_ModifierItem(PropertyGroup):
	apply: BoolProperty(name="Apply", default=False)  # type: ignore


class XXMI_TOOLBOX_OT_apply_modifiers_with_shape_keys(Operator):
	bl_idname = "xxmi_toolbox.apply_modifiers_with_shape_keys"
	bl_label = "Apply Modifiers with Shape Keys"
	bl_description = "Apply the chosen modifiers to the active mesh while keeping its shape keys. Sourced by Przemysław Bągard"
	bl_options = {"REGISTER", "UNDO"}

	modifiers: CollectionProperty(type=XXMI_TOOLBOX_ModifierItem)  # type: ignore

	@classmethod
	def poll(cls, context: Context) -> bool:
		obj = context.active_object
		return obj is not None and obj.type == "MESH" and len(obj.modifiers) > 0

	def invoke(self, context: Context, event: Event) -> set[str]:
		self.modifiers.clear()
		for modifier in context.active_object.modifiers:
			self.modifiers.add().name = modifier.name
		return context.window_manager.invoke_props_dialog(self)

	def draw(self, context: Context) -> None:
		key = context.active_object.data.shape_keys
		if key is not None and key.animation_data is not None:
			self.layout.label(
				text="Shape key animation and drivers will be lost", icon="ERROR"
			)
		column = self.layout.column(align=True)
		for item in self.modifiers:
			column.prop(item, "apply", text=item.name)

	def execute(self, context: Context) -> set[str]:
		names = [item.name for item in self.modifiers if item.apply]
		if not names:
			report(self, "ERROR", "No modifier chosen")
			return {"CANCELLED"}
		with object_mode(context):
			shape_keys.apply_modifiers_with_shape_keys(
				context, context.active_object, names
			)
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_name_shape_keys_for_export(Operator):
	bl_idname = "xxmi_toolbox.name_shape_keys_for_export"
	bl_label = "Name Shape Keys for Export"
	bl_description = (
		"Rename the selected meshes' shape keys to what the exporters take: keys already named Deform <n> (the game's "
		"own) or Custom <n> stay, every other one becomes Custom <n>, one number per name across the selection. Select "
		"all of a part's meshes together. The old names are kept in each mesh's custom properties"
	)
	bl_options = {"REGISTER", "UNDO"}

	@classmethod
	def poll(cls, context: Context) -> bool:
		return any(obj.data.shape_keys for obj in selected_meshes(context))

	def execute(self, context: Context) -> set[str]:
		with object_mode(context):
			count = shape_keys.name_for_export(selected_meshes(context))
		report(self, "INFO", f"Renamed {count} shape keys to Custom <n>")
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_create_merged_object(Operator):
	bl_idname = "xxmi_toolbox.create_merged_object"
	bl_label = "Create Merged Object"
	bl_description = "Join copies of the selected meshes into one object for sculpting. Don't add or remove vertices on the originals until the sculpt is applied"
	bl_options = {"REGISTER", "UNDO"}

	@classmethod
	def poll(cls, context: Context) -> bool:
		return len(selected_meshes(context)) > 1

	def execute(self, context: Context) -> set[str]:
		with object_mode(context):
			sculpt.create_merged_object(context, selected_meshes(context))
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_apply_merged_sculpt(Operator):
	bl_idname = "xxmi_toolbox.apply_merged_sculpt"
	bl_label = "Apply Merged Object Sculpt"
	bl_description = (
		"Copy vertex positions from the merged object back to the original meshes"
	)
	bl_options = {"REGISTER", "UNDO"}

	shape_keys: BoolProperty(
		name="Apply to Shape Keys",
		description="Also move every shape key of the originals by the sculpted offset",
	)  # type: ignore

	@classmethod
	def poll(cls, context: Context) -> bool:
		obj = context.active_object
		return (
			obj is not None
			and obj.type == "MESH"
			and any(
				key in obj
				for key in (sculpt.MERGED_OBJECT_KEY, *sculpt.LEGACY_MERGED_OBJECT_KEYS)
			)
		)

	def execute(self, context: Context) -> set[str]:
		merged = context.active_object
		# Sculpt strokes are only written back to the mesh when leaving Sculpt Mode.
		was_sculpt = merged.mode == "SCULPT"
		if was_sculpt:
			bpy.ops.object.mode_set(mode="OBJECT")
		try:
			count = sculpt.apply_merged_sculpt(merged, self.shape_keys)
		finally:
			if was_sculpt:
				bpy.ops.object.mode_set(mode="SCULPT")
		report(self, "INFO", f"Applied sculpt to {count} meshes")
		return {"FINISHED"}
