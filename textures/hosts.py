from dataclasses import dataclass
from pathlib import Path

import bpy
from bpy.types import Context

# (host add-on, its scene settings) for those naming textures by hash.
_HASHING_HOSTS = (
	("WWMI Tools", "wwmi_tools_settings"),
	("EFMI Tools", "efmi_tools_settings"),
)


@dataclass
class ModFolders:
	"""Where a host add-on's dump is and where its exporter puts the mod's textures."""

	host: str
	source: Path
	textures: Path
	# Whether the exporter writes the textures into the mod at all.
	copies: bool

	@property
	def by_part(self) -> bool:
		"""Whether textures are named after parts and slots (XXMI Tools) rather than by hash."""
		return self.host == "XXMI Tools"


def any_host(context: Context) -> bool:
	scene = context.scene
	return hasattr(scene, "xxmi") or any(hasattr(scene, a) for _, a in _HASHING_HOSTS)


def mod_folders(context: Context) -> list[ModFolders]:
	"""The folders of every installed host add-on set up in this scene, found as their exporters find them."""
	found = []
	xxmi = getattr(context.scene, "xxmi", None)
	if xxmi is not None and xxmi.dump_path:
		dump = Path(bpy.path.abspath(xxmi.dump_path))
		if not dump.is_dir() or dump.suffix:
			dump = dump.parent
		if xxmi.destination_path:
			destination = Path(bpy.path.abspath(xxmi.destination_path))
		else:
			destination = dump.parent / f"{dump.name}Mod"
		found.append(ModFolders("XXMI Tools", dump, destination, xxmi.copy_textures))

	for host, attribute in _HASHING_HOSTS:
		settings = getattr(context.scene, attribute, None)
		if settings is None or not settings.object_source_folder:
			continue
		if not settings.mod_output_folder:
			continue
		found.append(
			ModFolders(
				host,
				Path(bpy.path.abspath(settings.object_source_folder)),
				Path(bpy.path.abspath(settings.mod_output_folder)) / "Textures",
				settings.copy_textures,
			)
		)
	return found
