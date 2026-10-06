from bpy.props import BoolProperty
from bpy.types import Context, Object, Operator

from ..common.utils import ToolError, object_mode, selected_meshes
from . import attach, cleanup
from .settings import CONNECT_DESCRIPTION, GATHER_DESCRIPTION


def game_armature(context: Context) -> Object | None:
	"""The one game armature the selection points at: selected, deforming a selected mesh, or behind its ID armature."""
	objects = [context.active_object, *context.selected_objects]
	armatures = {attach.game_armature(obj) for obj in objects}
	armatures |= {
		attach.game_armature(obj.find_armature()) for obj in selected_meshes(context)
	}
	armatures.discard(None)
	return armatures.pop() if len(armatures) == 1 else None


class XXMI_TOOLBOX_OT_attach_to_game_armature(Operator):
	bl_idname = "xxmi_toolbox.attach_to_game_armature"
	bl_label = "Attach to Game Armature"
	bl_description = (
		"Make the selected dumped meshes follow the game armature. Select the game model (its armature or a mesh it "
		"deforms) and the dumped meshes, in the same place and scale. Each dumped mesh's IDs are matched to the game "
		"bones it overlaps; meshes numbering their bones the same way share a hidden armature whose bones are named by "
		"ID and copy the game bones, so posing the game armature poses them all and their vertex groups stay as they "
		"are. Run it again with new pieces selected to attach them too"
	)
	bl_options = {"REGISTER", "UNDO"}

	@classmethod
	def poll(cls, context: Context) -> bool:
		return game_armature(context) is not None and bool(selected_meshes(context))

	def execute(self, context: Context) -> set[str]:
		try:
			with object_mode(context):
				lines = attach.attach(
					context, game_armature(context), selected_meshes(context)
				)
		except ToolError as e:
			self.report({"ERROR"}, str(e))
			return {"CANCELLED"}
		for line in lines[1:]:
			self.report({"WARNING"}, line)
		self.report({"INFO"}, lines[0])
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_clean_up_game_model(Operator):
	bl_idname = "xxmi_toolbox.clean_up_game_model"
	bl_label = "Clean Up Game Model"
	bl_description = (
		"Once every dumped mesh is attached: delete the game model's meshes, what hangs under its armature (weapons, "
		"props), the empties left holding nothing (hiding the ones above the armature) and the bones no ID armature follows, keeping their parents. New pieces can't be attached afterwards"
	)
	bl_options = {"REGISTER", "UNDO"}

	gather_ids: BoolProperty(
		name="Into Collections", default=True, description=GATHER_DESCRIPTION
	)  # type: ignore
	connect_bones: BoolProperty(
		name="Connect Bones", default=True, description=CONNECT_DESCRIPTION
	)  # type: ignore

	@classmethod
	def poll(cls, context: Context) -> bool:
		rig = game_armature(context)
		return rig is not None and bool(attach.existing_spaces(context, rig))

	def execute(self, context: Context) -> set[str]:
		try:
			with object_mode(context):
				line = cleanup.clean_up(
					context,
					game_armature(context),
					self.gather_ids,
					self.connect_bones,
				)
		except ToolError as e:
			self.report({"ERROR"}, str(e))
			return {"CANCELLED"}
		self.report({"INFO"}, line)
		return {"FINISHED"}
