import os

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Context, Event, Object, Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..common.library import add_saved
from ..common.log import report
from ..common.utils import ToolError, object_mode, selected_meshes
from . import attach, clean_model, cleanup, save
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
		with object_mode(context):
			lines = attach.attach(
				context, game_armature(context), selected_meshes(context)
			)
		for line in lines[1:]:
			report(self, "WARNING", line)
		report(self, "INFO", lines[0])
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
		with object_mode(context):
			line = cleanup.clean_up(
				context,
				game_armature(context),
				self.gather_ids,
				self.connect_bones,
			)
		report(self, "INFO", line)
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
			raise ToolError(f"Save the {self.saved} to another file than this one")
		folder = os.path.dirname(os.path.abspath(bpy.path.abspath(self.filepath)))
		if not os.path.isdir(folder):
			raise ToolError(f"{folder} doesn't exist")

		line = self.save(context)
		report(self, "INFO", line)
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


def _rigged(context: Context) -> list[Object]:
	return [obj for obj in selected_meshes(context) if obj.find_armature()]


class XXMI_TOOLBOX_OT_save_clean_model(_SaveBlend, Operator):
	bl_idname = "xxmi_toolbox.save_clean_model"
	bl_label = "Save Clean Model"
	bl_description = (
		"Save the selected rigged meshes to a new .blend as a plain model: modifiers (but Subdivision) applied, into "
		"each shape key too, and an armature of just the deform bones they use, with no controls, constraints, "
		"drivers or widgets. Add it to a mod project with Add Saved. This file is left as it is"
	)
	saved = "clean model"

	drop_empty_uvs: BoolProperty(
		name="Drop Empty UV Maps",
		default=True,
		description="Leave out UV maps that give less than a tenth of the faces any area: leftovers, not textures",
	)  # type: ignore
	rename_uvs: BoolProperty(
		name="Name UV Maps UV0, UV1...",
		default=True,
		description="Name the UV maps in order, the main one first, so Model Swap can tell them apart by number",
	)  # type: ignore

	@classmethod
	def poll(cls, context: Context) -> bool:
		return bool(_rigged(context))

	def saved_name(self, context: Context) -> str:
		return clean_model.main_rig(_rigged(context)).name

	def save(self, context: Context) -> str:
		with object_mode(context):
			return clean_model.save_clean_model(
				context,
				_rigged(context),
				self.filepath,
				self.drop_empty_uvs,
				self.rename_uvs,
			)


class XXMI_TOOLBOX_OT_add_saved(Operator, ImportHelper):
	bl_idname = "xxmi_toolbox.add_saved"
	bl_label = "Add Saved"
	bl_description = "Add a model saved with Save Clean Model, or a game armature saved with Save Game Armature, to this scene"
	bl_options = {"REGISTER", "UNDO"}
	filename_ext = ".blend"
	filter_glob: StringProperty(default="*.blend", options={"HIDDEN"})  # type: ignore

	def execute(self, context: Context) -> set[str]:
		with object_mode(context):
			objects = add_saved(context, self.filepath)
		report(
			self,
			"INFO",
			f"Added {len(objects)} objects from {os.path.basename(self.filepath)}",
		)
		return {"FINISHED"}
