from ..common.operators import register_classes_factory
from . import operators

classes = (operators.XXMI_TOOLBOX_OT_export_material_textures,)

register, unregister = register_classes_factory(classes)
