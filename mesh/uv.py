from bpy.types import Object

from ..common.utils import rename_all


def texcoord_name(index: int) -> str:
	return "TEXCOORD.xy" if index == 0 else f"TEXCOORD{index}.xy"


def clean_uv_names(obj: Object) -> int:
	layers = list(obj.data.uv_layers)
	rename_all(layers, [texcoord_name(i) for i in range(len(layers))])
	return len(layers)
