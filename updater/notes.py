import re
import textwrap

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|`)(.+?)\1")
_BULLET = re.compile(r"^(\s*)[-*+]\s+")


def _plain(line: str) -> str:
	line = _LINK.sub(r"\1", line)
	line = _EMPHASIS.sub(r"\2", line)
	return _BULLET.sub(lambda m: m.group(1) + "• ", line)


def changes_of(notes: str) -> list[str]:
	"""The lines of the release notes' Changes section, as plain text."""
	lines, inside = [], False
	for line in notes.replace("\r", "").splitlines():
		if line.startswith("#"):
			inside = line.lstrip("#").strip().lower() == "changes"
		elif inside and line.strip():
			lines.append(_plain(line.rstrip()))
	return lines


def wrapped(lines: list[str], width: int) -> list[str]:
	"""Lines broken to fit width characters, continuing under a bullet's text."""
	out = []
	for line in lines:
		indent = len(line) - len(line.lstrip())
		bullet = line.lstrip().startswith("• ")
		out += textwrap.wrap(
			line,
			width,
			subsequent_indent=" " * (indent + (2 if bullet else 0)),
			drop_whitespace=True,
		) or [""]
	return out
