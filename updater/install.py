import os
import re
import shutil
import tempfile
import zipfile

from ..common.addon import ADDON_DIR, IS_EXTENSION
from ..common.utils import ToolError
from .releases import Release, download
from .version import asset_name, parse_version

_NEW = ADDON_DIR + ".new"
_OLD = ADDON_DIR + ".old"
_UNPACK = ADDON_DIR + ".unpack"
# Handed out separately rather than released, so an update carries them over.
_KEPT = ("experimental",)


def is_development_copy() -> bool:
	# Installing over a git checkout would delete it, history and local-only files included.
	return os.path.exists(os.path.join(ADDON_DIR, ".git"))


def remove_leftovers() -> None:
	"""A folder an earlier update could not delete, e.g. while Windows still held a file in it."""
	for folder in (_UNPACK, _NEW, _OLD):
		shutil.rmtree(folder, ignore_errors=True)


def _unpack(path: str, release: Release) -> None:
	# The extension zip holds the add-on's files, the legacy one its folder.
	inner = "" if IS_EXTENSION else "xxmi_toolbox"
	with zipfile.ZipFile(path) as archive:
		try:
			manifest = archive.read(f"{inner}/blender_manifest.toml".lstrip("/"))
		except KeyError as e:
			raise ToolError(
				f"{asset_name(release.version)} is not an XXMI Toolbox build"
			) from e
		match = re.search(
			r'^version\s*=\s*"([^"]+)"', manifest.decode("utf-8"), re.MULTILINE
		)
		if match is None or parse_version(match.group(1)) != release.version:
			raise ToolError(
				f"{asset_name(release.version)} does not hold {release.tag}"
			)
		remove_leftovers()
		archive.extractall(_UNPACK)
	os.replace(os.path.join(_UNPACK, inner) if inner else _UNPACK, _NEW)
	shutil.rmtree(_UNPACK, ignore_errors=True)


def _swap() -> None:
	# Renames first, so a folder that can't be moved (a file still open on Windows) leaves the add-on as it was.
	shutil.rmtree(_OLD, ignore_errors=True)
	try:
		os.replace(ADDON_DIR, _OLD)
	except OSError as e:
		shutil.rmtree(_NEW, ignore_errors=True)
		raise ToolError(f"Could not replace the add-on folder: {e}") from e
	try:
		for name in _KEPT:
			kept = os.path.join(_OLD, name)
			if os.path.isdir(kept) and not os.path.exists(os.path.join(_NEW, name)):
				shutil.copytree(kept, os.path.join(_NEW, name))
		os.replace(_NEW, ADDON_DIR)
	except OSError as e:
		shutil.rmtree(_NEW, ignore_errors=True)
		os.replace(_OLD, ADDON_DIR)
		raise ToolError(f"Could not replace the add-on folder: {e}") from e
	shutil.rmtree(_OLD, ignore_errors=True)


def install(release: Release) -> None:
	"""Replace the add-on's files with the release; Blender picks them up on restart."""
	if is_development_copy():
		raise ToolError("This is a git checkout: update it with git")
	if release.download_url is None:
		raise ToolError(
			f"{release.tag} has no {asset_name(release.version)} to install"
		)
	folder = tempfile.mkdtemp(prefix="xxmi_toolbox_update_")
	try:
		path = os.path.join(folder, asset_name(release.version))
		try:
			download(release.download_url, path)
		except OSError as e:
			raise ToolError(f"Download failed: {getattr(e, 'reason', e)}") from e
		try:
			_unpack(path, release)
		except zipfile.BadZipFile as e:
			raise ToolError(f"{asset_name(release.version)} is damaged") from e
		_swap()
	finally:
		shutil.rmtree(folder, ignore_errors=True)
