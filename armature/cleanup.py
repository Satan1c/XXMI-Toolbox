import bpy
from bpy.types import Context, Object

from ..common.utils import ToolError
from .attach import Space, editing, existing_spaces


def _kept_bones(rig: Object, spaces: list[Space]) -> set[str]:
	"""The game bones the ID armatures copy, and their parents: a bone's pose depends on every bone above it."""
	kept = set()
	for space in spaces:
		for name in space.bones.values():
			bone = rig.data.bones.get(name)
			while bone is not None and bone.name not in kept:
				kept.add(bone.name)
				bone = bone.parent
	return kept


def _remove_objects(objects: set[Object]) -> int:
	collections = {collection for obj in objects for collection in obj.users_collection}
	meshes = {obj.data for obj in objects if obj.type == "MESH"}
	for obj in objects:
		bpy.data.objects.remove(obj)
	for mesh in meshes:
		if not mesh.users:
			bpy.data.meshes.remove(mesh)
	# Only collections this emptied: ones the user left empty are none of its business.
	emptied = [
		collection
		for collection in collections
		if isinstance(collection, bpy.types.Collection)
		and not collection.all_objects
		and not collection.children
	]
	for collection in emptied:
		bpy.data.collections.remove(collection)
	return len(emptied)


def clean_up(context: Context, rig: Object) -> str:
	"""Remove what the ID armatures don't need from the game model: its meshes, what hangs under it (weapons,
	props) and the bones nothing copies."""
	spaces = existing_spaces(context, rig)
	if not spaces:
		raise ToolError(
			f"Nothing follows {rig.name} yet: attach the dumped meshes first"
		)
	armatures = {space.armature for space in spaces}
	attached = {
		obj
		for obj in context.scene.objects
		if obj.type == "MESH"
		and any(
			mod.type == "ARMATURE" and mod.object in armatures for mod in obj.modifiers
		)
	}
	doomed = {
		obj
		for obj in context.scene.objects
		if obj.type == "MESH" and obj.find_armature() == rig
	}
	doomed |= set(rig.children_recursive)
	doomed -= attached | armatures | {rig}

	kept = _kept_bones(rig, spaces)
	unused = [bone.name for bone in rig.data.bones if bone.name not in kept]
	if unused:
		with editing(context, rig) as edit_bones:
			for name in unused:
				edit_bones.remove(edit_bones[name])
	removed_objects = len(doomed)
	removed_collections = _remove_objects(doomed)
	return (
		f"Removed {removed_objects} objects, {len(unused)} bones and {removed_collections} emptied collections "
		f"from {rig.name}; kept {len(kept)} bones"
	)
