from typing import Any

from bpy.types import ID


def custom_property_keys(obj: ID) -> list[str]:
	# Add-on properties registered on Object also show up in keys(); those belong to their add-on.
	rna = obj.bl_rna.properties
	return [key for key in obj.keys() if key not in rna and key != "_RNA_UI"]


def _plain(value: Any) -> Any:
	if hasattr(value, "to_dict"):
		return value.to_dict()
	if hasattr(value, "to_list"):
		return value.to_list()
	return value


def replace_custom_properties(source: ID, target: ID) -> int:
	for key in custom_property_keys(target):
		del target[key]
	keys = custom_property_keys(source)
	for key in keys:
		target[key] = _plain(source[key])
		try:
			target.id_properties_ui(key).update(
				**source.id_properties_ui(key).as_dict()
			)
		except TypeError:
			pass  # Group and ID properties have no UI data.
	return len(keys)
