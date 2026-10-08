import os

import bpy
from bpy.props import BoolProperty
from bpy.types import Context, Event, Object, Operator
from bpy_extras.io_utils import ExportHelper

from ..common.utils import ToolError, object_mode, selected_meshes
from . import attach, cleanup, save
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


class _SaveBlend(ExportHelper):
	"""Writes a .blend to add with Add Saved: named after what it saves, next to this file, never over it."""

	filename_ext = ".blend"
	saved = ""

	def saved_name(self, context: Context) -> str:
		raise NotImplementedError

	def save(self, context: Context) -> str:
		raise NotImplementedError

	def invoke(self, context: Context, event: Event) -> set[str]:
		if not self.filepath:
			folder = os.path.dirname(bpy.data.filepath) or os.path.expanduser("~")
			name = bpy.path.clean_name(self.saved_name(context))
			self.filepath = os.path.join(folder, f"{name}.blend")
		return ExportHelper.invoke(self, context, event)

	def execute(self, context: Context) -> set[str]:
		this_file = bpy.data.filepath
		if this_file and os.path.abspath(self.filepath) == os.path.abspath(this_file):
			self.report(
				{"ERROR"}, f"Save the {self.saved} to another file than this one"
			)
			return {"CANCELLED"}
		try:
			line = self.save(context)
		except ToolError as e:
			self.report({"ERROR"}, str(e))
			return {"CANCELLED"}
		self.report({"INFO"}, line)
		return {"FINISHED"}


class XXMI_TOOLBOX_OT_save_game_armature(_SaveBlend, Operator):
	bl_idname = "xxmi_toolbox.save_game_armature"
	bl_label = "Save Game Armature"
	bl_description = (
		"Save the game armature and its ID armatures to a .blend for other mods of this character: add it there "
		"with Add Saved, select it with new dumped meshes and Attach to Game Armature, no game model needed"
	)
	saved = "game armature"

	@classmethod
	def poll(cls, context: Context) -> bool:
		rig = game_armature(context)
		return rig is not None and bool(attach.existing_spaces(context, rig))

	def saved_name(self, context: Context) -> str:
		return game_armature(context).name

	def save(self, context: Context) -> str:
		return save.save(context, game_armature(context), self.filepath)
