from bpy.types import Context, Object

from ..common.library import write_objects
from ..common.utils import ToolError, deformed_by
from .attach import existing_spaces, record_centres


def save(context: Context, rig: Object, filepath: str) -> str:
	"""Write the game armature, the empties above it and its ID armatures to a .blend for other mods:
	new dumped meshes then attach to it without the game model."""
	spaces = existing_spaces(context, rig)
	if not spaces:
		raise ToolError(
			f"Nothing follows {rig.name} yet: attach the dumped meshes first"
		)
	# Armatures attached before centres were recorded get them from the meshes following them now.
	for space in spaces:
		space.meshes = deformed_by(context.scene.objects, {space.armature})
		record_centres(space)

	objects = [rig, *[space.armature for space in spaces]]
	parent = rig.parent
	while parent is not None:
		objects.append(parent)
		parent = parent.parent
	write_objects(filepath, rig.name, objects)
	return f"Saved {rig.name} with {len(spaces)} ID armatures to {filepath}"
