from collections.abc import Sequence

import numpy as np
from bpy.types import Object


def reset_vertex_colors(
	obj: Object, name: str, color: Sequence[float], data_type: str, domain: str
) -> None:
	mesh = obj.data
	existing = mesh.color_attributes.get(name)
	if existing is not None:
		mesh.color_attributes.remove(existing)
	attribute = mesh.color_attributes.new(name=name, type=data_type, domain=domain)
	attribute.data.foreach_set(
		"color", np.tile(np.array(color, dtype=np.float32), len(attribute.data))
	)


def convert_byte_colors(obj: Object) -> list[str]:
	mesh = obj.data
	converted = []
	# Removing an attribute invalidates references to the others, so look each one up again by name.
	for name in [a.name for a in mesh.color_attributes if a.data_type == "BYTE_COLOR"]:
		attribute = mesh.color_attributes[name]
		domain = attribute.domain
		# color_srgb is the raw stored byte/255; `color` would decode it as sRGB and change the values the game reads.
		data = np.empty(len(attribute.data) * 4, dtype=np.float32)
		attribute.data.foreach_get("color_srgb", data)
		mesh.color_attributes.remove(attribute)
		mesh.color_attributes.new(
			name=name, type="FLOAT_COLOR", domain=domain
		).data.foreach_set("color", data)
		converted.append(name)
	return converted
