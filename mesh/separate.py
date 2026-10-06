import bpy
from bpy.types import Context, Object


def separate_by_material(context: Context, obj: Object) -> list[Object]:
	before = set(bpy.data.objects)
	with context.temp_override(
		object=obj,
		active_object=obj,
		selected_objects=[obj],
		selected_editable_objects=[obj],
	):
		bpy.ops.object.mode_set(mode="EDIT")
		bpy.ops.mesh.select_all(action="SELECT")
		bpy.ops.mesh.separate(type="MATERIAL")
		bpy.ops.object.mode_set(mode="OBJECT")
	parts = [obj] + [o for o in bpy.data.objects if o not in before]
	for part in parts:
		material = part.active_material
		if material is not None:
			part.name = material.name.replace("mat_", "").replace("Diffuse", "").strip()
	return parts
