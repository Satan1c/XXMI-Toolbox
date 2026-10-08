import re
from pathlib import Path

from bpy.types import Material

from .export import Replacement, image_nodes

# A texture's hash in a WWMI or EFMI Tools dump's file names:
# "Components-0-1 t=1a2b3c4d.dds", or the older "Component_0-ps-t0-1a2b3c4d.dds".
_DUMPED = (
	re.compile(r"t=([0-9a-f]{8})"),
	re.compile(r"component_\d-ps-t\d-([0-9a-f]{8})"),
)
_HASH = re.compile(r"[0-9a-f]{8}")


def dumped_textures(source: Path) -> dict[str, str]:
	"""{hash: file name} of the textures in the object's dump folder, as the exporter finds them."""
	found = {}
	for path in sorted(source.iterdir()) if source.is_dir() else ():
		if path.suffix.lower() not in (".dds", ".jpg"):
			continue
		for pattern in _DUMPED:
			match = pattern.search(path.name.lower())
			if match:
				found.setdefault(match.group(1), path.name)
				break
	return found


def hash_replacements(
	materials: list[Material], source: Path, textures: Path
) -> tuple[list[Replacement], list[str]]:
	"""WWMI and EFMI Tools: any image whose node or image is named with a dumped texture's hash, as that texture.
	Also returns the textures that can't be written."""
	dumped = dumped_textures(source)
	replacements, failed, taken = [], [], set()
	for material in materials:
		for node in image_nodes(material):
			image = node.image
			names = [node.label, node.name, image.name, Path(image.filepath).name]
			hashes = {h for name in names for h in _HASH.findall(name.lower())}
			for texture_hash in sorted(hashes & set(dumped)):
				filename = dumped[texture_hash]
				if filename in taken:
					continue
				taken.add(filename)
				if not filename.lower().endswith(".dds"):
					failed.append(f"{filename} (only .dds is written)")
					continue
				replacements.append(
					Replacement(
						image,
						source / filename,
						textures / filename,
						image.colorspace_settings.name == "sRGB",
					)
				)
	return replacements, failed
