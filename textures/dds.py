import struct
from pathlib import Path

import numpy as np

_R8G8B8A8_UNORM = 28
_R8G8B8A8_UNORM_SRGB = 29
_SRGB_FORMATS = {_R8G8B8A8_UNORM_SRGB, 72, 75, 78, 91, 93, 99}


def is_srgb(path: Path) -> bool | None:
	"""Whether a .dds file holds sRGB colors, or None if it can't tell (no file, or an old-style header)."""
	try:
		with open(path, "rb") as file:
			header = file.read(148)
	except OSError:
		return None
	if len(header) < 148 or header[:4] != b"DDS " or header[84:88] != b"DX10":
		return None
	return struct.unpack_from("<I", header, 128)[0] in _SRGB_FORMATS


def write_dds(path: Path, pixels: np.ndarray, srgb: bool) -> None:
	"""Write (height, width, 4) 8-bit RGBA rows, top first, as an uncompressed single-level .dds."""
	height, width = pixels.shape[:2]
	# DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PITCH | DDSD_PIXELFORMAT
	flags = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000
	header = struct.pack(
		"<4s7I44x", b"DDS ", 124, flags, height, width, width * 4, 0, 1
	)
	# The pixel format points on to the DX10 header; DDSCAPS_TEXTURE.
	header += struct.pack("<2I4s5I", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
	header += struct.pack("<5I", 0x1000, 0, 0, 0, 0)
	fmt = _R8G8B8A8_UNORM_SRGB if srgb else _R8G8B8A8_UNORM
	# A 2D texture, one in its array.
	header += struct.pack("<5I", fmt, 3, 0, 1, 0)
	with open(path, "wb") as file:
		file.write(header)
		file.write(np.ascontiguousarray(pixels, np.uint8).tobytes())
