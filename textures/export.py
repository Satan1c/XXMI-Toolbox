import os
from dataclasses import dataclass
from pathlib import Path

import bpy
import numpy as np
from bpy.types import Context, Image, Material, Node

from ..common.log import log
from .dds import is_srgb, write_dds

# Color spaces whose float pixels are data, not colors to encode as sRGB.
_DATA_SPACES = {"Non-Color", "Raw", "Linear Rec.709", "Generic Data"}


@dataclass
class Replacement:
	"""An image to write as a mod texture in place of the dump's."""

	image: Image
	# The dump's texture it replaces, and the file the mod reads.
	source: Path
	target: Path
	# Whether it holds colors when the dump's texture doesn't tell.
	srgb: bool


def scene_materials(context: Context) -> list[Material]:
	"""The materials of the scene's meshes, by name."""
	found = {
		material
		for obj in context.scene.objects
		if obj.type == "MESH"
		for material in obj.data.materials
		if material is not None
	}
	return sorted(found, key=lambda material: material.name)


def image_nodes(material: Material) -> list[Node]:
	if material.node_tree is None:
		return []
	return [
		node
		for node in material.node_tree.nodes
		if node.type == "TEX_IMAGE" and node.image is not None
	]


def _pixels(image: Image, srgb: bool) -> np.ndarray:
	"""The image's 8-bit RGBA rows, top first. Byte images hold their colors as stored;
	float ones are linear, and are encoded for an sRGB texture unless they hold data."""
	width, height = image.size
	pixels = np.empty(width * height * 4, dtype=np.float32)
	image.pixels.foreach_get(pixels)
	pixels = pixels.reshape(height, width, 4)[::-1]

	if srgb and image.is_float and image.colorspace_settings.name not in _DATA_SPACES:
		rgb = np.clip(pixels[..., :3], 0.0, None)
		pixels[..., :3] = np.where(
			rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055
		)
	return (np.clip(pixels, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _same_file(image: Image, path: Path) -> bool:
	source = bpy.path.abspath(image.filepath, library=image.library)
	try:
		return bool(source) and os.path.samefile(source, path)
	except OSError:
		return False


def write_replacements(
	replacements: list[Replacement],
) -> tuple[list[str], list[str], list[str]]:
	"""Write each replacement as an uncompressed .dds, sRGB where the dump's texture is.
	Returns the files written, those left to the exporter as still the dump's, and those that couldn't be."""
	written, kept, failed = [], [], []
	for replacement in replacements:
		image, name = replacement.image, replacement.target.name
		if _same_file(image, replacement.source):
			kept.append(name)
			continue
		if not image.size[0]:
			failed.append(f"{name} ({image.name} has no pixels)")
			continue

		srgb = is_srgb(replacement.source)
		srgb = replacement.srgb if srgb is None else srgb
		try:
			replacement.target.parent.mkdir(parents=True, exist_ok=True)
			write_dds(replacement.target, _pixels(image, srgb), srgb)
		except OSError as e:
			failed.append(f"{name} ({e.strerror or e})")
			continue
		log.info(
			"wrote %s from %s, %dx%d, %s",
			replacement.target,
			image.name,
			*image.size,
			"sRGB" if srgb else "linear",
		)
		written.append(name)
	return written, kept, failed
