import functools
import logging
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

from bpy.types import Operator

from .utils import ToolError, blender_error

# Everything the toolbox writes to the system console. Operators' reports go there too, so a user's console holds
# the whole story; the details only show with the Detailed Console Log preference on.
log = logging.getLogger("xxmi_toolbox")

_LEVELS = {"ERROR": logging.ERROR, "WARNING": logging.WARNING}
_handler: logging.Handler | None = None


def start_logging(detailed: bool) -> None:
	global _handler
	if _handler is None:
		_handler = logging.StreamHandler(sys.stdout)
		_handler.setFormatter(
			logging.Formatter("XXMI Toolbox %(levelname)s: %(message)s")
		)
		log.addHandler(_handler)
		log.propagate = False
	log.setLevel(logging.DEBUG if detailed else logging.INFO)


def stop_logging() -> None:
	global _handler
	if _handler is not None:
		log.removeHandler(_handler)
		_handler = None


@contextmanager
def timed(step: str) -> Iterator[None]:
	"""Write how long the step took, in the detailed log."""
	start = time.perf_counter()
	try:
		yield
	finally:
		log.debug("%s took %.2f s", step, time.perf_counter() - start)


def report(operator: Operator, kind: str, message: str) -> None:
	"""Report to the user and write it to the console, where the details around it are."""
	label = operator.bl_label
	text = message if message.startswith(label) else f"{label}: {message}"
	log.log(_LEVELS.get(kind, logging.INFO), text)
	operator.report({kind}, message)


def _first_line(error: Exception) -> str:
	text = blender_error(error)
	return text.splitlines()[0] if text else type(error).__name__


def _failed(operator: Operator, error: Exception) -> set[str]:
	if isinstance(error, ToolError):
		report(operator, "ERROR", str(error))
	else:
		log.exception("%s failed", operator.bl_label)
		operator.report(
			{"ERROR"},
			f"{operator.bl_label} failed: {_first_line(error)}. The system console has the details",
		)
	return {"CANCELLED"}


def _guarded(method: Callable[..., set[str]], name: str) -> Callable[..., set[str]]:
	# Blender checks how many arguments execute and invoke take, so each gets its own.
	if name == "invoke":

		def guarded(self: Operator, context, event) -> set[str]:
			try:
				return method(self, context, event)
			except Exception as e:
				return _failed(self, e)

	else:

		def guarded(self: Operator, context) -> set[str]:
			try:
				return method(self, context)
			except Exception as e:
				return _failed(self, e)

	functools.update_wrapper(guarded, method)
	guarded.guarded = True
	return guarded


def guard_operators(classes: Iterable[type]) -> None:
	"""Make every operator's execute and invoke end in an error report instead of a Python traceback: a ToolError
	as it is, anything else in short with its traceback in the console."""
	for cls in classes:
		if not issubclass(cls, Operator):
			continue
		for name in ("execute", "invoke"):
			method = getattr(cls, name, None)
			if method is not None and not getattr(method, "guarded", False):
				setattr(cls, name, _guarded(method, name))
