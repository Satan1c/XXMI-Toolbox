import bpy
from bpy.props import PointerProperty
from bpy.types import PropertyGroup

from .model_swap.settings import XXMI_TOOLBOX_ModelSwapSettings
from .vertex_groups.settings import XXMI_TOOLBOX_VertexGroupSettings


class XXMI_TOOLBOX_Settings(PropertyGroup):
	vertex_groups: PointerProperty(type=XXMI_TOOLBOX_VertexGroupSettings)  # type: ignore
	model_swap: PointerProperty(type=XXMI_TOOLBOX_ModelSwapSettings)  # type: ignore


def register():
	bpy.utils.register_class(XXMI_TOOLBOX_Settings)
	bpy.types.Scene.xxmi_toolbox = PointerProperty(type=XXMI_TOOLBOX_Settings)


def unregister():
	del bpy.types.Scene.xxmi_toolbox
	bpy.utils.unregister_class(XXMI_TOOLBOX_Settings)
