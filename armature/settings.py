from bpy.props import BoolProperty
from bpy.types import PropertyGroup

GATHER_DESCRIPTION = (
	"Move each ID armature into the collection holding the dumped meshes it deforms"
)
CONNECT_DESCRIPTION = (
	"Point each kept game bone at its child and connect them, so the armature reads as a skeleton. Bone axes "
	"change, so poses and actions made for the original bones won't fit; the ID armatures are updated to match"
)


class XXMI_TOOLBOX_ArmatureSettings(PropertyGroup):
	gather_ids: BoolProperty(
		name="Into Collections", default=True, description=GATHER_DESCRIPTION
	)  # type: ignore
	connect_bones: BoolProperty(
		name="Connect Bones", default=True, description=CONNECT_DESCRIPTION
	)  # type: ignore
