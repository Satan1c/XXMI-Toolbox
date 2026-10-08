from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Context, Object, Operator

from ..common.operators import PerMeshOperator
from ..common.utils import ToolError
from . import cleanup, weights
from .ids import sort_vertex_groups
from .settings import MERGE_MODES


class XXMI_TOOLBOX_OT_merge_vertex_groups(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.merge_vertex_groups"
	bl_label = "Merge Vertex Groups"
	bl_description = "Merge vertex groups that address the same ID (`7`, `7.1`, `7.head.001`) or differ only by Blender's .001 suffix, then sort"

	mode: EnumProperty(name="Mode", items=MERGE_MODES, default="ALL")  # type: ignore
	names: StringProperty(name="Groups")  # type: ignore
	first: IntProperty(name="From", min=0)  # type: ignore
	last: IntProperty(name="To", min=0)  # type: ignore

	def process(self, context: Context, obj: Object) -> None:
		active = obj.vertex_groups.active
		if self.mode == "ACTIVE" and active is None:
			raise ToolError(f"{obj.name}: no active vertex group")
		scope = cleanup.merge_scope(
			self.mode,
			active.name if active else "",
			self.names,
			self.first,
			self.last,
		)
		cleanup.merge(obj, scope)
		sort_vertex_groups(obj)


class XXMI_TOOLBOX_OT_fill_vertex_group_gaps(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.fill_vertex_group_gaps"
	bl_label = "Fill Vertex Group Gaps"
	bl_description = (
		"Add missing IDs so the list runs 0..N without gaps, prefix name-only groups with their position "
		"(`hair` at position 2 becomes `2.hair`), then sort"
	)

	largest: IntProperty(name="Largest", min=0, max=cleanup.FILL_MAX_ID - 1)  # type: ignore

	def process(self, context: Context, obj: Object) -> None:
		cleanup.fill_gaps(obj, self.largest)
		sort_vertex_groups(obj)


class XXMI_TOOLBOX_OT_remove_unused_vertex_groups(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.remove_unused_vertex_groups"
	bl_label = "Remove Unused Vertex Groups"
	bl_description = "Remove vertex groups without any weight above the threshold"

	threshold: FloatProperty(name="Threshold", min=0.0, max=1.0, default=0.0)  # type: ignore

	def process(self, context: Context, obj: Object) -> None:
		cleanup.remove_unused(obj, self.threshold)


class XXMI_TOOLBOX_OT_fill_missing_weights(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.fill_missing_weights"
	bl_label = "Fill Missing Weights"
	bl_description = (
		"Give every vertex without any weight the weights of the nearest weighted vertex of the same mesh: vertices "
		"without weights don't follow the skeleton in game"
	)

	def execute(self, context: Context) -> set[str]:
		self.filled = 0
		return super().execute(context)

	def process(self, context: Context, obj: Object) -> None:
		self.filled += weights.fill_missing(obj)

	def summary(self, count: int) -> str:
		return f"Filled the weights of {self.filled} vertices in {count} meshes"


class XXMI_TOOLBOX_OT_remove_all_vertex_groups(PerMeshOperator, Operator):
	bl_idname = "xxmi_toolbox.remove_all_vertex_groups"
	bl_label = "Remove All Vertex Groups"
	bl_description = "Remove every vertex group from the selected meshes"

	def process(self, context: Context, obj: Object) -> None:
		cleanup.remove_all(obj)
