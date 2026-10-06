import os
import re

from ..common.addon import ADDON_DIR, IS_EXTENSION

Version = tuple[int, ...]


def parse_version(text: str) -> Version | None:
	match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip())
	return tuple(int(part) for part in match.group(1).split(".")) if match else None


def version_text(version: Version) -> str:
	return ".".join(str(part) for part in version)


def installed_version() -> Version:
	# The manifest is the one version both builds ship; bl_info is checked against it when releasing.
	with open(
		os.path.join(ADDON_DIR, "blender_manifest.toml"), encoding="utf-8"
	) as file:
		match = re.search(r'^version\s*=\s*"([^"]+)"', file.read(), re.MULTILINE)
	return (match and parse_version(match.group(1))) or (0,)


def asset_name(version: Version) -> str:
	suffix = "" if IS_EXTENSION else "-legacy"
	return f"xxmi_toolbox-{version_text(version)}{suffix}.zip"
