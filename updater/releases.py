import json
import shutil
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass

from .version import Version, asset_name, parse_version

REPOSITORY = "Satan1c/XXMI-Toolbox"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
_LATEST = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
_TIMEOUT = 15


@dataclass
class Release:
	version: Version
	tag: str
	page: str
	download_url: str | None


def _ssl_context() -> ssl.SSLContext:
	# Python can miss the system certificates on macOS and some Windows setups; Blender bundles certifi.
	try:
		import certifi
	except ImportError:
		return ssl.create_default_context()
	return ssl.create_default_context(cafile=certifi.where())


def _open(url: str, accept: str):
	request = urllib.request.Request(
		url, headers={"Accept": accept, "User-Agent": "xxmi-toolbox-updater"}
	)
	return urllib.request.urlopen(request, timeout=_TIMEOUT, context=_ssl_context())


def latest_release() -> Release | None:
	"""The newest published release, or None while there is none. Raises OSError."""
	try:
		with _open(_LATEST, "application/vnd.github+json") as response:
			data = json.load(response)
	except urllib.error.HTTPError as e:
		if e.code == 404:
			return None
		raise
	version = parse_version(data.get("tag_name", ""))
	if version is None:
		return None
	name = asset_name(version)
	url = next(
		(
			a["browser_download_url"]
			for a in data.get("assets", [])
			if a["name"] == name
		),
		None,
	)
	return Release(version, data["tag_name"], data.get("html_url", RELEASES_PAGE), url)


def download(url: str, path: str) -> None:
	with _open(url, "application/octet-stream") as response, open(path, "wb") as file:
		shutil.copyfileobj(response, file)
