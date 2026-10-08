import bpy

from . import operators

classes = (operators.XXMI_TOOLBOX_OT_export_material_textures,)

register, unregister = bpy.utils.register_classes_factory(classes)
