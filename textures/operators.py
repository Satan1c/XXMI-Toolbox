from bpy.types import Context, Operator

from ..common.utils import ToolError
from .export import scene_materials, write_replacements
from .hashes import hash_replacements
from .hosts import ModFolders, any_host, mod_folders
from .parts import part_replacements


def _export(context: Context, folders: ModFolders) -> tuple[list[str], list[str]]:
	"""Write one host's textures; returns the files written and the notes on the rest."""
	match = part_replacements if folders.by_part else hash_replacements
	replacements, failed = match(
		scene_materials(context), folders.source, folders.textures
	)
	written, kept, unwritten = write_replacements(replacements)

	notes = []
	if kept:
		notes.append(
			f"{folders.host}: still the dump's, left to the exporter: "
			+ ", ".join(kept)
		)
	if failed or unwritten:
		notes.append(f"{folders.host}: not written: " + ", ".join(failed + unwritten))
	if written and not folders.copies:
		notes.append(
			f"{folders.host} doesn't copy textures into the mod: the exported ini won't use them"
		)
	return written, notes


class XXMI_TOOLBOX_OT_export_material_textures(Operator):
	bl_idname = "xxmi_toolbox.export_material_textures"
	bl_label = "Export Material Textures"
	bl_description = (
		"Write material images into the mod as the textures they replace, where the exporter would copy the dump's; "
		"it keeps files already there. XXMI Tools: materials named after the dump's parts (NangongYuRapsodyBodyA), "
		"an image filling the slot its node or image is named after (Diffuse, NormalMap, LightMap, MaterialMap), else "
		"the one feeding Base Color is the Diffuse and one through a Normal Map node the NormalMap. WWMI and EFMI "
		"Tools: any image whose node or image name holds a dumped texture's hash. Written as uncompressed .dds, sRGB "
		"where the dump's texture is"
	)
	bl_options = {"REGISTER"}

	@classmethod
	def poll(cls, context: Context) -> bool:
		return any_host(context)

	def execute(self, context: Context) -> set[str]:
		try:
			hosts = mod_folders(context)
			if not hosts:
				raise ToolError(
					"Set XXMI Tools' Dump Folder, or WWMI or EFMI Tools' object sources and mod folder"
				)
			written, notes = [], []
			for folders in hosts:
				host_written, host_notes = _export(context, folders)
				written += [f"{folders.textures / name}" for name in host_written]
				notes += host_notes
		except ToolError as e:
			self.report({"ERROR"}, str(e))
			return {"CANCELLED"}

		if not written and not notes:
			self.report(
				{"ERROR"}, "No material image replaces one of the dump's textures"
			)
			return {"CANCELLED"}
		for note in notes:
			self.report({"WARNING"}, note)
		self.report({"INFO"}, f"Wrote {len(written)} textures: " + ", ".join(written))
		return {"FINISHED"}
