import json
import re
from collections.abc import Callable
from pathlib import Path

from bpy.types import Image, Material, Node, NodeSocket

from ..common.utils import ToolError
from .export import Replacement, image_nodes

# Blender's suffix on a name already taken: NangongYuRapsodyBodyA.001.
_COPY_SUFFIX = re.compile(r"\.\d{3}$")


def dump_parts(dump: Path) -> dict[str, list[tuple[str, str]]]:
	"""{part name: [(texture slot, file extension)]} from the dump's hash.json,
	named the way XXMI Tools names them: the dump folder's name, the component's and the part's letter."""
	try:
		components = json.loads((dump / "hash.json").read_text())
	except (OSError, ValueError) as e:
		raise ToolError(f"Can't read {dump / 'hash.json'}: {e}") from e

	parts = {}
	for component in components:
		for letter, textures in zip(
			component.get("object_classifications", []),
			component.get("texture_hashes", []),
		):
			name = dump.name + component["component_name"] + letter
			parts[name] = [(slot, ext) for slot, ext, _ in textures]
	return parts


def _plain(name: str) -> str:
	return re.sub(r"[^a-z0-9]", "", name.lower())


def _named_slot(node: Node, slots: list[str]) -> str | None:
	"""The slot an image node's label, name or image says it fills: ending in Diffuse, NormalMap..."""
	image = node.image
	names = [node.label, node.name, image.name, Path(image.filepath).stem]
	for slot in slots:
		if any(_plain(name).endswith(_plain(slot)) for name in names if name):
			return slot
	return None


def _feeds(node: Node, reaches: Callable[[NodeSocket], bool]) -> bool:
	"""Whether the node's output reaches a socket passing the test, through any nodes on the way."""
	seen, todo = set(), [node]
	while todo:
		current = todo.pop()
		for output in current.outputs:
			for link in output.links:
				if reaches(link.to_socket):
					return True
				if link.to_node not in seen:
					seen.add(link.to_node)
					todo.append(link.to_node)
	return False


def _is_diffuse(socket: NodeSocket) -> bool:
	return socket.name == "Base Color"


def _is_normal(socket: NodeSocket) -> bool:
	return socket.node.type == "NORMAL_MAP" and socket.name == "Color"


def slot_images(material: Material, slots: list[str]) -> dict[str, Image]:
	"""{slot: image} for the material's image nodes: by what they're named after first,
	then a Base Color one as the Diffuse and one through a Normal Map node as the NormalMap."""
	nodes = image_nodes(material)

	found = {}
	for node in nodes:
		slot = _named_slot(node, slots)
		if slot is not None:
			found.setdefault(slot, node.image)

	for slot, test in (("Diffuse", _is_diffuse), ("NormalMap", _is_normal)):
		if slot in slots and slot not in found:
			node = next((n for n in nodes if _feeds(n, test)), None)
			if node is not None:
				found[slot] = node.image
	return found


def part_replacements(
	materials: list[Material], dump: Path, textures: Path
) -> tuple[list[Replacement], list[str]]:
	"""XXMI Tools: the images of materials named after the dump's parts, as those parts' textures.
	Also returns the textures that can't be written."""
	parts = dump_parts(dump)
	replacements, failed = [], []
	for material in materials:
		part = _COPY_SUFFIX.sub("", material.name)
		if part not in parts:
			continue
		extensions = dict(parts[part])
		for slot, image in slot_images(material, list(extensions)).items():
			filename = part + slot + extensions[slot]
			if extensions[slot].lower() != ".dds":
				failed.append(f"{filename} (only .dds is written)")
				continue
			# Without the dump's to go by, only a Diffuse holds colors.
			replacements.append(
				Replacement(
					image, dump / filename, textures / filename, slot == "Diffuse"
				)
			)
	return replacements, failed
